// 전투 뷰어: CombatSim 을 한 틱(0.3초)씩 진행하며 화면에 그린다.
// - 판 로직은 그대로 (같은 seed·params → 학습 서버와 같은 결과). 뷰어는 상태를 읽기만 한다.
// - 로직은 1차원(거리)이라, 틱마다 '플레이어 이동분'과 '보스 이동분'을 나눠 2D 평면 위치로 그린다.
// - 헤드리스(batchmode)에서는 만들지 않는다.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.Boot;
using Qa.Data;
using Qa.Protocol;
using Qa.Sim;
using UnityEngine;

namespace Qa.Presentation
{
    public sealed partial class BattleViewer : MonoBehaviour
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Create()
        {
            if (Application.isBatchMode) return;
            var go = new GameObject("BattleViewer");
            go.AddComponent<BattleViewer>();
            DontDestroyOnLoad(go);
        }

        // ------------------------------------------------------------------ 데이터·판
        SpecRepository _repo;
        string _loadError;
        readonly SimConfig _cfg = new SimConfig();
        CombatSim _sim;
        ClassSpec _spec;
        BossSpec _bossSpec;
        string _scenario = "base";
        long _seed;
        int _evIndex;
        string _simError;

        // 재생 (학습 서버 판)
        EpisodeRecord _replay;          // 재생 중인 기록 (null = 직접 설정한 판)
        bool? _replayMatch;              // 끝난 뒤 서버 결과와 일치?
        long _lastAutoSerial;

        // 진행
        float _speed = 1f;
        bool _paused;
        float _acc;                      // 다음 틱까지 누적 (화면 시간)
        bool _enrageShown;

        // ------------------------------------------------------------------ 화면
        Camera _cam;
        Transform _world;
        ViewerArt.Rig _boss, _player;
        string _playerClass;
        FxSystem _fx;
        GameObject _teleFill, _teleRing, _gimRing, _shield, _aura;
        Material _teleFillMat, _teleRingMat, _gimRingMat, _shieldMat, _auraMat;

        Vector3 _bossFrom, _bossTo, _playerFrom, _playerTo;   // 직전 틱 → 이번 틱 위치 (보간)
        bool _leapArc;
        float _swingT = 99f, _slamT = 99f, _hurtT = 99f, _bossHurtT = 99f;
        float _shake;
        float _camYaw = 35f, _camDist = 24f, _camPitch = 48f;
        Vector3 _camFocus;

        // ------------------------------------------------------------------ 수명
        void Start()
        {
            Application.targetFrameRate = 60;
            Application.runInBackground = true;
            try
            {
                _repo = QaBoot.Repo ?? new SpecRepository(new ResourcesSpecSource("QaData"));
            }
            catch (Exception ex)
            {
                _loadError = ex.Message;
                return;
            }
            BuildStage();
            _fx = new FxSystem(_world);
            InitHud();
            ApplyCommandLine();
            NewBattle(_repo.ClassNames[0], "base", NextSeed(), null);
        }

        static long _seedCounter = (long)(DateTime.Now.Ticks % 100000);
        static long NextSeed() => 1000 + (++_seedCounter * 7919) % 900000;

        void BuildStage()
        {
            _world = new GameObject("World").transform;

            var camGo = new GameObject("ViewerCamera");
            camGo.transform.SetParent(_world, false);
            _cam = camGo.AddComponent<Camera>();
            _cam.clearFlags = CameraClearFlags.SolidColor;
            _cam.backgroundColor = new Color(0.06f, 0.07f, 0.10f);
            _cam.fieldOfView = 45f;
            _cam.farClipPlane = 400f;
            _cam.tag = "MainCamera";

            var lightGo = new GameObject("Sun");
            lightGo.transform.SetParent(_world, false);
            var sun = lightGo.AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = new Color(1f, 0.93f, 0.85f);
            sun.intensity = 1.15f;
            sun.shadows = LightShadows.Soft;
            lightGo.transform.rotation = Quaternion.Euler(52f, -35f, 0f);

            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(0.30f, 0.32f, 0.40f);
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogColor = _cam.backgroundColor;
            RenderSettings.fogStartDistance = 45f;
            RenderSettings.fogEndDistance = 120f;

            // 바닥: 큰 판 + 격자 + 중앙 문양
            var ground = ViewerArt.Prim(PrimitiveType.Plane, _world, Vector3.zero, new Vector3(40, 1, 40), ViewerArt.Lit(new Color(0.16f, 0.17f, 0.19f), 0.05f), null, "Ground");
            ground.GetComponent<Renderer>().receiveShadows = true;
            var grid = ViewerArt.MeshObj("Grid", ViewerArt.Grid(150f, 3f), ViewerArt.Fade(new Color(0.6f, 0.7f, 0.9f, 0.07f)), _world);
            grid.transform.position = Vector3.up * 0.01f;
            for (int i = 1; i <= 4; i++)
            {
                var ring = ViewerArt.MeshObj("ArenaRing", ViewerArt.Ring(0.985f, 128), ViewerArt.Fade(new Color(0.9f, 0.6f, 0.3f, 0.10f)), _world);
                ring.transform.position = Vector3.up * 0.015f;
                ring.transform.localScale = Vector3.one * (6f * i);
            }
            // 이동 경계 표시 (이 안에서만 움직임)
            var edge = ViewerArt.MeshObj("ArenaEdge", ViewerArt.Ring(0.97f, 128), ViewerArt.Fade(new Color(1f, 0.45f, 0.2f, 0.28f)), _world);
            edge.transform.position = Vector3.up * 0.02f;
            edge.transform.localScale = Vector3.one * (ArenaRadius + 1.2f);
            // 주변 기둥 (경계 바깥)
            var pillarMat = ViewerArt.Lit(new Color(0.22f, 0.22f, 0.26f), 0.1f);
            var torchMat = ViewerArt.Glow(new Color(1f, 0.55f, 0.2f), 3f);
            for (int i = 0; i < 12; i++)
            {
                float a = i * Mathf.PI * 2 / 12;
                var p = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a)) * 30f;
                ViewerArt.Prim(PrimitiveType.Cylinder, _world, p + Vector3.up * 3f, new Vector3(1.4f, 3f, 1.4f), pillarMat, null, "Pillar");
                ViewerArt.Prim(PrimitiveType.Sphere, _world, p + Vector3.up * 6.4f, Vector3.one * 0.7f, torchMat, null, "Torch");
            }

            _boss = ViewerArt.BuildBoss();
            _boss.Root.SetParent(_world, false);

            // 바닥 경고 표시 (보스 준비 동작)
            _teleFillMat = ViewerArt.Fade(new Color(1f, 0.15f, 0.1f, 0.35f));
            _teleFill = ViewerArt.MeshObj("TelegraphFill", ViewerArt.Disc(), _teleFillMat, _world);
            _teleRingMat = ViewerArt.Fade(new Color(1f, 0.25f, 0.15f, 0.9f));
            _teleRing = ViewerArt.MeshObj("TelegraphRing", ViewerArt.Ring(0.94f), _teleRingMat, _world);
            _gimRingMat = ViewerArt.Fade(new Color(1f, 0.9f, 0.2f, 0.9f));
            _gimRing = ViewerArt.MeshObj("GimmickRing", ViewerArt.Ring(0.8f), _gimRingMat, _world);
            _auraMat = ViewerArt.Fade(new Color(1f, 0.1f, 0.05f, 0.35f));
            _aura = ViewerArt.MeshObj("EnrageAura", ViewerArt.Ring(0.55f), _auraMat, _world);
            _shieldMat = ViewerArt.Fade(new Color(0.5f, 0.8f, 1f, 0.28f));
            _shield = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            Destroy(_shield.GetComponent<Collider>());
            _shield.GetComponent<Renderer>().sharedMaterial = _shieldMat;
            _shield.transform.SetParent(_world, false);
            _shield.transform.localScale = Vector3.one * 2.6f;
            _teleFill.SetActive(false);
            _teleRing.SetActive(false);
            _gimRing.SetActive(false);
            _aura.SetActive(false);
            _shield.SetActive(false);
        }

        // ------------------------------------------------------------------ 판 시작
        /// <summary>직접 설정한 판 (트리거 없음).</summary>
        void NewBattle(string cls, string scenario, long seed, JObject paramOverrides)
        {
            _replay = null;
            _replayMatch = null;
            StartSim(cls, scenario, seed, paramOverrides, null, null);
        }

        /// <summary>학습 서버가 돌린 판을 같은 seed·params·트리거 응답으로 재현.</summary>
        void ReplayRecord(EpisodeRecord rec)
        {
            var req = rec.Request;
            var cls = (string)req["class"];
            var sc = req["scenario"]?.Type == JTokenType.String ? (string)req["scenario"] : "base";
            if (!_repo.HasClass(cls) || !_repo.HasScenario(sc)) { _simError = "기록된 판의 class/scenario 를 찾을 수 없음"; return; }
            var trig = new List<double>();
            if (req["triggers"] is JObject t && t["boss_hp_below"] is JArray arr)
                foreach (var x in arr) trig.Add(x.Value<double>());
            _replay = rec;
            _replayMatch = null;
            StartSim(cls, sc, req["seed"].Value<long>(), req["params"] as JObject, trig, rec.TriggerParams);
        }

        void StartSim(string cls, string scenario, long seed, JObject paramOverrides, List<double> triggers, List<JObject> triggerParams)
        {
            _simError = null;
            _spec = _repo.Class(cls);
            _scenario = string.IsNullOrEmpty(scenario) ? "base" : scenario;
            _bossSpec = _repo.BossFor(_scenario);
            _seed = seed;
            TriggerHandler handler = null;
            if (triggers != null && triggers.Count > 0)
            {
                var recorded = triggerParams ?? new List<JObject>();
                handler = (index, state, totals) =>
                {
                    _fx?.Text(HeadPos(_player) + Vector3.up, "결정 트리거 #" + index, new Color(0.6f, 0.85f, 1f), 16, 1.6f);
                    return index < recorded.Count ? recorded[index] : null;
                };
            }
            try
            {
                _sim = new CombatSim(_spec, _bossSpec, paramOverrides, seed, new JValue(seed), _cfg.WithRecordEvents(true), triggers, handler);
                CurrentParams = paramOverrides == null ? new JObject() : (JObject)paramOverrides.DeepClone();
                _sim.Begin();
            }
            catch (Exception ex)
            {
                _simError = ex.Message;
                _sim = null;
                return;
            }

            if (_player == null || _playerClass != cls)
            {
                if (_player != null) Destroy(_player.Root.gameObject);
                _player = ViewerArt.BuildPlayer(cls);
                _player.Root.SetParent(_world, false);
                _playerClass = cls;
            }
            _fx.Clear();
            _log.Clear();
            _evIndex = 0;
            _acc = 0f;
            _enrageShown = false;
            _bossTo = _bossFrom = Vector3.zero;
            _playerTo = _playerFrom = new Vector3(0, 0, -(float)_sim.Distance);
            _camFocus = (_bossTo + _playerTo) * 0.5f;
            _player.Body.localRotation = Quaternion.identity;
            ConsumeEvents();
            LogLine("<b>전투 시작</b> — " + _spec.DisplayName + " vs 보스, 시나리오 " + _scenario + ", seed " + seed +
                    (_replay != null ? "  (학습 판 #" + _replay.Serial + " 재생)" : ""));
        }

        // ------------------------------------------------------------------ 진행
        void Update()
        {
            if (_repo == null) return;
            float dt = Time.deltaTime;
            float vdt = _paused ? 0f : dt * _speed;   // 화면 시간

            if (_sim != null && !_sim.Done && !_paused)
            {
                _acc += vdt;
                int guard = 0;
                while (_acc >= _cfg.Dt && !_sim.Done && guard++ < 400)
                {
                    _acc -= (float)_cfg.Dt;
                    StepOnce();
                }
                if (_sim.Done) OnFinished();
            }
            AutoFollow();

            float frac = _sim == null || _sim.Done ? 1f : Mathf.Clamp01(_acc / (float)_cfg.Dt);
            Animate(frac, vdt, dt);
            _fx.Tick(vdt);
            UpdateCamera(dt);
        }

        void StepOnce()
        {
            var u = _playerTo - _bossTo;
            u.y = 0;
            u = u.sqrMagnitude < 1e-4f ? Vector3.back : u.normalized;
            var p = _sim.PlayerState;
            // 보기 좋게 보스 주위를 천천히 돈다 (원거리는 더 많이)
            if (!p.Dead)
            {
                float omega = (_spec.Ranged ? 9f : 3f) * (float)_cfg.Dt;
                u = Quaternion.Euler(0, omega, 0) * u;
            }

            _sim.Step();

            float d1 = (float)_sim.DistanceAfterPlayer;
            float d2 = (float)_sim.Distance;
            _playerFrom = _playerTo;
            _bossFrom = _bossTo;
            u = KeepInsideDirection(_bossTo, u, d1);   // 경계에 닿으면 벽을 따라 돌기
            _playerTo = _bossTo + u * d1;          // 플레이어 이동 (보스 고정)
            _bossTo = _playerTo - u * d2;          // 보스 이동 (플레이어 쪽으로)
            KeepInsidePair(ref _bossTo, ref _playerTo);
            _leapArc = false;
            ConsumeEvents();
        }

        // ------------------------------------------------------------------ 맵 경계 (화면 전용, 로직은 거리만 다룸)
        /// <summary>둘 다 이 반지름 안에서만 움직인다 (기둥 원 30m, 보스 몸집 여유).</summary>
        const float ArenaRadius = 27f;

        static float Flat(Vector3 v) => new Vector2(v.x, v.z).magnitude;

        /// <summary>boss + u·d 가 경계 밖이면, 보스 기준으로 u 를 돌려 경계 안쪽 방향을 찾는다 (가장 적게 도는 쪽).</summary>
        static Vector3 KeepInsideDirection(Vector3 boss, Vector3 u, float d)
        {
            if (Flat(boss + u * d) <= ArenaRadius) return u;
            for (float ang = 4f; ang <= 180f; ang += 4f)
            {
                var a = Quaternion.Euler(0, ang, 0) * u;
                var b = Quaternion.Euler(0, -ang, 0) * u;
                bool okA = Flat(boss + a * d) <= ArenaRadius, okB = Flat(boss + b * d) <= ArenaRadius;
                if (okA && okB) return Flat(boss + a * d) <= Flat(boss + b * d) ? a : b;
                if (okA) return a;
                if (okB) return b;
            }
            // 어느 방향도 안 되면 (거리가 너무 큼) 중심 쪽을 향하고, 남는 건 KeepInsidePair 가 밀어 넣는다
            var toCenter = -new Vector3(boss.x, 0, boss.z);
            return toCenter.sqrMagnitude > 1e-4f ? toCenter.normalized : u;
        }

        /// <summary>그래도 밖에 있는 쪽이 있으면 둘을 같이 안쪽으로 평행 이동 (서로의 거리는 그대로).</summary>
        static void KeepInsidePair(ref Vector3 boss, ref Vector3 player)
        {
            for (int k = 0; k < 3; k++)
            {
                var worst = Flat(boss) >= Flat(player) ? boss : player;
                float over = Flat(worst) - ArenaRadius;
                if (over <= 0f) return;
                var shift = -new Vector3(worst.x, 0, worst.z).normalized * over;
                boss += shift;
                player += shift;
            }
        }

        void OnFinished()
        {
            if (_replay != null && _replayMatch == null)
                _replayMatch = JToken.DeepEquals(Strip(_sim.Result()), Strip(_replay.Result));
            var r = _sim.Result();
            LogLine((bool)r["cleared"]
                ? "<color=#7CFC00><b>클리어!</b></color> " + ((double)r["clear_time"]).ToString("0.0") + "초"
                : "<color=#FF6060><b>실패</b></color> " + (r["stalled"].Value<bool>() ? "(멈춤: " + r["stall_reason"] + ")" : "보스 체력 " + (r["boss_hp_remaining"].Value<double>() * 100).ToString("0") + "% 남음"));
        }

        static JObject Strip(JObject r)
        {
            var c = (JObject)r.DeepClone();
            c.Remove("events");
            return c;
        }

        void AutoFollow()
        {
            if (!_autoFollow || QaBoot.Recorder == null) return;
            var last = QaBoot.Recorder.Last;
            if (last == null || last.Serial == _lastAutoSerial) return;
            if (_sim != null && !_sim.Done && _replay != null) return;   // 재생 중이면 끝날 때까지
            _lastAutoSerial = last.Serial;
            ReplayRecord(last);
        }

        // ------------------------------------------------------------------ 이벤트 → 효과
        void ConsumeEvents()
        {
            var ev = _sim.Events;
            for (; _evIndex < ev.Count; _evIndex++)
            {
                var e = (JArray)ev[_evIndex];
                var kind = (string)e[1];
                var pl = (JObject)e[2];
                OnEvent(kind, pl);
            }
        }

        Vector3 BossChest() => _boss.Root.position + Vector3.up * 2.6f;
        static Vector3 HeadPos(ViewerArt.Rig r) => r == null ? Vector3.zero : r.Root.position + Vector3.up * (r.Height + 0.4f);

        void OnEvent(string kind, JObject pl)
        {
            switch (kind)
            {
                case "skill":
                {
                    var name = (string)pl["name"];
                    var sd = _spec.Skill(name);
                    if (sd.Role != SkillRole.Basic) _fx.Text(HeadPos(_player), Names.Skill(name), new Color(0.75f, 0.9f, 1f), 15, 1.0f);
                    SkillStartFx(sd);
                    LogSkill(name, (string)pl["block"]);
                    break;
                }
                case "dmg":
                {
                    var name = (string)pl["skill"];
                    var sd = _spec.Skill(name);
                    float dmg = pl["dmg"].Value<float>();
                    bool crit = pl["crit"].Value<bool>();
                    Action land = () =>
                    {
                        _bossHurtT = 0f;
                        _fx.Text(HeadPos(_boss) + UnityEngine.Random.insideUnitSphere * 0.6f, (crit ? "치명! " : "") + dmg.ToString("0"),
                                 crit ? new Color(1f, 0.85f, 0.2f) : new Color(1f, 1f, 1f), crit ? 24 : 17, 1.0f);
                        if (crit) _fx.Burst(BossHitPoint(), new Color(1f, 0.85f, 0.3f, 0.8f), 1.8f, 0.25f);
                    };
                    SkillHitFx(sd, crit, land);
                    break;
                }
                case "potion":
                    _fx.Pillar(_player.Root.position, new Color(0.3f, 1f, 0.4f, 0.5f), 3.5f, 1.4f, 0.8f);
                    _fx.Text(HeadPos(_player), "+" + pl["healed"].Value<float>().ToString("0") + " 물약", new Color(0.4f, 1f, 0.5f), 18, 1.2f);
                    LogLine("<color=#80FF90>물약</color> +" + pl["healed"].Value<float>().ToString("0"));
                    break;
                case "gimmick_ok":
                    _fx.Burst(_player.Root.position + Vector3.up, new Color(1f, 0.95f, 0.3f, 0.7f), 3f, 0.4f);
                    _fx.Text(HeadPos(_player), "기믹 대응!", new Color(1f, 0.95f, 0.3f), 20, 1.2f);
                    LogLine("<color=#FFE060>기믹 대응 성공</color>");
                    break;
                case "phase":
                {
                    int phase = _sim.BossState.Phase + 1;
                    Banner("페이즈 " + phase, new Color(1f, 0.6f, 0.25f));
                    _fx.Shockwave(_boss.Root.position, 1f, 12f, new Color(1f, 0.5f, 0.2f, 0.7f), 1.0f);
                    LogLine("<color=#FFA050><b>페이즈 " + phase + "</b></color> (보스 체력 " + (pl["threshold"].Value<float>() * 100).ToString("0") + "% 돌파)");
                    break;
                }
                case "boss":
                {
                    var move = (string)pl["move"];
                    if (move == "aoe" || move == "gimmick") break;   // 효과는 피격/경고에서
                    _fx.Text(HeadPos(_boss) + Vector3.up * 0.6f, Names.BossMove(move) + "!", new Color(1f, 0.45f, 0.35f), 20, 1.2f);
                    LogLine("<color=#FF7060>보스: " + Names.BossMove(move) + "</color> 준비");
                    break;
                }
                case "hit":
                {
                    var k = (string)pl["kind"];
                    float dmg = pl["dmg"].Value<float>();
                    var pp = _player.Root.position;
                    switch (k)
                    {
                        case "aoe":
                            _fx.Shockwave(_boss.Root.position, 1f, 26f, new Color(1f, 0.35f, 0.15f, 0.8f), 0.9f, 0.9f);
                            _slamT = 0f; _shake = 0.25f;
                            break;
                        case "cleave":
                            _fx.Shockwave(_boss.Root.position + (pp - _boss.Root.position).normalized * 1.5f, 0.5f, 4.5f, new Color(1f, 0.25f, 0.1f, 0.9f), 0.45f, 0.6f);
                            _slamT = 0f; _shake = 0.45f;
                            break;
                        case "leap":
                            _fx.Shockwave(_boss.Root.position, 0.5f, 6f, new Color(0.8f, 0.7f, 0.5f, 0.9f), 0.6f, 0.6f);
                            _slamT = 0f; _shake = 0.6f; _leapArc = true;
                            break;
                        case "execute":
                            _fx.Burst(pp + Vector3.up, new Color(0.6f, 0f, 0f, 0.9f), 4f, 0.5f);
                            _slamT = 0f; _shake = 0.8f;
                            break;
                        case "gimmick":
                            _fx.Burst(pp + Vector3.up, new Color(0.7f, 0.2f, 1f, 0.85f), 5f, 0.6f);
                            _fx.Text(HeadPos(_player) + Vector3.up * 0.5f, "기믹 실패", new Color(0.85f, 0.5f, 1f), 20, 1.4f);
                            _shake = 0.6f;
                            break;
                        case "throw":
                            _fx.Burst(pp + Vector3.up, new Color(0.7f, 0.6f, 0.5f, 0.8f), 1.8f, 0.3f);
                            break;
                        default:   // auto
                            _slamT = 0f;
                            _fx.Burst(pp + Vector3.up * 1.2f, new Color(1f, 0.3f, 0.2f, 0.6f), 1.2f, 0.25f);
                            break;
                    }
                    if (dmg <= 0.05f) _fx.Text(HeadPos(_player), "회피", new Color(0.7f, 1f, 0.7f), 16, 0.9f);
                    else
                    {
                        _hurtT = 0f;
                        _fx.Text(HeadPos(_player) + UnityEngine.Random.insideUnitSphere * 0.4f, "-" + dmg.ToString("0"),
                                 new Color(1f, 0.35f, 0.3f), k == "auto" ? 15 : 20, 1.0f);
                    }
                    if (k != "auto") LogLine("<color=#FF8070>" + Names.BossMove(k) + "</color> 피격 " + (dmg <= 0.05f ? "(회피)" : "-" + dmg.ToString("0")));
                    break;
                }
                case "death":
                    _fx.Text(HeadPos(_player), "사망 " + pl["count"] + "/" + (_cfg.MaxDeaths + 1), new Color(1f, 0.2f, 0.2f), 24, 2f);
                    LogLine("<color=#FF4040><b>사망</b></color> " + pl["count"] + "회");
                    break;
                case "revive":
                    _playerFrom = _playerTo;   // 순간이동
                    _fx.Pillar(_playerTo, new Color(1f, 0.95f, 0.7f, 0.6f), 6f, 1.8f, 1.2f);
                    LogLine("부활");
                    break;
                case "trigger":
                    LogLine("<color=#90D0FF>결정 트리거 #" + pl["index"] + "</color> (파라미터 갱신)");
                    break;
            }
        }

        // ------------------------------------------------------------------ 애니메이션 (화면 전용)
        void Animate(float frac, float vdt, float dt)
        {
            if (_sim == null) return;
            var p = _sim.PlayerState;
            var b = _sim.BossState;
            float time = Time.time;

            // 위치 보간
            var bossPos = Vector3.Lerp(_bossFrom, _bossTo, frac);
            if (_leapArc) bossPos.y = Mathf.Sin(frac * Mathf.PI) * 5f;
            var playerPos = Vector3.Lerp(_playerFrom, _playerTo, frac);
            _boss.Root.position = bossPos;
            _player.Root.position = playerPos;

            // 서로 바라보기
            var toP = playerPos - bossPos; toP.y = 0;
            if (toP.sqrMagnitude > 1e-4f)
            {
                _boss.Root.rotation = Quaternion.Slerp(_boss.Root.rotation, Quaternion.LookRotation(toP), 1f - Mathf.Exp(-8f * dt));
                _player.Root.rotation = Quaternion.Slerp(_player.Root.rotation, Quaternion.LookRotation(-toP), 1f - Mathf.Exp(-12f * dt));
            }

            _swingT += vdt; _slamT += vdt; _hurtT += vdt; _bossHurtT += vdt;

            // ----- 플레이어 -----
            bool dead = p.Dead;
            var targetBody = dead ? Quaternion.Euler(-85f, 0, 0) : Quaternion.identity;
            _player.Body.localRotation = Quaternion.Slerp(_player.Body.localRotation, targetBody, 1f - Mathf.Exp(-10f * dt));
            _player.Body.localPosition = new Vector3(0, dead ? 0.3f : Mathf.Abs(Mathf.Sin(time * 3f)) * 0.06f, 0);
            bool casting = p.Casting != null;
            float castLift = casting ? 1f : 0f;
            float moveSpeed = frac < 1f ? Vector3.Distance(_playerFrom, _playerTo) / (float)_cfg.Dt : 0f;
            AnimateClass(vdt, dt, time, dead, casting, moveSpeed);
            if (_player.TipGlow != null)
                ViewerArt.SetEmission(_player.TipGlow.sharedMaterial, new Color(0.75f, 0.45f, 1f) * (2f + castLift * (3f + Mathf.Sin(time * 20f) * 2f)));
            float hurt = _hurtT < 0.15f ? 1f - _hurtT / 0.15f : 0f;
            _player.Body.localScale = Vector3.one * (1f + hurt * 0.08f);

            // 보호막·회피
            bool shielded = p.Shield > 0 && !dead;
            _shield.SetActive(shielded);
            if (shielded)
            {
                _shield.transform.position = playerPos + Vector3.up * 1.1f;
                var sc = _playerClass == "mage" ? new Color(0.8f, 0.5f, 1f, 0.25f) : new Color(0.5f, 0.8f, 1f, 0.28f);
                sc.a *= 0.8f + Mathf.Sin(time * 6f) * 0.2f;
                _shieldMat.color = sc;
            }
            bool evading = p.EvadeTime > 0 && !dead;
            foreach (var r in _player.Root.GetComponentsInChildren<Renderer>()) r.enabled = !evading || Mathf.Repeat(time * 12f, 1f) > 0.35f;

            // 기믹 경고 (플레이어 발밑 노란 고리)
            bool gim = b.GimmickWarning;
            _gimRing.SetActive(gim);
            if (gim)
            {
                float k = (float)(b.GimmickLeft / Math.Max(0.01, _bossSpec.GimmickWindow));
                _gimRing.transform.position = playerPos + Vector3.up * 0.05f;
                _gimRing.transform.localScale = Vector3.one * (1.2f + k * 1.8f);
                _gimRingMat.color = new Color(1f, 0.9f, 0.2f, 0.6f + Mathf.Sin(time * 25f) * 0.35f);
            }

            // ----- 보스 -----
            float windProg = 0f;
            if (b.Winding)
            {
                double total = WindupTotal(b.PendingKind);
                windProg = total <= 0 ? 1f : Mathf.Clamp01(1f - (float)((b.WindupLeft - frac * _cfg.Dt) / total));
            }
            float slam = _slamT < 0.35f ? Mathf.Sin(_slamT / 0.35f * Mathf.PI) : 0f;
            float raise = b.Winding ? windProg : 0f;
            _boss.ArmL.localRotation = Quaternion.Euler(-raise * 150f + slam * 40f, 0, -10f - raise * 20f);
            _boss.ArmR.localRotation = Quaternion.Euler(-raise * 150f + slam * 40f, 0, 10f + raise * 20f);
            _boss.Body.localPosition = new Vector3(0, Mathf.Sin(time * 1.6f) * 0.08f - slam * 0.25f, 0);
            _boss.Body.localRotation = Quaternion.Euler(raise * -12f + slam * 18f, 0, 0);
            float bossHurt = _bossHurtT < 0.12f ? 1f - _bossHurtT / 0.12f : 0f;
            float phaseScale = 1f + b.Phase * 0.06f;
            _boss.Root.localScale = Vector3.one * phaseScale * (1f + bossHurt * 0.03f);
            Color eye = PhaseColor(b.Phase, b.Enraged);
            float eyeI = 3f + raise * 6f + (b.Enraged ? Mathf.Sin(time * 8f) * 2f + 2f : 0f);
            foreach (var r in _boss.Eyes) ViewerArt.SetEmission(r.sharedMaterial, eye * eyeI);
            var skin = Color.Lerp(new Color(0.30f, 0.28f, 0.33f), new Color(0.45f, 0.18f, 0.16f), b.Phase / 3f);
            if (bossHurt > 0) skin = Color.Lerp(skin, Color.white, bossHurt * 0.6f);
            foreach (var r in _boss.Skin) r.sharedMaterial.color = skin;

            // 준비 동작 경고 (바닥)
            bool tele = b.Winding && (b.PendingKind == BossAttackKind.Cleave || b.PendingKind == BossAttackKind.Execute || b.PendingKind == BossAttackKind.Leap || b.PendingKind == BossAttackKind.Throw);
            _teleFill.SetActive(tele);
            _teleRing.SetActive(tele);
            if (tele)
            {
                Vector3 c; float r;
                Color col = new Color(1f, 0.15f, 0.1f);
                switch (b.PendingKind)
                {
                    case BossAttackKind.Leap: c = playerPos; r = 2.2f; col = new Color(1f, 0.6f, 0.2f); break;
                    case BossAttackKind.Throw: c = playerPos; r = 1.5f; col = new Color(0.9f, 0.7f, 0.4f); break;
                    case BossAttackKind.Execute: c = bossPos; r = (float)(_bossSpec.Reach + 0.5) * phaseScale; col = new Color(0.7f, 0f, 0.05f); break;
                    default: c = bossPos; r = (float)(_bossSpec.Reach + _bossSpec.CleaveRangeBonus) * phaseScale; break;
                }
                c.y = 0.04f;
                _teleRing.transform.position = c;
                _teleRing.transform.localScale = Vector3.one * r;
                _teleRingMat.color = new Color(col.r, col.g, col.b, 0.9f);
                _teleFill.transform.position = c + Vector3.up * 0.005f;
                _teleFill.transform.localScale = Vector3.one * r * Mathf.Max(0.05f, windProg);
                _teleFillMat.color = new Color(col.r, col.g, col.b, 0.35f + windProg * 0.25f);
            }

            // 격노
            _aura.SetActive(b.Enraged);
            if (b.Enraged)
            {
                if (!_enrageShown) { _enrageShown = true; Banner("격노!", new Color(1f, 0.2f, 0.15f)); LogLine("<color=#FF3030><b>보스 격노</b></color> — 모든 피해 증가"); }
                _aura.transform.position = new Vector3(bossPos.x, 0.03f, bossPos.z);
                _aura.transform.localScale = Vector3.one * (4.5f + Mathf.Sin(time * 5f) * 0.4f);
                _aura.transform.Rotate(0, 40f * dt, 0);
            }
        }

        double WindupTotal(BossAttackKind k)
        {
            switch (k)
            {
                case BossAttackKind.Cleave: return _bossSpec.CleaveWindup;
                case BossAttackKind.Leap: return _bossSpec.LeapWindup;
                case BossAttackKind.Execute: return _bossSpec.ExecuteWindup;
                case BossAttackKind.Throw: return _bossSpec.ThrowWindup;
                default: return 1.0;
            }
        }

        static Color PhaseColor(int phase, bool enraged)
        {
            if (enraged) return new Color(1f, 0.1f, 0.05f);
            switch (phase)
            {
                case 0: return new Color(1f, 0.6f, 0.15f);
                case 1: return new Color(1f, 0.45f, 0.1f);
                case 2: return new Color(1f, 0.3f, 0.08f);
                default: return new Color(1f, 0.15f, 0.08f);
            }
        }

        void UpdateCamera(float dt)
        {
            if (_cam == null || _boss == null || _player == null) return;
            var focus = (_boss.Root.position * 0.45f + _player.Root.position * 0.55f);
            focus.y = 1.5f;
            _camFocus = Vector3.Lerp(_camFocus, focus, 1f - Mathf.Exp(-4f * dt));
            float sep = Vector3.Distance(_boss.Root.position, _player.Root.position);
            float dist = _camDist + sep * 0.6f;
            var rot = Quaternion.Euler(_camPitch, _camYaw, 0);
            var pos = _camFocus + rot * new Vector3(0, 0, -dist);
            if (_shake > 0)
            {
                pos += UnityEngine.Random.insideUnitSphere * _shake * 0.35f;
                _shake = Mathf.Max(0, _shake - dt * 2.5f);
            }
            _cam.transform.SetPositionAndRotation(pos, rot);
        }
    }

    /// <summary>화면 표시용 한글 이름.</summary>
    public static class Names
    {
        public static string Skill(string s)
        {
            switch (s)
            {
                case "basic_attack": return "평타";
                case "strike": return "강타";
                case "charge": return "돌진";
                case "shield_block": return "방패 막기";
                case "bladestorm": return "칼날폭풍";
                case "magic_bolt": return "마력탄";
                case "fireball": return "화염구";
                case "barrier": return "보호막";
                case "blink": return "점멸";
                case "meteor": return "메테오";
                case "basic_shot": return "기본 사격";
                case "aimed_shot": return "조준 사격";
                case "evade": return "회피";
                case "rapid_fire": return "속사";
                default: return s;
            }
        }

        public static string Block(string b)
        {
            switch (b)
            {
                case "burst": return "버스트";
                case "dps": return "딜 유지";
                case "survival": return "생존";
                case "gimmick": return "기믹 대응";
                case "approach": return "접근";
                case "dead": return "사망";
                default: return b;
            }
        }

        public static string BossMove(string m)
        {
            switch (m)
            {
                case "cleave": return "내려찍기";
                case "leap": return "도약";
                case "execute": return "처형";
                case "aoe": return "광역 충격";
                case "gimmick": return "기믹";
                case "throw": return "투척";
                case "auto": return "평타";
                default: return m;
            }
        }
    }
}
