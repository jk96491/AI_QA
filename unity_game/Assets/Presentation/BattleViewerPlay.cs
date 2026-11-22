// 플레이 모드 전투 연출: 필드에서 조우하면 화면을 암전 → 아레나(전투 뷰어 무대)로 전환 → 실제 전투를 기존 뷰어 연출로 보여 준다
// → 결과 배너 → 필드로 복귀.
// - 판 진행 주체는 PlaySession 이다. 뷰어는 세션이 넘긴 CombatSim 을 한 틱씩 밟으며(StepOnce) 그리기만 한다.
//   (트리거 응답 대기도 그 Step 안에서 일어난다 — 그동안 화면은 멈춘다)
// - 결과는 밸런스 run_episode 와 같다: 이벤트 기록(RecordEvents)은 result 에 "events" 만 더하고 로직은 바꾸지 않는다 (세션이 빼고 보냄).
// - 플레이 모드에서는 사람의 입력(일시정지·속도·설정 패널)을 받지 않는다.
using System;
using Qa.Data;
using Qa.Play.Perception;
using Qa.Play.Server;
using Qa.Sim;
using UnityEngine;

namespace Qa.Presentation
{
    public sealed partial class BattleViewer : ICombatPresenter
    {
        /// <summary>플레이 모드 창에서 만든 뷰어 (PlayView 가 연출기로 쓴다). 그 외에는 null.</summary>
        public static BattleViewer PlayInstance { get; private set; }

        bool _playMode;            // -qaPlay 로 만든 뷰어
        bool _presenting;          // 전투 연출 중
        enum PlayPhase { Intro, Fight, Outro }
        PlayPhase _phase;
        float _phaseT;
        float _fade;               // 0~1 암전 (IMGUI 오버레이)
        float _fadeOutT = -1f;     // 복귀 후 밝아지는 중
        Action<bool> _setField;
        float _playSpeed = 1f;
        string _bossTitle = "돌의 군주";

        // 아레나 조명 (필드와 공유하는 전역 RenderSettings 를 전투 동안만 바꾼다)
        bool _savedFog;
        Color _savedFogColor, _savedAmbient;
        float _savedFogStart, _savedFogEnd;
        UnityEngine.Rendering.AmbientMode _savedAmbientMode;
        FogMode _savedFogMode;

        public const float IntroSeconds = 0.8f, OutroSeconds = 2.0f, FadeBackSeconds = 0.5f;

        static void CreatePlay()
        {
            var go = new GameObject("BattleViewer(Play)");
            var v = go.AddComponent<BattleViewer>();
            v._playMode = true;
            v._panel = false;
            DontDestroyOnLoad(go);
            PlayInstance = v;
        }

        /// <summary>Start 에서: 무대는 만들어 두되 숨긴다 (필드 화면과 겹치지 않게).</summary>
        void StartPlayMode()
        {
            SaveLighting();
            BuildStage();
            _fx = new FxSystem(_world);
            InitHud();
            ArenaLighting(false);
            _world.gameObject.SetActive(false);
        }

        void SaveLighting()
        {
            _savedFog = RenderSettings.fog;
            _savedFogColor = RenderSettings.fogColor;
            _savedFogMode = RenderSettings.fogMode;
            _savedFogStart = RenderSettings.fogStartDistance;
            _savedFogEnd = RenderSettings.fogEndDistance;
            _savedAmbient = RenderSettings.ambientLight;
            _savedAmbientMode = RenderSettings.ambientMode;
        }

        void ArenaLighting(bool on)
        {
            if (on)
            {
                RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
                RenderSettings.ambientLight = new Color(0.30f, 0.32f, 0.40f);
                RenderSettings.fog = true;
                RenderSettings.fogMode = FogMode.Linear;
                RenderSettings.fogColor = _cam.backgroundColor;
                RenderSettings.fogStartDistance = 45f;
                RenderSettings.fogEndDistance = 120f;
            }
            else
            {
                RenderSettings.fog = _savedFog;
                RenderSettings.fogColor = _savedFogColor;
                RenderSettings.fogMode = _savedFogMode;
                RenderSettings.fogStartDistance = _savedFogStart;
                RenderSettings.fogEndDistance = _savedFogEnd;
                RenderSettings.ambientLight = _savedAmbient;
                RenderSettings.ambientMode = _savedAmbientMode;
            }
        }

        // ------------------------------------------------------------------ ICombatPresenter
        public void Begin(CombatSim sim, string cls, string scenario, long seed, string bossTitle, Action<bool> setFieldVisible)
        {
            if (_world == null) StartPlayMode();
            _setField = setFieldVisible;
            _sim = sim;
            _replay = null;
            _replayMatch = null;
            _simError = null;
            _spec = _repo.Class(cls);
            _scenario = scenario;
            _bossSpec = _repo.BossFor(scenario);
            _seed = seed;
            _bossTitle = bossTitle ?? "보스";
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
            _phase = PlayPhase.Intro;
            _phaseT = 0f;
            _fade = 0f;
            _fadeOutT = -1f;
            _presenting = true;
            LogLine("<b>조우!</b> — " + _spec.DisplayName + " vs " + _bossTitle + ", 시나리오 " + _scenario + ", seed " + seed);
        }

        /// <summary>한 프레임. 판은 Fight 단계에서만 진행한다. 연출까지 끝나면 true.</summary>
        public bool Tick(double realDelta, double speed)
        {
            if (!_presenting) return true;
            float rd = (float)realDelta;
            _playSpeed = (float)speed;
            _phaseT += rd;
            switch (_phase)
            {
                case PlayPhase.Intro:
                    float half = IntroSeconds / 2;
                    if (_phaseT < half) _fade = _phaseT / half;          // 필드가 어두워짐
                    else
                    {
                        if (!_world.gameObject.activeSelf) Show(true);   // 암전 상태에서 장면 전환
                        _fade = Mathf.Clamp01(1f - (_phaseT - half) / half);
                    }
                    if (_phaseT >= IntroSeconds)
                    {
                        _fade = 0f;
                        _phase = PlayPhase.Fight;
                        _phaseT = 0f;
                        ConsumeEvents();   // 판 시작(트리거 0 등) 이벤트
                        Banner("전투 시작!", new Color(1f, 0.85f, 0.4f));
                    }
                    break;
                case PlayPhase.Fight:
                    _acc += rd * (float)speed;
                    int guard = 0;
                    while (_acc >= _cfg.Dt && !_sim.Done && guard++ < 2000)
                    {
                        _acc -= (float)_cfg.Dt;
                        StepOnce();
                    }
                    if (_sim.Done)
                    {
                        OnFinished();
                        bool won = _sim.Cleared;
                        Banner(won ? "승리!" : "패배...", won ? new Color(0.5f, 1f, 0.4f) : new Color(1f, 0.4f, 0.35f));
                        _phase = PlayPhase.Outro;
                        _phaseT = 0f;
                    }
                    break;
                case PlayPhase.Outro:
                    _fade = Mathf.Clamp01((_phaseT - (OutroSeconds - 0.4f)) / 0.4f);   // 마지막에 어두워짐
                    if (_phaseT >= OutroSeconds) return true;
                    break;
            }
            return false;
        }

        public void OnTrigger(int index)
        {
            if (_presenting && _player != null)
                _fx?.Text(HeadPos(_player) + Vector3.up, "결정 트리거 #" + index, new Color(0.6f, 0.85f, 1f), 16, 1.6f);
        }

        /// <summary>연출 종료 (정상·중단 모두). 필드는 즉시 되돌린다 — 응답 직후의 관찰이 필드를 보도록.</summary>
        public void End()
        {
            if (!_presenting) return;
            _presenting = false;
            Show(false);
            _sim = null;
            _fade = 1f;
            _fadeOutT = 0f;   // 필드가 다시 밝아짐
        }

        void Show(bool arena)
        {
            _world.gameObject.SetActive(arena);
            ArenaLighting(arena);
            _setField?.Invoke(!arena);
        }

        /// <summary>Update 에서 (플레이 모드): 판은 세션이 진행하므로 그리기만.</summary>
        void UpdatePlayMode()
        {
            if (_fadeOutT >= 0f)
            {
                _fadeOutT += Time.unscaledDeltaTime;
                _fade = Mathf.Clamp01(1f - _fadeOutT / FadeBackSeconds);
                if (_fadeOutT >= FadeBackSeconds) _fadeOutT = -1f;
            }
            if (!_presenting || _sim == null) return;
            float dt = Time.unscaledDeltaTime;
            float frac = _phase != PlayPhase.Fight || _sim.Done ? 1f : Mathf.Clamp01(_acc / (float)_cfg.Dt);
            float vdt = _phase == PlayPhase.Fight ? dt * Mathf.Clamp(_playSpeed, 1f, 32f) : dt;
            Animate(frac, vdt, dt);
            _fx.Tick(vdt);
            UpdateCamera(dt);
        }

        void OnGUIPlayMode()
        {
            EnsureStyles();
            if (_presenting && _sim != null && _world.gameObject.activeSelf)
            {
                _bannerT += Time.deltaTime;
                DrawFloatTexts();
                DrawBossBar();
                DrawPlayerPanel();
                DrawInfo();
                DrawLog();
                DrawBanner();
                if (_sim.Done) DrawResult();
            }
            if (_fade > 0.001f)
            {
                var old = GUI.color;
                GUI.color = new Color(0, 0, 0, _fade);
                GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), Texture2D.whiteTexture);
                GUI.color = old;
            }
        }
    }
}
