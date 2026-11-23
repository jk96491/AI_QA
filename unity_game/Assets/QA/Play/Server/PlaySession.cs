// 플레이 모드 메시지 처리 (PLAY_PROTOCOL 4장). 메인 스레드에서 Pump() 로 돈다.
//   hello, play_describe, set_loadout, reset, observe, act, get_log, bye
//   act 중 전투: combat_started → (trigger ↔ trigger_response)* → combat_ended → action_result. 전투 중 다른 요청 → error(busy)
// 세계 정지: 시간은 act 처리 중 ActionRunner.Tick 에서만 흐른다. 응답을 보낸 뒤 다음 요청까지 아무것도 Step 하지 않는다.
using Btqa.Game;
using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using Qa.Data;
using Qa.Play.Actions;
using Qa.Play.Combat;
using Qa.Sim;
using Qa.Play.Log;
using Qa.Play.Perception;
using Qa.Play.World;
using Qa.Protocol;

namespace Qa.Play.Server
{
    public static class PP
    {
        public const string Protocol = "play";
        public const string ProtocolVersion = "0.1";

        public const string Hello = "hello", HelloOk = "hello_ok";
        public const string Describe = "play_describe", Description = "play_description";
        public const string SetLoadout = "set_loadout", Reset = "reset", Observe = "observe", Act = "act";
        public const string GetLog = "get_log", PlayLog = "play_log", Bye = "bye";
        public const string Observation = "observation", ActionResult = "action_result";
        public const string TriggerResponse = "trigger_response", Trigger = "trigger", LoadoutOk = "loadout_ok";
        public const string CombatStarted = "combat_started", CombatEnded = "combat_ended";

        // 밸런스 프로토콜 오류 코드 + 플레이 추가분 (4.9)
        public const string EUnknownBoss = "unknown_boss", EUnknownAction = "unknown_action", EBusy = "busy", ENotReset = "not_reset";

        /// <summary>P1 에서 구현한 행동 (play_describe.actions 에 이것만 싣는다).</summary>
        public static readonly string[] Actions = { "move_to", "interact", "ui_click", "use_item", "engage", "wait" };
    }

    public sealed class PlayOptions
    {
        public long DefaultSeed = 1;
        public double Speed = 1.0;       // 0 이하 = 즉시 (헤드리스는 항상 즉시)
        public double CombatSpeed = -1;  // 전투 장면 배속 (-qaPlayCombatSpeed, 음수 = Speed 와 같음). 결과와 무관
        public bool Omniscient;
        public bool Instant;
        public int SettleFrames = 2;     // UI 변경 후 레이캐스트가 새 배치를 보도록 응답 전 대기 프레임
    }

    public sealed class PlaySession
    {
        readonly PlayServer _server;
        readonly SpecRepository _repo;
        readonly PlayData _data;
        readonly IPlayScene _scene;
        readonly PlayOptions _opt;
        readonly SemanticObserver _semantic;
        readonly HierarchyObserver _hier;
        readonly Action<string> _onAction;   // 관람용 로그 표시

        WorldState _world;
        readonly PlayLog _log = new PlayLog();
        long _conn = -1;
        bool _isReset;
        int _obsSeq;

        PlayRequest _req;
        PlayRequest _deferred;            // 전투 대기 중 받은 연결 종료·bye (전투 정리 후 처리)
        Loadout _loadout = new Loadout();
        readonly SimConfig _cfg;
        ActiveCombat _combat;
        string _combatAbort;              // 전투가 중단됐으면 사유 (action_result failed)
        double _combatAcc;
        ActionRunner _runner;
        JToken _actSeq;
        string _actName;
        Func<JObject> _respond;
        int _settle;
        double _acc;

        public WorldState World => _world;

        sealed class ActiveCombat
        {
            public CombatSim Sim;
            public ICombatPresenter Pres;   // 창 모드 전투 장면 (null = 즉시/간이 표시)
            public EntityState Enemy;
            public string EncounterId;
            public int PendingIndex = -1;
        }

        sealed class CombatAbort : Exception
        {
            public CombatAbort(string m) : base(m) { }
        }

        public PlaySession(PlayServer server, SpecRepository repo, PlayData data, IPlayScene scene, PlayOptions opt, Action<string> onAction, SimConfig cfg)
        {
            _cfg = cfg;
            _server = server;
            _repo = repo;
            _data = data;
            _scene = scene;
            _opt = opt;
            _onAction = onAction ?? (_ => { });
            _semantic = new SemanticObserver(scene, opt.Omniscient);
            _hier = new HierarchyObserver(scene, opt.Omniscient);
        }

        // ------------------------------------------------------------------ 펌프 (매 프레임)
        public void Pump(double realDelta)
        {
            if (_combat != null)
            {
                PumpCombat(realDelta);
                return;
            }
            if (_req == null && _deferred != null)
            {
                var d = _deferred;
                _deferred = null;
                Take(d);
                if (_req == null) return;
            }
            if (_req == null)
            {
                if (!_server.Inbox.TryTake(out var r)) return;
                Take(r);
                if (_req == null) return;
            }

            if (_runner != null && !_runner.Finished)
            {
                try
                {
                    int max = (int)Math.Ceiling(_data.Limits.MaxActionSeconds / _data.Limits.Dt) + 2;
                    if (_opt.Instant || _opt.Speed <= 0)
                    {
                        for (int i = 0; i < max && _runner.Tick(); i++) { }
                    }
                    else
                    {
                        _acc += realDelta * _opt.Speed;
                        int n = 0;
                        while (_acc >= _data.Limits.Dt && n < max && _runner.Tick()) { _acc -= _data.Limits.Dt; n++; }
                    }
                    _scene.Sync(_world);
                    if (_runner.Finished) AfterAction();
                }
                catch (Exception ex)
                {
                    _runner = null;
                    Reply(P.MakeError(P.EInternal, ex.GetType().Name + ": " + ex.Message));
                }
                return;
            }

            if (_respond != null)
            {
                if (_settle-- > 0) return;
                var f = _respond;
                _respond = null;
                _scene.Sync(_world);
                JObject m;
                try { m = f(); }
                catch (Exception ex) { m = P.MakeError(P.EInternal, ex.GetType().Name + ": " + ex.Message); }
                Reply(m);
            }
        }

        /// <summary>요청 1개 시작 (연결 종료·파싱 오류 포함).</summary>
        void Take(PlayRequest r)
        {
            if (r.Disconnected)
            {
                if (r.Connection == _conn) { _isReset = false; _loadout = new Loadout(); }
                r.Complete();
                return;
            }
            if (r.Connection != _conn)
            {
                _conn = r.Connection;   // 새 연결: reset 부터, 로드아웃도 새로
                _isReset = false;
                _loadout = new Loadout();
            }
            if (r.PreError != null)
            {
                SendTo(r, r.PreError);
                return;
            }
            _req = r;
            try { Begin(r.Msg); }
            catch (ProtocolException ex) { Reply(P.MakeError(ex.Code, ex.Message)); }
            catch (ActionArgException ex) { _runner = null; Reply(P.MakeError(P.EBadRequest, ex.Message)); }
            catch (Exception ex) { _runner = null; Reply(P.MakeError(P.EInternal, ex.GetType().Name + ": " + ex.Message)); }
        }

        static void SendTo(PlayRequest r, JObject m)
        {
            try { r.Channel.Send(m); } catch (IOException) { }
            r.Complete();
        }

        void Reply(JObject m, bool close = false)
        {
            var r = _req;
            if (r == null) return;
            _req = null;
            _respond = null;
            try { if (m != null) r.Channel.Send(m); }
            catch (IOException) { close = true; _runner = null; }
            r.CloseAfter = close;
            r.Complete();
        }

        /// <summary>현재 act 의 연결로 중간 메시지(combat_started·trigger·combat_ended) 송신.</summary>
        void SendMid(JObject m)
        {
            try { _req.Channel.Send(m); }
            catch (IOException) { throw new CombatAbort("연결 끊김"); }
        }

        void AfterAction()
        {
            if (_runner.Encounter != null) StartCombat();
            else ScheduleActionResult();
        }

        // ------------------------------------------------------------------ 전투 (PLAY_PROTOCOL 4.7)
        void StartCombat()
        {
            var w = _world;
            var enemy = _runner.Encounter;
            var scen = enemy.Def.Scenario;
            var boss = _repo.BossFor(scen);
            var spec = _repo.Class(w.Class);
            var entry = _loadout.Find(w.Class, scen);
            long seed = w.BeginEncounter(enemy, out var encId);
            var c = new ActiveCombat { Enemy = enemy, EncounterId = encId };
            var started = new JObject
            {
                ["type"] = PP.CombatStarted, ["seq"] = _actSeq?.DeepClone(), ["encounter_id"] = encId, ["enemy"] = enemy.Id,
                ["boss"] = boss.Name, ["class"] = w.Class, ["scenario"] = scen, ["seed"] = seed,
                ["loadout"] = new JObject { ["matched"] = entry != null, ["source"] = entry?.Source, ["persona"] = _loadout.Persona },
                ["triggers"] = entry != null && entry.Triggers.Count > 0 ? new JObject { ["boss_hp_below"] = new JArray(entry.Triggers) } : null,
                ["start_state"] = "full",
            };
            _log.Add(w.Time, "combat_start", started.DeepClone());
            _onAction("전투 시작 " + enemy.Id + " (" + scen + ", seed " + seed + ", loadout " + (entry != null ? "학습값" : "default") + ")");
            TriggerHandler onTrigger = (index, state, totals) =>
            {
                SendMid(new JObject
                {
                    ["type"] = PP.Trigger, ["seq"] = _actSeq?.DeepClone(), ["encounter_id"] = encId,
                    ["index"] = index, ["state"] = state, ["totals"] = totals,
                });
                c.PendingIndex = index;
                var po = WaitTriggerResponse(c, index);   // 응답이 올 때까지 전투 시간 정지
                c.PendingIndex = -1;
                c.Pres?.OnTrigger(index);
                _log.Add(w.Time, "trigger", new JObject { ["encounter_id"] = encId, ["index"] = index, ["params"] = po?.DeepClone() });
                return po;
            };
            // 창 모드는 전투 장면 연출 (뷰어가 이벤트를 읽도록 기록만 켠다 — 로직 동일, result 의 "events" 는 보낼 때 뺀다)
            c.Pres = _opt.Instant || _opt.Speed <= 0 ? null : _scene.Presenter;
            var cfg = c.Pres != null ? _cfg.WithRecordEvents(true) : _cfg;
            // 밸런스 run_episode 와 같은 인자: 같은 (class, scenario, seed, params, 트리거 응답) → 같은 result (T5)
            c.Sim = new CombatSim(spec, boss, entry?.Params, seed, new JValue(seed), cfg,
                                  entry != null && entry.Triggers.Count > 0 ? entry.Triggers : null, onTrigger);
            _combat = c;
            _combatAcc = 0;
            _combatAbort = null;
            CombatGuard(() =>
            {
                SendMid(started);
                if (c.Pres == null) _scene.SyncCombat(_world, c.Enemy, c.Sim);
                c.Sim.Begin();   // index 0 트리거
                c.Pres?.Begin(c.Sim, w.Class, scen, seed, enemy.Def.Label, _scene.SetFieldVisible);
            });
        }

        void PumpCombat(double realDelta)
        {
            var c = _combat;
            // 전투 중 들어온 다른 요청 → busy (trigger 대기 중이 아닐 때 온 trigger_response 는 bad_request)
            while (_combat != null && _deferred == null && _server.Inbox.TryTake(out var r)) DuringCombat(r);
            if (_combat == null) return;
            CombatGuard(() =>
            {
                if (c.Pres != null)
                {
                    if (c.Pres.Tick(realDelta, _opt.CombatSpeed > 0 ? _opt.CombatSpeed : _opt.Speed)) FinishCombat();   // 장면 연출이 판을 한 틱씩 진행
                    return;
                }
                if (_opt.Instant || _opt.Speed <= 0)
                {
                    while (!c.Sim.Done) c.Sim.Step();
                }
                else
                {
                    _combatAcc += realDelta * _opt.Speed;
                    int n = 0;
                    while (_combatAcc >= _cfg.Dt && !c.Sim.Done && n < 2000) { c.Sim.Step(); _combatAcc -= _cfg.Dt; n++; }
                }
                _scene.SyncCombat(_world, c.Enemy, c.Sim);
                if (c.Sim.Done) FinishCombat();
            });
        }

        void DuringCombat(PlayRequest r)
        {
            if (r.Disconnected || r.Type == PP.Bye || r.Connection != _conn)
            {
                _deferred = r;
                AbortCombat("연결 종료");
                return;
            }
            if (r.PreError != null) { SendTo(r, r.PreError); return; }
            if (r.Type == PP.TriggerResponse) { SendTo(r, P.MakeError(P.EBadRequest, "대기 중인 trigger 없음")); return; }
            SendTo(r, P.MakeError(PP.EBusy, "전투 중 (" + _combat.EncounterId + ") — trigger_response 외 요청은 받지 않음"));
        }

        JObject WaitTriggerResponse(ActiveCombat c, int index)
        {
            var id = new JValue(c.EncounterId);
            while (true)
            {
                var r = _server.Inbox.Take();
                if (r.Disconnected || r.Type == PP.Bye || r.Connection != _conn)
                {
                    _deferred = r;
                    throw new CombatAbort("trigger 응답 대기 중 연결 종료");
                }
                if (r.PreError != null) { SendTo(r, r.PreError); continue; }
                if (r.Type == PP.TriggerResponse)
                {
                    try
                    {
                        var po = CombatEpisodeRunner.CheckTriggerResponse(r.Msg, "encounter_id", id, index);
                        if (po != null) _repo.Class(_world.Class).ResolveParams(_repo.Class(_world.Class).DefaultParams(), po);   // 이름·범위 미리 검사
                        r.Complete();
                        return po;
                    }
                    catch (ProtocolException ex) { SendTo(r, P.MakeError(ex.Code, ex.Message)); continue; }
                    catch (ParamException ex) { SendTo(r, P.MakeError(ex.Code, ex.Message)); continue; }
                }
                SendTo(r, P.MakeError(PP.EBusy, "전투 중 (" + c.EncounterId + ", trigger " + index + " 응답 대기) — trigger_response 만 받음"));
            }
        }

        /// <summary>전투 진행 중 예외 정리: 연결 종료 → 조용히 중단, 그 외 → 중단 + action_result failed.</summary>
        void CombatGuard(Action a)
        {
            try { a(); }
            catch (CombatAbort ex) { AbortCombat(ex.Message); }
            catch (ParamException ex) { AbortCombat("trigger params 오류: " + ex.Message); }
            catch (Exception ex) { AbortCombat(ex.GetType().Name + ": " + ex.Message); }
        }

        void AbortCombat(string why)
        {
            var c = _combat;
            if (c == null) return;
            _combat = null;
            c.Pres?.End();
            _scene.EndCombat();
            _world.Emit("combat_aborted", new JObject { ["encounter_id"] = c.EncounterId, ["reason"] = why });
            _world.PlayerState = "idle";
            _combatAbort = why;
            if (_deferred != null)
            {
                // 연결이 끊겼으면 결과를 보낼 곳이 없다
                _runner = null;
                Reply(null);
                return;
            }
            ScheduleActionResult();
        }

        void FinishCombat()
        {
            var c = _combat;
            var w = _world;
            var result = (JObject)c.Sim.Result().DeepClone();
            result.Remove("events");   // 연출용 기록 — run_episode(record_events 없음)와 같은 필드만
            w.AddSeconds(c.Sim.Time);
            var aftermath = w.EndEncounter(c.Enemy, c.EncounterId, c.Sim.Cleared);
            _combat = null;
            c.Pres?.End();
            _scene.EndCombat();
            _log.Add(w.Time, "combat_result", new JObject { ["encounter_id"] = c.EncounterId, ["result"] = result.DeepClone(), ["aftermath"] = aftermath.DeepClone() });
            _onAction("전투 끝 " + (c.Sim.Cleared ? "승리" : "패배") + " " + Math.Round(c.Sim.Time) + "s 사망 " + c.Sim.Deaths);
            try
            {
                _req.Channel.Send(new JObject
                {
                    ["type"] = PP.CombatEnded, ["seq"] = _actSeq?.DeepClone(), ["encounter_id"] = c.EncounterId,
                    ["result"] = result.DeepClone(), ["aftermath"] = aftermath,
                });
            }
            catch (IOException) { _runner = null; Reply(null); return; }
            _scene.Sync(w);
            ScheduleActionResult();
        }

        void Later(Func<JObject> f)
        {
            if (_world != null) _scene.Sync(_world);   // UI 변경을 먼저 반영 → 대기 프레임 동안 레이캐스트 배치가 갱신된다
            _respond = f;
            _settle = _opt.SettleFrames;
        }

        // ------------------------------------------------------------------ 디스패치
        void Begin(JObject msg)
        {
            var kind = msg["type"]?.Type == JTokenType.String ? (string)msg["type"] : null;
            switch (kind)
            {
                case PP.Hello: Reply(Hello(msg)); return;
                case PP.Describe: Reply(Describe()); return;
                case PP.Reset: DoReset(msg); return;
                case PP.Observe: DoObserve(msg); return;
                case PP.Act: DoAct(msg); return;
                case PP.GetLog: DoGetLog(msg); return;
                case PP.Bye: Reply(null, true); return;
                case PP.SetLoadout:
                {
                    _loadout = Loadout.Parse(msg, _repo);
                    _log.Add(_world?.Time ?? 0, "set_loadout", new JObject { ["persona"] = _loadout.Persona, ["entries"] = _loadout.Entries.Count });
                    Reply(new JObject { ["type"] = PP.LoadoutOk, ["entries"] = _loadout.Entries.Count });
                    return;
                }
                case PP.TriggerResponse:
                    throw new ProtocolException(P.EBadRequest, "대기 중인 trigger 없음 (전투 밖)");
                default:
                    throw new ProtocolException(P.EUnknownType, "알 수 없는 type '" + msg["type"] + "'");
            }
        }

        JObject Hello(JObject msg)
        {
            var proto = msg["protocol"]?.Type == JTokenType.String ? (string)msg["protocol"] : null;
            var v = msg["protocol_version"]?.ToString() ?? "";
            if (proto != PP.Protocol)
                throw new ProtocolException(P.EProtocolVersion, "이 인스턴스는 플레이 모드(protocol \"play\" " + PP.ProtocolVersion + ") 서버. 요청 protocol=" + (proto ?? "없음") + " version='" + v + "'");
            // 0.x 는 부 버전 변경도 호환 깨짐 허용 (PLAY_PROTOCOL 7장) → 주.부 일치 요구
            if (MajorMinor(v) != MajorMinor(PP.ProtocolVersion))
                throw new ProtocolException(P.EProtocolVersion, "지원 버전 " + PP.ProtocolVersion + ", 요청 '" + v + "'");
            return new JObject
            {
                ["type"] = PP.HelloOk, ["protocol"] = PP.Protocol, ["protocol_version"] = PP.ProtocolVersion,
                ["game"] = _repo.GameName, ["game_version"] = _repo.GameVersion,
            };
        }

        static string MajorMinor(string v)
        {
            var p = v.Split('.');
            return p.Length >= 2 ? p[0] + "." + p[1] : v;
        }

        JObject Describe()
        {
            var bosses = new JArray();
            var seen = new HashSet<string>(StringComparer.Ordinal);
            var scenarios = new JArray();
            foreach (var s in _repo.Scenarios)
            {
                var b = _repo.BossFor(s.Name).Name;
                scenarios.Add(new JObject { ["name"] = s.Name, ["boss"] = b });
                if (seen.Add(b)) bosses.Add(new JObject { ["name"] = b, ["display_name"] = b });
            }
            var actions = new JArray
            {
                new JObject { ["name"] = "move_to", ["args"] = new JObject { ["target"] = "entity_id | null", ["pos"] = "[x,y,z] | null" } },
                new JObject { ["name"] = "interact", ["args"] = new JObject { ["target"] = "entity_id", ["verb"] = "talk|pickup|open|enter" } },
                new JObject { ["name"] = "ui_click", ["args"] = new JObject { ["ui_id"] = "string" } },
                new JObject { ["name"] = "use_item", ["args"] = new JObject { ["item_id"] = "string" } },
                new JObject { ["name"] = "engage", ["args"] = new JObject { ["target"] = "entity_id" } },
                new JObject { ["name"] = "wait", ["args"] = new JObject { ["seconds"] = "number | null", ["until"] = "event_kind | null" } },
            };
            return new JObject
            {
                ["type"] = PP.Description,
                ["protocol_version"] = PP.ProtocolVersion, ["game"] = _repo.GameName, ["game_version"] = _repo.GameVersion,
                ["classes"] = new JArray(_repo.ClassNames),
                ["bosses"] = bosses,
                ["scenarios"] = scenarios,
                ["actions"] = actions,
                ["limits"] = new JObject { ["max_action_seconds"] = _data.Limits.MaxActionSeconds, ["interact_range"] = _data.Limits.InteractRange },
                ["observation_modes"] = new JArray("semantic", "hierarchy"),
                ["debug"] = new JObject { ["omniscient"] = _opt.Omniscient },
                ["combat"] = new JObject
                {
                    ["trigger_state_features"] = new JArray(P.TriggerStateFeatures),
                    ["trigger_totals"] = new JArray(P.TriggerTotalsFields),
                    ["encounter_start_state"] = "full",
                    ["encounters"] = Encounters(),
                },
                ["quests"] = QuestList(),
                ["stage"] = "P3",
            };
        }

        JArray Encounters()
        {
            var a = new JArray();
            foreach (var z in _data.Zones)
                foreach (var e in z.Entities)
                    if (e.Role == "enemy")
                        a.Add(new JObject { ["enemy"] = e.Id, ["zone"] = z.Id, ["scenario"] = e.Scenario, ["boss"] = _repo.BossFor(e.Scenario).Name });
            return a;
        }

        JArray QuestList()
        {
            var a = new JArray();
            foreach (var q in _data.Quests) a.Add(new JObject { ["id"] = q.Id, ["title"] = q.Title });
            return a;
        }

        void DoReset(JObject msg)
        {
            long seed = _opt.DefaultSeed;
            var st = msg["seed"];
            if (st != null && st.Type != JTokenType.Null)
            {
                if (st.Type != JTokenType.Integer) throw new ProtocolException(P.EBadRequest, "seed 는 정수여야 함");
                seed = st.Value<long>();
            }
            var ct = msg["class"];
            string cls = _repo.ClassNames.Count > 0 ? (_repo.HasClass("warrior") ? "warrior" : _repo.ClassNames[0]) : null;
            if (ct != null && ct.Type != JTokenType.Null)
            {
                cls = ct.Type == JTokenType.String ? (string)ct : null;
                if (!_repo.HasClass(cls)) throw new ProtocolException(P.EUnknownClass, "알 수 없는 class " + ct);
            }
            foreach (var p in msg.Properties())
                if (p.Name != "type" && p.Name != "seed" && p.Name != "class")
                    throw new ProtocolException(P.EBadRequest, "reset 인자는 seed·class 뿐 (항상 새 게임, 시작 지점 옵션 없음): '" + p.Name + "'");

            _runner = null;
            _world = new WorldState(_data, seed, cls);
            _log.Clear();
            var w = _world;
            _world.OnEvent += ev => _log.Add(ev.Time, ev.Kind, ev.Payload);
            _log.Add(0, "reset", new JObject { ["seed"] = seed, ["class"] = cls, ["omniscient"] = _opt.Omniscient });
            _world.Emit("new_game", new JObject { ["seed"] = seed, ["class"] = cls });
            _world.Begin();   // 시작 퀘스트 수락
            _isReset = true;
            _obsSeq = 0;
            _scene.Sync(_world);
            _onAction("reset seed=" + seed + " " + cls);
            Later(() => _semantic.Build(w, _obsSeq++));
        }

        void RequireReset()
        {
            if (!_isReset || _world == null) throw new ProtocolException(PP.ENotReset, "reset 을 먼저 보내야 함");
        }

        void DoObserve(JObject msg)
        {
            RequireReset();
            var mode = msg["mode"]?.Type == JTokenType.String ? (string)msg["mode"] : "semantic";
            if (mode == "semantic")
            {
                Later(() => _semantic.Build(_world, _obsSeq++));
                return;
            }
            if (mode != "hierarchy") throw new ProtocolException(P.EBadRequest, "mode 는 semantic|hierarchy");
            var root = msg["root"]?.Type == JTokenType.String ? (string)msg["root"] : null;
            int depth = msg["max_depth"]?.Type == JTokenType.Integer ? (int)msg["max_depth"] : 4;
            depth = Math.Max(0, Math.Min(depth, 12));
            Later(() =>
            {
                var t = _hier.Find(root);
                if (t == null) return P.MakeError(P.EBadRequest, "hierarchy root '" + root + "' 없음 (또는 지각 불가)");
                if (!_opt.Omniscient && t is UnityEngine.RectTransform && !Visibility.UiPerceivable(t))
                    return P.MakeError(P.EBadRequest, "hierarchy root '" + root + "' 없음 (또는 지각 불가)");
                return new JObject
                {
                    ["type"] = PP.Observation, ["seq"] = _obsSeq++, ["mode"] = "hierarchy", ["root"] = root ?? "ui",
                    ["game_time"] = Math.Round(_world.Time, 2), ["tree"] = _hier.Node(t, depth),
                };
            });
        }

        void DoAct(JObject msg)
        {
            RequireReset();
            var name = msg["action"]?.Type == JTokenType.String ? (string)msg["action"] : null;
            if (name == null) throw new ProtocolException(P.EBadRequest, "act 에 'action' 필요");
            var argsTok = msg["args"];
            if (argsTok != null && argsTok.Type != JTokenType.Null && argsTok.Type != JTokenType.Object)
                throw new ProtocolException(P.EBadRequest, "args 는 객체여야 함");
            var args = argsTok as JObject ?? new JObject();
            IPlayAction a;
            switch (name)
            {
                case "move_to": a = new MoveTo(); break;
                case "interact": a = new Interact(); break;
                case "ui_click": a = new UiClick(_hier); break;
                case "use_item": a = new UseItem(); break;
                case "engage": a = new Engage(); break;
                case "wait": a = new Wait(); break;
                default:
                    throw new ProtocolException(PP.EUnknownAction, "알 수 없는(또는 이 단계에서 아직 없는) 행동 '" + name + "'. 지원: " + string.Join(",", PP.Actions));
            }
            _actSeq = msg["seq"];
            _actName = name;
            _log.Add(_world.Time, "act", new JObject { ["seq"] = _actSeq?.DeepClone(), ["action"] = name, ["args"] = args.DeepClone() });
            var ctx = new ActionContext { World = _world, Perceivable = _semantic.EntityPerceivable };
            _acc = 0;
            _runner = new ActionRunner(ctx, a, args);   // ActionArgException → bad_request
            if (_runner.Finished) ScheduleActionResult();
        }

        void ScheduleActionResult()
        {
            var r = _runner;
            _runner = null;
            r.Refresh();
            var a = r.Action;
            string status = r.Status == ActionStatus.Done ? "done" : r.Status == ActionStatus.Failed ? "failed" : "interrupted";
            string reason = a.Reason, detail = a.ReasonDetail, by = a.InterruptedBy;
            if (_combatAbort != null)
            {
                status = "failed";
                reason = "invalid_state";
                detail = "combat aborted: " + _combatAbort;
                by = null;
                _combatAbort = null;
            }
            var seq = _actSeq;
            var summary = new JObject
            {
                ["seq"] = seq?.DeepClone(), ["action"] = _actName, ["status"] = status, ["reason"] = reason,
                ["game_seconds"] = Math.Round(r.GameSeconds, 2),
            };
            if (detail != null) summary["reason_detail"] = detail;
            if (by != null) summary["interrupted_by"] = by;
            _log.Add(_world.Time, "action_result", summary);
            _onAction(_actName + " → " + status + (reason != null ? " (" + reason + ")" : "") + (by != null ? " by " + by : ""));
            Later(() =>
            {
                var m = new JObject
                {
                    ["type"] = PP.ActionResult, ["seq"] = seq?.DeepClone(), ["status"] = status, ["reason"] = reason,
                };
                if (detail != null) m["reason_detail"] = detail;
                if (by != null) m["interrupted_by"] = by;
                m["game_seconds"] = Math.Round(r.GameSeconds, 2);
                m["observation"] = _semantic.Build(_world, _obsSeq++);
                return m;
            });
        }

        void DoGetLog(JObject msg)
        {
            int since = msg["since_seq"]?.Type == JTokenType.Integer ? (int)msg["since_seq"] : 0;
            Reply(new JObject { ["type"] = PP.PlayLog, ["entries"] = _log.Since(since), ["next_seq"] = _log.Count });
        }
    }
}
