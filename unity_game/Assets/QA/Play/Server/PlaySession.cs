// 플레이 모드 메시지 처리 (PLAY_PROTOCOL 4장). 메인 스레드에서 Pump() 로 돈다.
//   hello, play_describe, set_loadout, reset, observe, act, get_log, pilot_note(v0.3), bye
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
        public const string ProtocolVersion = "0.4";
        /// <summary>받는 버전 (0.x 는 주.부 일치). 0.3 클라이언트도 그대로 접속 — 0.4 기능(raw 입력·좌표)은 0.4 hello 에서만.</summary>
        public static readonly string[] Accepted = { "0.4", "0.3" };

        public const string Hello = "hello", HelloOk = "hello_ok";
        public const string Describe = "play_describe", Description = "play_description";
        public const string SetLoadout = "set_loadout", Reset = "reset", Observe = "observe", Act = "act";
        public const string GetLog = "get_log", PlayLog = "play_log", Bye = "bye";
        public const string Observation = "observation", ActionResult = "action_result";
        public const string TriggerResponse = "trigger_response", Trigger = "trigger", LoadoutOk = "loadout_ok";
        public const string CombatStarted = "combat_started", CombatEnded = "combat_ended";
        public const string PilotNote = "pilot_note", PilotNoteOk = "pilot_note_ok";

        /// <summary>조우 시작 상태 (v0.3): 체력·자원 = 보스 결계 회복 full, 물약 = 퀵슬롯 등록 물약 min(보유, cap).</summary>
        public const string EncounterStartState = "barrier_inventory_potions";
        /// <summary>pilot_note (4.10) 종류·최대 길이.</summary>
        public static readonly string[] PilotKinds = { "thought", "plan", "finding" };
        public const int PilotMaxChars = 200;

        // 밸런스 프로토콜 오류 코드 + 플레이 추가분 (4.9)
        public const string EBossMismatch = "boss_mismatch", EUnknownAction = "unknown_action", EBusy = "busy", ENotReset = "not_reset";

        /// <summary>P1 에서 구현한 행동 (play_describe.actions 에 이것만 싣는다).</summary>
        public static readonly string[] Actions = { "move_to", "interact", "ui_click", "use_item", "engage", "wait" };
        /// <summary>v0.4 저수준 입력 (input_mode "raw" 에서는 이것 + wait + move_to(pos) 만).</summary>
        public static readonly string[] RawActions = { "pointer_click", "pointer_move", "drag", "key_press", "key_hold", "text_input", "wait", "move_to" };
        public static readonly string[] InputModes = { "semantic", "raw" };
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
        readonly Action<string, string> _onPilotNote;   // 플레이어 메모 표시 (헤드리스·-qaNoPilotNotes 는 null)

        WorldState _world;
        readonly PlayLog _log = new PlayLog();
        long _conn = -1;
        bool _isReset;
        int _obsSeq;
        string _version = ProtoDefault;     // hello 로 정한 버전
        string _inputMode = "semantic";
        const string ProtoDefault = "0.3";
        bool V04 => _version == "0.4";

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
            public string PotionItem;      // 전투에 가져간 물약 아이템 (null = 없음)
            public int Carried;
        }

        sealed class CombatAbort : Exception
        {
            public CombatAbort(string m) : base(m) { }
        }

        public PlaySession(PlayServer server, SpecRepository repo, PlayData data, IPlayScene scene, PlayOptions opt, Action<string> onAction, SimConfig cfg,
                           Action<string, string> onPilotNote = null)
        {
            _cfg = cfg;
            _server = server;
            _repo = repo;
            _data = data;
            _scene = scene;
            _opt = opt;
            _onAction = onAction ?? (_ => { });
            _onPilotNote = onPilotNote;
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
                _version = ProtoDefault;
                _inputMode = "semantic";
                _semantic.IncludeCoords = false;
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
            // 보스 결계 (v0.3): 회복 직전 필드 상태를 기록하고, 물약은 퀵슬롯에 등록한 것을 min(보유, cap) 개 가져간다
            var potionItem = w.QuickSlotPotion();
            int available = potionItem != null ? w.CountOf(potionItem) : 0;
            int cap = spec.Stats.Potions;
            int carried = Math.Min(available, cap);
            var fieldState = w.Barrier(encId, potionItem, carried);
            var c = new ActiveCombat { Enemy = enemy, EncounterId = encId, PotionItem = potionItem, Carried = carried };
            var started = new JObject
            {
                ["type"] = PP.CombatStarted, ["seq"] = _actSeq?.DeepClone(), ["encounter_id"] = encId, ["enemy"] = enemy.Id,
                ["boss"] = boss.Name, ["class"] = w.Class, ["scenario"] = scen, ["seed"] = seed,
                ["loadout"] = new JObject { ["matched"] = entry != null, ["source"] = entry?.Source, ["persona"] = _loadout.Persona },
                ["triggers"] = entry != null && entry.Triggers.Count > 0 ? new JObject { ["boss_hp_below"] = new JArray(entry.Triggers) } : null,
                ["start_state"] = PP.EncounterStartState,
                ["field_state"] = fieldState,
                ["potions"] = new JObject { ["item"] = potionItem, ["available"] = available, ["carried"] = carried, ["cap"] = cap },
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
            c.Sim.SetStartPotions(carried);   // carried == cap 이면 밸런스 run_episode 와 같은 판 (T5)
            _combat = c;
            _combatAcc = 0;
            _combatAbort = null;
            CombatGuard(() =>
            {
                SendMid(started);
                if (c.Pres == null) _scene.SyncCombat(_world, c.Enemy, c.Sim);
                c.Sim.Begin();   // index 0 트리거
                c.Pres?.Begin(c.Sim, w.Class, scen, seed, enemy.Def.Label, _scene.SetFieldVisible, BarrierText(potionItem, carried, cap));
            });
        }

        string BarrierText(string item, int carried, int cap)
        {
            var label = item != null ? (_data.Item(item)?.Label ?? item) : null;
            return "보스 결계: 체력과 자원이 전투 준비 상태로 회복됩니다. 물약은 퀵슬롯에서 " +
                   (label != null ? label + " " + carried + "/" + cap + "개" : "0/" + cap + "개 (퀵슬롯에 물약 없음)") + "를 가져갑니다";
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
            var aftermath = w.EndEncounter(c.Enemy, c.EncounterId, c.Sim.Cleared, c.Sim.Deaths, c.PotionItem, Math.Min(c.Carried, c.Sim.ConsumablesUsed));
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
                case PP.PilotNote: DoPilotNote(msg); return;
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
            string got = null;
            foreach (var a in PP.Accepted) if (MajorMinor(v) == a) got = a;
            if (got == null)
                throw new ProtocolException(P.EProtocolVersion, "지원 버전 " + string.Join(", ", PP.Accepted) + ", 요청 '" + v + "'");
            _version = got;
            _semantic.IncludeCoords = V04;
            return new JObject
            {
                ["type"] = PP.HelloOk, ["protocol"] = PP.Protocol, ["protocol_version"] = got,
                ["game"] = _repo.GameName, ["game_version"] = _repo.GameVersion,
            };
        }

        static string MajorMinor(string v)
        {
            var p = v.Split('.');
            return p.Length >= 2 ? p[0] + "." + p[1] : v;
        }

        // ------------------------------------------------------------------ 행동·안내 선언 (play 0.3 선택 필드 4.2.1, 0.8.3)
        // 게임이 정본: 학습 쪽 외부 스펙(play_agent/specs/qa_arena.play.json)보다 우선. schema.properties 키 = args 키.
        // 작성 규칙: 플레이어가 게임 안에서 알 수 있는 것만 (숨은 좌표·데이터·의도적 QA 함정은 쓰지 않는다).
        static JObject Act(string name, JObject args, string desc, JObject props, params string[] required) => new JObject
        {
            ["name"] = name, ["args"] = args, ["description"] = desc,
            ["schema"] = new JObject { ["type"] = "object", ["properties"] = props, ["required"] = new JArray(required) },
        };
        static JObject Prop(string type, string desc) => new JObject { ["type"] = type, ["description"] = desc };

        JArray DeclaredActions()
        {
            string range = _data.Limits.InteractRange.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture);
            string maxSec = _data.Limits.MaxActionSeconds.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture);
            return new JArray
            {
                Act("move_to", new JObject { ["target"] = "entity_id | null", ["pos"] = "[x,y,z] | null" },
                    "엔티티(target) 또는 좌표(pos=[x,y,z]) 로 걸어간다. 둘 중 하나만 준다. 대상의 상호작용 거리(" + range + ") 안에 들어가면 done. " +
                    "시야 밖 대상은 not_visible — 근처 좌표나 지역 입구로 먼저 간다 (entities 에 known:\"marker\" 로 있는 퀘스트 대상은 시야 밖이어도 바로 갈 수 있다). 길이 없으면 unreachable, 창(modal)이 열려 있으면 blocked_by_modal. " +
                    "이동 중 적의 어그로 범위에 들어가면 전투가 자동으로 시작되고 학습된 BT 가 싸운다 (interrupted, 결과는 combats).",
                    new JObject
                    {
                        ["target"] = Prop("string", "observation.entities[].id"),
                        ["pos"] = new JObject { ["type"] = "array", ["items"] = new JObject { ["type"] = "number" }, ["description"] = "[x,y,z] 월드 좌표" },
                    }),
                Act("interact", new JObject { ["target"] = "entity_id", ["verb"] = "talk|pickup|open|enter" },
                    "엔티티와 상호작용. verb 는 그 엔티티 actions 에 있는 것 (talk 대화, pickup 줍기, open 열기, enter 지역 입구로 이동). " +
                    "범위 밖이면 자동으로 다가가지 않고 out_of_range — 먼저 move_to. 엔티티가 지원하지 않는 verb 는 not_interactable, 지금 할 수 없으면 invalid_state, 창이 열려 있으면 blocked_by_modal.",
                    new JObject
                    {
                        ["target"] = Prop("string", "observation.entities[].id"),
                        ["verb"] = new JObject { ["type"] = "string", ["enum"] = new JArray("talk", "pickup", "open", "enter") },
                    }, "target", "verb"),
                Act("ui_click", new JObject { ["ui_id"] = "string" },
                    "화면 UI 요소를 클릭 (screen.ui 의 id, 또는 hierarchy 노드 id). interactable:false 면 not_interactable — " +
                    "reason_detail 'blocked by <id>' 는 그 창이 가리고 있다는 뜻, 'disabled' 는 비활성.",
                    new JObject { ["ui_id"] = Prop("string", "screen.ui[].id") }, "ui_id"),
                Act("use_item", new JObject { ["item_id"] = "string" },
                    "인벤토리 아이템을 필드에서 사용 (inventory 의 id). 효과가 없는 상태(체력 가득에서 물약 등)나 쓸 수 없는 아이템이면 invalid_state, 창이 열려 있으면 blocked_by_modal. " +
                    "전투 중 물약은 BT 가 퀵슬롯 물약을 쓴다 — 이 행동이 아니다.",
                    new JObject { ["item_id"] = Prop("string", "observation.inventory[].id") }, "item_id"),
                Act("engage", new JObject { ["target"] = "entity_id" },
                    "적에게 다가가 일부러 전투를 시작한다. 전투는 학습된 BT 가 하고, 끝나면 done (승패는 combats[].cleared). " +
                    "적이 아니면 not_interactable. 지면 체크포인트(없으면 지역 시작점)에서 부활하고 적은 남는다.",
                    new JObject { ["target"] = Prop("string", "role=enemy 엔티티 id") }, "target"),
                Act("wait", new JObject { ["seconds"] = "number | null", ["until"] = "event_kind | null" },
                    "세계 시간을 보낸다: seconds 초, 또는 until 사건이 일어날 때까지 중 먼저 (최대 " + maxSec + "초, 넘으면 timeout). 둘 중 하나는 준다.",
                    new JObject
                    {
                        ["seconds"] = Prop("number", "초 (0~" + maxSec + ")"),
                        ["until"] = Prop("string", "세계 사건 종류 = events[].kind (예: dialog_closed, quest_progress, quest_completed, combat_ended, item_added)"),
                    }),
            };
        }

        static JObject PilotGuide() => new JObject
        {
            ["about"] = "QaArena: 마을과 숲으로 된 튜토리얼 RPG. 촌장의 의뢰로 시작해 숲의 늑대왕을 쓰러뜨린다.",
            ["system_prompt"] =
                "이 게임의 비전투 부분(이동·대화·퀘스트·아이템·UI)을 플레이한다.\n\n" +
                "관찰:\n" +
                "- player: 지역·위치·체력·골드·퀵슬롯·상태\n" +
                "- quests: 진행 중인 퀘스트와 목표 (progress [현재, 목표], hint_targets = 관련 엔티티 id). state=ready 는 반납만 남은 것\n" +
                "- entities: 지금 보이는 것 + 진행 중 퀘스트 목표의 대상 (같은 지역이면 시야 밖이어도 known:\"marker\" — 위치를 알아 move_to 가능). marker: quest_available / quest_turn_in / objective\n" +
                "- screen.modal: 입력을 막는 창 (dialog / quests / inventory / shop / tip). screen.ui: 클릭 가능한 UI 요소 (interactable)\n" +
                "- events: 직전 이후 일어난 일 (wait.until 에 쓰는 kind)\n\n" +
                "규칙:\n" +
                "- 상호작용은 먼저 move_to 로 다가간 뒤 interact. 보이지 않는 대상은 근처 좌표나 지역 입구로 먼저 간다.\n" +
                "- 창(modal)이 열려 있으면 그 창의 버튼으로 진행하거나 닫는다. interactable:false 버튼은 가려졌거나 비활성이다 — 가린 창부터 처리한다.\n" +
                "- 적에게 다가가거나 engage 하면 학습된 전투 AI 가 싸운다. 지면 체크포인트에서 부활하니 다시 시도할 수 있다.\n" +
                "- 게임 버그로 보이는 것은 finish 의 blocked 에 UI id·메시지를 포함해 적는다.",
            ["rules"] = new JArray(
                "전투에는 퀵슬롯에 등록한 물약만 가져간다 (보유 수와 직업 한도 중 작은 쪽). 퀵슬롯이 비어 있으면 물약 없이 싸운다.",
                "퀵슬롯 등록은 인벤토리 창에서 한다. 물약이 모자라면 상인에게 대화로 상점을 열어 산다.",
                "다른 지역으로 가려면 지역 입구 엔티티에 interact(enter) 한다. 숲 입구는 마을 북쪽 끝에 있다.",
                "진행 중인 퀘스트의 목표는 관찰 quests 또는 퀘스트 창에서 확인한다. 반납만 남은 퀘스트(state=ready)는 marker quest_turn_in 이 붙은 NPC 에게 말을 건다.",
                "전투에서 지면 근처 체크포인트에서 부활하고 적과 퀘스트는 그대로 남는다 — 물약을 채워 다시 도전한다."),
            ["default_goal"] = "튜토리얼 퀘스트를 모두 끝까지 완료하라 (진행 중인 퀘스트가 없어질 때까지).",
        };

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
            var actions = DeclaredActions();   // 0.8.3: description·schema (play 0.3 선택 필드 4.2.1), args 는 그대로
            return new JObject
            {
                ["type"] = PP.Description,
                ["protocol_version"] = PP.ProtocolVersion, ["game"] = _repo.GameName, ["game_version"] = _repo.GameVersion,
                ["classes"] = new JArray(_repo.ClassNames),
                ["bosses"] = bosses,
                ["scenarios"] = scenarios,
                ["actions"] = actions,
                ["pilot_guide"] = PilotGuide(),
                ["progress_keys"] = new JArray("quests", "player.zone", "inventory", "player.gold", "player.quickslots"),
                ["limits"] = new JObject { ["max_action_seconds"] = _data.Limits.MaxActionSeconds, ["interact_range"] = _data.Limits.InteractRange },
                ["observation_modes"] = new JArray("semantic", "hierarchy"),
                ["debug"] = new JObject { ["omniscient"] = _opt.Omniscient },
                ["combat"] = new JObject
                {
                    ["trigger_state_features"] = new JArray(P.TriggerStateFeatures),
                    ["trigger_totals"] = new JArray(P.TriggerTotalsFields),
                    ["encounter_start_state"] = PP.EncounterStartState,
                    ["encounters"] = Encounters(),
                },
                ["quests"] = QuestList(),
                ["pilot_notes"] = new JObject { ["max_chars"] = PP.PilotMaxChars, ["kinds"] = new JArray(PP.PilotKinds) },
                // v0.4 (computer use): raw 입력 모드
                ["input_modes"] = new JArray(PP.InputModes),
                ["screen"] = new JObject { ["width"] = VirtualScreen.W, ["height"] = VirtualScreen.H, ["origin"] = "top_left" },
                ["keys"] = KeyMap.ToWire(),
                ["actions_raw"] = RawActionsWire(),
                ["stage"] = "P3",
            };
        }

        static JArray RawActionsWire() => new JArray
        {
            new JObject { ["name"] = "pointer_click", ["args"] = new JObject { ["x"] = "number", ["y"] = "number", ["button"] = "left|right | null" } },
            new JObject { ["name"] = "pointer_move", ["args"] = new JObject { ["x"] = "number", ["y"] = "number" } },
            new JObject { ["name"] = "drag", ["args"] = new JObject { ["x0"] = "number", ["y0"] = "number", ["x1"] = "number", ["y1"] = "number" } },
            new JObject { ["name"] = "key_press", ["args"] = new JObject { ["key"] = "string (keys)" } },
            new JObject { ["name"] = "key_hold", ["args"] = new JObject { ["key"] = "w|a|s|d", ["seconds"] = "number" } },
            new JObject { ["name"] = "text_input", ["args"] = new JObject { ["text"] = "string" } },
            new JObject { ["name"] = "wait", ["args"] = new JObject { ["seconds"] = "number | null", ["until"] = "event_kind | null" } },
            new JObject { ["name"] = "move_to", ["args"] = new JObject { ["pos"] = "[x,y,z] (raw 모드는 좌표만)" } },
        };

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
            string mode = "semantic";
            foreach (var p in msg.Properties())
            {
                if (p.Name == "input_mode" && V04)
                {
                    mode = p.Value.Type == JTokenType.String ? (string)p.Value : null;
                    if (Array.IndexOf(PP.InputModes, mode) < 0) throw new ProtocolException(P.EBadRequest, "input_mode 는 semantic|raw");
                    continue;
                }
                if (p.Name != "type" && p.Name != "seed" && p.Name != "class")
                    throw new ProtocolException(P.EBadRequest, "reset 인자는 seed·class" + (V04 ? "·input_mode" : "") + " 뿐 (항상 새 게임, 시작 지점 옵션 없음): '" + p.Name + "'");
            }
            _inputMode = mode;

            _runner = null;
            _world = new WorldState(_data, seed, cls);
            _log.Clear();
            var w = _world;
            _world.OnEvent += ev => _log.Add(ev.Time, ev.Kind, ev.Payload);
            var rl = new JObject { ["seed"] = seed, ["class"] = cls, ["omniscient"] = _opt.Omniscient };
            if (V04) rl["input_mode"] = _inputMode;
            _log.Add(0, "reset", rl);
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
            bool raw = _inputMode == "raw";
            if (raw && Array.IndexOf(PP.RawActions, name) < 0)
                throw new ProtocolException(PP.EUnknownAction, "raw 입력 모드에서는 id 기반 행동 '" + name + "' 없음. 지원: " + string.Join(",", PP.RawActions));
            if (raw && name == "move_to" && args["target"] != null && args["target"].Type != JTokenType.Null)
                throw new ProtocolException(P.EBadRequest, "raw 입력 모드의 move_to 는 args.pos 만 (target 없음)");
            IPlayAction a;
            switch (name)
            {
                case "move_to": a = new MoveTo(); break;
                case "interact": a = new Interact(); break;
                case "ui_click": a = new UiClick(_hier); break;
                case "use_item": a = new UseItem(); break;
                case "engage": a = new Engage(); break;
                case "wait": a = new Wait(); break;
                case "pointer_click" when V04: a = new PointerClick(); break;
                case "pointer_move" when V04: a = new PointerMove(); break;
                case "drag" when V04: a = new Drag(); break;
                case "key_press" when V04: a = new KeyPress(); break;
                case "key_hold" when V04: a = new KeyHold(); break;
                case "text_input" when V04: a = new TextInput(); break;
                default:
                    throw new ProtocolException(PP.EUnknownAction, "알 수 없는(또는 이 단계에서 아직 없는) 행동 '" + name + "'. 지원: " + string.Join(",", PP.Actions) +
                                                                   (V04 ? " + raw " + string.Join(",", PP.RawActions) : ""));
            }
            _actSeq = msg["seq"];
            _actName = name;
            _log.Add(_world.Time, "act", new JObject { ["seq"] = _actSeq?.DeepClone(), ["action"] = name, ["args"] = args.DeepClone() });
            var ctx = new ActionContext { World = _world, Perceivable = id => _semantic.EntityPerceivable(id, _world), Scene = _scene };
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
            var hitA = a as IHitAction;
            bool hasHit = hitA != null && hitA.HasHit;
            string hit = hasHit ? hitA.Hit : null;
            if (hasHit) summary["hit"] = hit;
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
                if (hasHit) m["hit"] = hit;
                m["game_seconds"] = Math.Round(r.GameSeconds, 2);
                m["observation"] = _semantic.Build(_world, _obsSeq++);
                return m;
            });
        }

        /// <summary>pilot_note (4.10): 플레이어 생각을 화면에 띄우고 로그에 남긴다. 세계 시간·관찰·난수는 건드리지 않는다.</summary>
        void DoPilotNote(JObject msg)
        {
            RequireReset();
            var kind = msg["kind"]?.Type == JTokenType.String ? (string)msg["kind"] : null;
            if (kind == null || Array.IndexOf(PP.PilotKinds, kind) < 0)
                throw new ProtocolException(P.EBadRequest, "pilot_note kind 는 " + string.Join("|", PP.PilotKinds) + " 중 하나: '" + msg["kind"] + "'");
            var raw = msg["text"]?.Type == JTokenType.String ? (string)msg["text"] : null;
            var text = OneLine(raw);
            if (text.Length == 0) throw new ProtocolException(P.EBadRequest, "pilot_note text 가 비었음 (문자열 필요)");
            if (text.Length > PP.PilotMaxChars) text = text.Substring(0, PP.PilotMaxChars - 1) + "…";
            _log.Add(_world.Time, PP.PilotNote, new JObject { ["kind"] = kind, ["text"] = text });
            _onPilotNote?.Invoke(kind, text);
            var ok = new JObject { ["type"] = PP.PilotNoteOk };
            if (msg["seq"] != null) ok["seq"] = msg["seq"].DeepClone();
            Reply(ok);
        }

        /// <summary>줄바꿈·연속 공백을 공백 하나로 (메모는 한 줄).</summary>
        static string OneLine(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new System.Text.StringBuilder(s.Length);
            bool sp = false;
            foreach (var ch in s)
            {
                if (char.IsWhiteSpace(ch)) { sp = sb.Length > 0; continue; }
                if (sp) { sb.Append(' '); sp = false; }
                sb.Append(ch);
            }
            return sb.ToString();
        }

        void DoGetLog(JObject msg)
        {
            int since = msg["since_seq"]?.Type == JTokenType.Integer ? (int)msg["since_seq"] : 0;
            Reply(new JObject { ["type"] = PP.PlayLog, ["entries"] = _log.Since(since), ["next_seq"] = _log.Count });
        }
    }
}
