// 전투 뷰어 HUD (IMGUI): 체력바·시전바·BT 블록·전투 기록·설정 패널·결과.
// 입력은 IMGUI 이벤트만 쓴다 (프로젝트의 Input 설정과 무관하게 동작).
using System;
using System.Collections.Generic;
using System.Globalization;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Qa.Boot;
using Qa.Data;
using Qa.Sim;
using UnityEngine;

namespace Qa.Presentation
{
    public sealed partial class BattleViewer
    {
        public JObject CurrentParams { get; private set; }

        readonly List<string> _log = new List<string>();
        string _bannerText;
        Color _bannerColor;
        float _bannerT = 99f;

        bool _panel = true;
        bool _showParams;
        bool _autoFollow;
        int _uiClass, _uiScenario;
        string _uiSeed = "";
        string _uiJson = "";
        string _uiJsonMsg;
        Vector2 _panelScroll;
        readonly Dictionary<string, Dictionary<string, float>> _edits = new Dictionary<string, Dictionary<string, float>>();
        static readonly float[] Speeds = { 0.5f, 1f, 2f, 4f, 8f, 16f };

        Texture2D _white;
        GUIStyle _label, _small, _big, _box, _rich, _center, _button, _shadow;
        bool _stylesReady;
        Rect _panelRect;

        void InitHud()
        {
            _white = Texture2D.whiteTexture;
            _uiClass = 0;
            _uiScenario = 0;
        }

        /// <summary>
        /// 창 모드 시작 설정 (VIEWER_REQUEST.md, 학습 쪽 --view 용). 판 로직과 무관.
        ///   -qaFollow          학습 판 자동 따라보기 켜기
        ///   -qaViewSpeed x     재생 속도 (0.5/1/2/4/8/16 중 가장 가까운 값)
        ///   -qaPanel 0         설정 패널 접기
        /// </summary>
        void ApplyCommandLine()
        {
            var args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length; i++)
            {
                var a = args[i];
                string next = i + 1 < args.Length ? args[i + 1] : null;
                if (a.Equals("-qaFollow", StringComparison.OrdinalIgnoreCase))
                {
                    _autoFollow = true;
                }
                else if (a.Equals("-qaViewSpeed", StringComparison.OrdinalIgnoreCase) && next != null &&
                         float.TryParse(next, NumberStyles.Float, CultureInfo.InvariantCulture, out var sp) && sp > 0)
                {
                    float best = Speeds[0];
                    foreach (var s in Speeds)
                        if (Mathf.Abs(Mathf.Log(s / sp)) < Mathf.Abs(Mathf.Log(best / sp))) best = s;
                    _speed = best;
                }
                else if (a.Equals("-qaPanel", StringComparison.OrdinalIgnoreCase) && next != null)
                {
                    _panel = next.Trim() != "0";
                }
            }
        }

        void LogLine(string s)
        {
            string t = _sim != null ? FormatTime(_sim.Time) : "0:00";
            _log.Add("<color=#8090A0>" + t + "</color>  " + s);
            if (_log.Count > 9) _log.RemoveAt(0);
        }

        string _lastSkillLogged;
        void LogSkill(string skill, string block)
        {
            var sd = _spec.Skill(skill);
            if (sd.Role == SkillRole.Basic) return;   // 평타는 기록하지 않음
            var key = skill + block;
            _lastSkillLogged = key;
            LogLine("<color=#A0D0FF>" + Names.Skill(skill) + "</color>  <color=#708090>[" + Names.Block(block) + "]</color>");
        }

        void Banner(string text, Color c)
        {
            _bannerText = text;
            _bannerColor = c;
            _bannerT = 0f;
        }

        static string FormatTime(double t)
        {
            int s = (int)t;
            return (s / 60) + ":" + (s % 60).ToString("00");
        }

        void EnsureStyles()
        {
            if (_stylesReady) return;
            _stylesReady = true;
            _label = new GUIStyle(GUI.skin.label) { fontSize = 14, richText = true };
            _label.normal.textColor = new Color(0.92f, 0.94f, 0.97f);
            _small = new GUIStyle(_label) { fontSize = 12 };
            _rich = new GUIStyle(_label) { fontSize = 13, wordWrap = true };
            _big = new GUIStyle(_label) { fontSize = 34, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
            _center = new GUIStyle(_label) { alignment = TextAnchor.MiddleCenter };
            _shadow = new GUIStyle(_label) { alignment = TextAnchor.MiddleCenter, fontStyle = FontStyle.Bold };
            _box = new GUIStyle(GUI.skin.box);
            _box.normal.background = MakeTex(new Color(0.05f, 0.06f, 0.09f, 0.82f));
            _button = new GUIStyle(GUI.skin.button) { fontSize = 13, richText = true };
        }

        static Texture2D MakeTex(Color c)
        {
            var t = new Texture2D(1, 1) { hideFlags = HideFlags.HideAndDontSave };
            t.SetPixel(0, 0, c);
            t.Apply();
            return t;
        }

        void Fill(Rect r, Color c)
        {
            var old = GUI.color;
            GUI.color = c;
            GUI.DrawTexture(r, _white);
            GUI.color = old;
        }

        void Bar(Rect r, float v, Color fill, Color back, string text = null)
        {
            Fill(r, back);
            Fill(new Rect(r.x, r.y, r.width * Mathf.Clamp01(v), r.height), fill);
            if (text != null) GUI.Label(r, text, _center);
        }

        void Shadowed(Rect r, string text, GUIStyle st, Color c)
        {
            var old = st.normal.textColor;
            st.normal.textColor = new Color(0, 0, 0, c.a * 0.8f);
            GUI.Label(new Rect(r.x + 2, r.y + 2, r.width, r.height), text, st);
            st.normal.textColor = c;
            GUI.Label(r, text, st);
            st.normal.textColor = old;
        }

        // ------------------------------------------------------------------ 그리기
        void OnGUI()
        {
            if (_playMode)
            {
                if (_repo != null && _world != null) OnGUIPlayMode();   // 입력·설정 패널 없음
                return;
            }
            EnsureStyles();
            if (_repo == null)
            {
                GUI.Label(new Rect(20, 20, 800, 60), "게임 데이터 로드 실패: " + _loadError, _label);
                return;
            }
            HandleInput();
            _bannerT += Time.deltaTime;

            DrawFloatTexts();
            if (_sim != null)
            {
                DrawBossBar();
                DrawPlayerPanel();
                DrawInfo();
                DrawLog();
                DrawBanner();
                if (_sim.Done) DrawResult();
            }
            if (_panel) DrawPanel();
            else if (GUI.Button(new Rect(Screen.width - 110, 10, 100, 28), "설정 ▸ (Tab)", _button)) _panel = true;
        }

        void DrawFloatTexts()
        {
            if (_cam == null) return;
            foreach (var t in _fx.Texts)
            {
                float k = t.Age / t.Life;
                var w = t.World + Vector3.up * (t.Rise * k);
                var sp = _cam.WorldToScreenPoint(w);
                if (sp.z < 0) continue;
                var st = new GUIStyle(_shadow) { fontSize = t.Size };
                var c = t.Color;
                c.a = k < 0.7f ? 1f : 1f - (k - 0.7f) / 0.3f;
                var r = new Rect(sp.x - 120, Screen.height - sp.y - 15, 240, 30);
                Shadowed(r, t.Text, st, c);
            }
        }

        void DrawBossBar()
        {
            var b = _sim.BossState;
            float w = Mathf.Min(640, Screen.width - 420), x = (Screen.width - w) / 2 - (_panel ? 150 : 0), y = 16;
            GUI.Box(new Rect(x - 10, y - 6, w + 20, b.Winding ? 78 : 58), GUIContent.none, _box);
            string title = "<b>" + _bossTitle + "</b>  <color=#FFB070>페이즈 " + (b.Phase + 1) + "</color>" + (b.Enraged ? "  <color=#FF4040><b>격노</b></color>" : "") +
                           (_scenario != "base" ? "  <color=#90A0B0>[" + _scenario + "]</color>" : "");
            GUI.Label(new Rect(x, y - 2, w, 20), title, _label);
            var hpRect = new Rect(x, y + 20, w, 18);
            Color hpc = Color.Lerp(new Color(0.85f, 0.25f, 0.2f), new Color(0.95f, 0.1f, 0.1f), b.Phase / 3f);
            Bar(hpRect, (float)b.HpRatio, hpc, new Color(0.15f, 0.05f, 0.05f, 0.9f),
                ((int)Math.Ceiling(b.Hp)).ToString("N0") + " / " + b.Spec.MaxHp.ToString("N0") + "  (" + (b.HpRatio * 100).ToString("0.0") + "%)");
            foreach (var th in b.Spec.PhaseThresholds)
                Fill(new Rect(x + w * (float)th - 1, y + 18, 2, 22), new Color(1f, 0.85f, 0.4f, 0.9f));
            if (b.Winding)
            {
                double total = WindupTotal(b.PendingKind);
                float prog = total <= 0 ? 1f : 1f - (float)(b.WindupLeft / total);
                Bar(new Rect(x + w * 0.25f, y + 44, w * 0.5f, 14), prog, new Color(1f, 0.35f, 0.2f), new Color(0.1f, 0.1f, 0.1f, 0.9f),
                    Names.BossMove(KindName(b.PendingKind)) + " 준비 중");
            }
        }

        static string KindName(BossAttackKind k) => new BossAttack { Kind = k }.KindName;

        void DrawPlayerPanel()
        {
            var p = _sim.PlayerState;
            float w = 460, h = 112, x = (Screen.width - w) / 2 - (_panel ? 150 : 0), y = Screen.height - h - 14;
            GUI.Box(new Rect(x, y, w, h), GUIContent.none, _box);
            var cc = ViewerArt.ClassColor(_playerClass);
            string hex = ColorUtility.ToHtmlStringRGB(cc);
            string block = _sim.CurrentBlock;
            GUI.Label(new Rect(x + 12, y + 6, w - 24, 20),
                "<b><color=#" + hex + ">" + _spec.DisplayName + "</color></b>   BT 블록: <b>" + BlockTag(p.Dead ? "dead" : block) + "</b>", _label);
            Bar(new Rect(x + 12, y + 30, w - 24, 18), (float)p.HpRatio, new Color(0.25f, 0.8f, 0.35f), new Color(0.05f, 0.15f, 0.05f, 0.9f),
                p.Dead ? "사망 — 부활까지 " + Math.Max(0, p.ReviveTimer).ToString("0.0") + "초" : ((int)Math.Ceiling(p.Hp)) + " / " + (int)p.MaxHp);
            string resName = _playerClass == "warrior" ? "분노" : _playerClass == "mage" ? "마나" : "집중";
            Color resC = _playerClass == "warrior" ? new Color(0.9f, 0.3f, 0.2f) : _playerClass == "mage" ? new Color(0.3f, 0.5f, 1f) : new Color(1f, 0.8f, 0.3f);
            Bar(new Rect(x + 12, y + 52, w - 24, 12), (float)p.ResourceRatio, resC, new Color(0.08f, 0.08f, 0.1f, 0.9f));
            GUI.Label(new Rect(x + 14, y + 49, 200, 16), resName + " " + (int)p.Resource, _small);
            if (p.Casting != null)
            {
                float prog = 1f - (float)(p.CastRemaining / Math.Max(0.01, p.Casting.CastTime));
                Bar(new Rect(x + 12, y + 68, w - 24, 14), prog, new Color(0.9f, 0.85f, 0.5f), new Color(0.1f, 0.1f, 0.1f, 0.9f), Names.Skill(p.Casting.Name) + " 시전");
            }
            string pots = new string('●', p.Potions) + new string('○', Math.Max(0, _spec.Stats.Potions - p.Potions));
            GUI.Label(new Rect(x + 12, y + 86, w - 24, 20),
                "물약 <color=#80FF90>" + pots + "</color>   사망 <color=#FF8080>" + _sim.Deaths + "/" + (_cfg.MaxDeaths + 1) + "</color>" +
                (p.Shield > 0 ? "   <color=#90D0FF>보호막 " + (p.Shield * 100).ToString("0") + "%</color>" : "") +
                (p.EvadeTime > 0 ? "   <color=#A0FFA0>회피 중</color>" : ""), _label);
        }

        static string BlockTag(string b)
        {
            string c;
            switch (b)
            {
                case "burst": c = "FFB040"; break;
                case "dps": c = "70C0FF"; break;
                case "survival": c = "70FF90"; break;
                case "gimmick": c = "FFE040"; break;
                case "dead": c = "FF5050"; break;
                default: c = "C0C0C0"; break;
            }
            return "<color=#" + c + ">" + Names.Block(b) + "</color>";
        }

        void DrawInfo()
        {
            var r = new Rect(12, 12, 290, 92);
            GUI.Box(r, GUIContent.none, _box);
            string speed = _paused ? "<color=#FFD060>일시정지</color>" : "x" + (_playMode ? _playSpeed : _speed).ToString("0.#", CultureInfo.InvariantCulture);
            GUI.Label(new Rect(22, 18, 270, 20), "<b>" + FormatTime(_sim.Time) + "</b> / " + FormatTime(_cfg.TimeLimit) + "   " + speed, _label);
            GUI.Label(new Rect(22, 40, 270, 20), "seed " + _seed + (_replay != null ? "   <color=#90D0FF>학습 판 #" + _replay.Serial + "</color>" : ""), _small);
            GUI.Label(new Rect(22, 58, 270, 20), "격노까지 " + (_bossSpec.EnrageTime > 0 ? FormatTime(Math.Max(0, _bossSpec.EnrageTime - _sim.Time)) : "-"), _small);
            if (_playMode)
            {
                GUI.Label(new Rect(22, 76, 270, 20), "<color=#90D0FF>필드 조우 — 학습된 BT 가 전투 중</color>", _small);
                return;
            }
            var s = QaBoot.Server;
            GUI.Label(new Rect(22, 76, 270, 20), s == null ? "<color=#708090>학습 서버 꺼짐</color>"
                : "학습 서버 :" + s.Port + "  " + (s.ClientConnected ? "<color=#7CFC00>접속 중</color>" : "대기") + "  판 " + s.EpisodesServed, _small);
        }

        void DrawLog()
        {
            float h = 20 + _log.Count * 18, w = 420;
            var r = new Rect(12, Screen.height - h - 14, w, h);
            GUI.Box(r, GUIContent.none, _box);
            for (int i = 0; i < _log.Count; i++)
                GUI.Label(new Rect(r.x + 10, r.y + 8 + i * 18, w - 20, 20), _log[i], _small);
        }

        void DrawBanner()
        {
            if (_bannerText == null || _bannerT > 2.2f) return;
            float a = _bannerT < 1.6f ? 1f : 1f - (_bannerT - 1.6f) / 0.6f;
            var c = _bannerColor; c.a = a;
            Shadowed(new Rect(0, Screen.height * 0.28f, Screen.width - (_panel ? 300 : 0), 50), _bannerText, _big, c);
        }

        void DrawResult()
        {
            var r = _sim.Result();
            float w = 420, h = 230, x = (Screen.width - w) / 2 - (_panel ? 150 : 0), y = Screen.height * 0.36f;
            GUI.Box(new Rect(x, y, w, h), GUIContent.none, _box);
            bool cleared = r["cleared"].Value<bool>();
            bool stalled = r["stalled"].Value<bool>();
            Shadowed(new Rect(x, y + 8, w, 40), cleared ? "클리어" : stalled ? "실패 (멈춤)" : "실패", _big,
                     cleared ? new Color(0.5f, 1f, 0.4f) : new Color(1f, 0.4f, 0.35f));
            string lines =
                "시간 <b>" + r["elapsed"].Value<double>().ToString("0.0") + "초</b>   사망 <b>" + r["deaths"] + "</b>   물약 <b>" + r["consumables_used"] + "</b>\n" +
                "준 피해 " + r["damage_dealt"].Value<double>().ToString("N0") + "   받은 피해 " + r["damage_taken"].Value<double>().ToString("N0") + "\n" +
                "기믹 성공 " + r["gimmick_success"] + " / 실패 " + r["gimmick_fail"] +
                (cleared ? "" : "   보스 체력 " + (r["boss_hp_remaining"].Value<double>() * 100).ToString("0") + "% 남음");
            if (stalled) lines += "\n<color=#FFB060>" + r["stall_reason"] + "</color>";
            GUI.Label(new Rect(x + 20, y + 54, w - 40, 70), lines, _rich);
            // 블록 점유 비율
            var bt = (JObject)r["block_time"];
            double total = 0;
            foreach (var p in bt.Properties()) total += p.Value.Value<double>();
            float bx = x + 20, by = y + 130, bw = w - 40;
            foreach (var p in bt.Properties())
            {
                float frac = (float)(p.Value.Value<double>() / Math.Max(1e-6, total));
                Fill(new Rect(bx, by, bw * frac, 14), BlockColor(p.Name));
                bx += bw * frac;
            }
            string legend = "";
            foreach (var p in bt.Properties()) legend += BlockTag(p.Name) + " " + (p.Value.Value<double>() / total * 100).ToString("0") + "%  ";
            GUI.Label(new Rect(x + 20, y + 146, w - 40, 20), legend, _small);
            if (_replay != null && _replayMatch.HasValue)
                GUI.Label(new Rect(x + 20, y + 166, w - 40, 20), _replayMatch.Value
                    ? "<color=#7CFC00>✓ 학습 서버 결과와 완전히 같음 (결정성)</color>"
                    : "<color=#FF6060>✗ 학습 서버 결과와 다름</color>", _small);
            if (_playMode) return;   // 플레이 모드: 판은 세션이 진행 — 다시·새 전투 없음
            if (GUI.Button(new Rect(x + 20, y + h - 40, 180, 30), "↺ 같은 판 다시 (R)", _button)) Restart();
            if (GUI.Button(new Rect(x + w - 200, y + h - 40, 180, 30), "▶ 새 전투 (Enter)", _button)) StartFromUi(true);
        }

        static Color BlockColor(string b)
        {
            switch (b)
            {
                case "burst": return new Color(1f, 0.7f, 0.25f);
                case "dps": return new Color(0.45f, 0.75f, 1f);
                case "survival": return new Color(0.45f, 1f, 0.55f);
                case "gimmick": return new Color(1f, 0.9f, 0.25f);
                case "dead": return new Color(1f, 0.3f, 0.3f);
                default: return new Color(0.6f, 0.6f, 0.6f);
            }
        }

        // ------------------------------------------------------------------ 설정 패널
        void DrawPanel()
        {
            float w = 290;
            _panelRect = new Rect(Screen.width - w - 10, 10, w, Screen.height - 20);
            GUI.Box(_panelRect, GUIContent.none, _box);
            GUILayout.BeginArea(new Rect(_panelRect.x + 10, _panelRect.y + 8, w - 20, _panelRect.height - 16));
            GUILayout.BeginHorizontal();
            GUILayout.Label("<b>전투 설정</b>", _label);
            if (GUILayout.Button("◂ 숨기기", _button, GUILayout.Width(80))) _panel = false;
            GUILayout.EndHorizontal();
            _panelScroll = GUILayout.BeginScrollView(_panelScroll);

            var names = _repo.ClassNames;
            var labels = new string[names.Count];
            for (int i = 0; i < names.Count; i++) labels[i] = _repo.Class(names[i]).DisplayName;
            GUILayout.Label("직업", _small);
            _uiClass = GUILayout.Toolbar(Mathf.Clamp(_uiClass, 0, names.Count - 1), labels, _button);

            GUILayout.Label("시나리오 (패치)", _small);
            var scs = _repo.Scenarios;
            var scLabels = new string[scs.Count];
            for (int i = 0; i < scs.Count; i++) scLabels[i] = scs[i].Name;
            _uiScenario = GUILayout.SelectionGrid(Mathf.Clamp(_uiScenario, 0, scs.Count - 1), scLabels, 1, _button);

            GUILayout.BeginHorizontal();
            GUILayout.Label("seed", _small, GUILayout.Width(40));
            _uiSeed = GUILayout.TextField(_uiSeed);
            if (GUILayout.Button("랜덤", _button, GUILayout.Width(50))) _uiSeed = "";
            GUILayout.EndHorizontal();
            GUILayout.Label("<color=#8090A0>비우면 새 seed</color>", _small);

            _showParams = GUILayout.Toggle(_showParams, " BT 파라미터 조정", GUI.skin.toggle);
            if (_showParams) DrawParamSliders(names[_uiClass]);

            GUILayout.Space(6);
            if (GUILayout.Button("<b>▶ 전투 시작</b> (Enter)", _button, GUILayout.Height(32))) StartFromUi(false);
            if (GUILayout.Button("↺ 같은 판 다시 (R)", _button)) Restart();

            GUILayout.Space(6);
            GUILayout.Label("재생 속도 (Space 일시정지, N 한 틱)", _small);
            int si = Array.IndexOf(Speeds, _speed);
            var spLabels = new[] { "0.5x", "1x", "2x", "4x", "8x", "16x" };
            int nsi = GUILayout.Toolbar(si < 0 ? 1 : si, spLabels, _button);
            _speed = Speeds[nsi];
            GUILayout.BeginHorizontal();
            if (GUILayout.Button(_paused ? "▶ 계속" : "⏸ 일시정지", _button)) _paused = !_paused;
            if (GUILayout.Button("한 틱 ▸", _button)) SingleStep();
            GUILayout.EndHorizontal();

            GUILayout.Space(8);
            GUILayout.Label("<b>학습 결과 파라미터 불러오기</b>", _label);
            GUILayout.Label("<color=#8090A0>reports/…/params.json 내용을 붙여넣기 (직업·시나리오도 자동 선택)</color>", _small);
            _uiJson = GUILayout.TextArea(_uiJson, GUILayout.Height(60));
            if (GUILayout.Button("JSON 적용 후 전투", _button)) ApplyJson();
            if (_uiJsonMsg != null) GUILayout.Label(_uiJsonMsg, _small);

            GUILayout.Space(8);
            GUILayout.Label("<b>학습 서버 판 보기</b>", _label);
            if (QaBoot.Recorder == null)
            {
                GUILayout.Label("<color=#8090A0>에디터: 메뉴 QA > Play Mode Server 를 켜고 Play\n빌드: QaArena.exe -qaPort 7777 (창 모드)</color>", _small);
            }
            else
            {
                var last = QaBoot.Recorder.Last;
                if (last == null) GUILayout.Label("아직 학습 쪽이 돌린 판이 없음", _small);
                else
                {
                    var rr = last.Result;
                    GUILayout.Label("최근 #" + last.Serial + "  " + last.Request["class"] + "  seed " + last.Request["seed"] + "  " +
                                    (rr["cleared"].Value<bool>() ? "<color=#7CFC00>클리어 " + rr["elapsed"] + "s</color>" : "<color=#FF7070>실패</color>") +
                                    (last.TriggerParams.Count > 0 ? "  트리거 " + last.TriggerParams.Count : ""), _small);
                    if (GUILayout.Button("이 판 재생", _button)) ReplayRecord(last);
                }
                _autoFollow = GUILayout.Toggle(_autoFollow, " 학습 판 자동 따라보기", GUI.skin.toggle);
            }

            if (_simError != null) GUILayout.Label("<color=#FF6060>" + _simError + "</color>", _rich);
            GUILayout.Space(8);
            GUILayout.Label("<color=#708090>마우스 휠 확대·축소, 오른쪽 드래그 회전, Tab 패널</color>", _small);
            GUILayout.EndScrollView();
            GUILayout.EndArea();
        }

        Dictionary<string, float> EditsFor(string cls)
        {
            if (!_edits.TryGetValue(cls, out var d))
            {
                d = new Dictionary<string, float>();
                foreach (var p in _repo.Class(cls).ParamList) d[p.Name] = (float)p.Default;
                _edits[cls] = d;
            }
            return d;
        }

        void DrawParamSliders(string cls)
        {
            var spec = _repo.Class(cls);
            var d = EditsFor(cls);
            foreach (var p in spec.ParamList)
            {
                float v = d[p.Name];
                GUILayout.Label(p.Name + (p.Group == ParamDef.GroupPersona ? " <color=#C090FF>(페르소나)</color>" : "") +
                                "  <b>" + v.ToString("0.00", CultureInfo.InvariantCulture) + "</b>" +
                                (Math.Abs(v - p.Default) > 1e-4 ? "  <color=#8090A0>기본 " + p.Default.ToString("0.##", CultureInfo.InvariantCulture) + "</color>" : ""), _small);
                d[p.Name] = GUILayout.HorizontalSlider(v, (float)p.Low, (float)p.High);
            }
            if (GUILayout.Button("기본값(손 튜닝)으로", _button))
                foreach (var p in spec.ParamList) d[p.Name] = (float)p.Default;
        }

        JObject ParamsFromUi(string cls)
        {
            var spec = _repo.Class(cls);
            var d = EditsFor(cls);
            var o = new JObject();
            foreach (var p in spec.ParamList)
            {
                double v = Math.Max(p.Low, Math.Min(p.High, d[p.Name]));
                if (Math.Abs(v - p.Default) > 1e-6) o[p.Name] = v;
            }
            return o;
        }

        void StartFromUi(bool newSeed)
        {
            var cls = _repo.ClassNames[_uiClass];
            var sc = _repo.Scenarios[_uiScenario].Name;
            long seed;
            if (newSeed || !long.TryParse(_uiSeed.Trim(), out seed)) seed = NextSeed();
            _uiSeed = newSeed ? "" : _uiSeed;
            NewBattle(cls, sc, seed, ParamsFromUi(cls));
        }

        void Restart()
        {
            if (_replay != null) { ReplayRecord(_replay); return; }
            if (_spec == null) return;
            NewBattle(_spec.Name, _scenario, _seed, CurrentParams);
        }

        void SingleStep()
        {
            _paused = true;
            if (_sim != null && !_sim.Done)
            {
                _acc = 0;
                StepOnce();
                if (_sim.Done) OnFinished();
            }
        }

        void ApplyJson()
        {
            _uiJsonMsg = null;
            JObject o;
            try
            {
                o = JsonConvert.DeserializeObject<JToken>(_uiJson, new JsonSerializerSettings { DateParseHandling = DateParseHandling.None }) as JObject;
            }
            catch (Exception ex)
            {
                _uiJsonMsg = "<color=#FF6060>JSON 오류: " + ex.Message + "</color>";
                return;
            }
            if (o == null) { _uiJsonMsg = "<color=#FF6060>JSON 객체가 아님</color>"; return; }
            var cls = o["class"]?.Type == JTokenType.String ? (string)o["class"] : _repo.ClassNames[_uiClass];
            if (!_repo.HasClass(cls)) { _uiJsonMsg = "<color=#FF6060>모르는 직업 " + cls + "</color>"; return; }
            var sc = o["scenario"]?.Type == JTokenType.String ? (string)o["scenario"] : _repo.Scenarios[_uiScenario].Name;
            if (!_repo.HasScenario(sc)) sc = "base";
            var ps = o["source"]?["params"] as JObject ?? o["params"] as JObject ?? o;
            var clean = new JObject();
            var spec = _repo.Class(cls);
            var d = EditsFor(cls);
            foreach (var p in ps.Properties())
                if (spec.HasParam(p.Name) && (p.Value.Type == JTokenType.Float || p.Value.Type == JTokenType.Integer))
                {
                    clean[p.Name] = p.Value;
                    d[p.Name] = p.Value.Value<float>();
                }
            if (clean.Count == 0) { _uiJsonMsg = "<color=#FF6060>적용할 파라미터가 없음</color>"; return; }
            for (int i = 0; i < _repo.ClassNames.Count; i++) if (_repo.ClassNames[i] == cls) _uiClass = i;
            for (int i = 0; i < _repo.Scenarios.Count; i++) if (_repo.Scenarios[i].Name == sc) _uiScenario = i;
            _showParams = true;
            _uiJsonMsg = "<color=#7CFC00>" + cls + " 파라미터 " + clean.Count + "개 적용</color>";
            long seed;
            if (!long.TryParse(_uiSeed.Trim(), out seed)) seed = NextSeed();
            NewBattle(cls, sc, seed, clean);
        }

        // ------------------------------------------------------------------ 입력 (IMGUI 이벤트)
        void HandleInput()
        {
            var e = Event.current;
            bool overPanel = _panel && _panelRect.Contains(e.mousePosition);
            if (e.type == EventType.ScrollWheel && !overPanel)
            {
                _camDist = Mathf.Clamp(_camDist + e.delta.y * 1.2f, 8f, 60f);
                e.Use();
            }
            else if (e.type == EventType.MouseDrag && e.button == 1)
            {
                _camYaw += e.delta.x * 0.3f;
                _camPitch = Mathf.Clamp(_camPitch + e.delta.y * 0.2f, 15f, 80f);
                e.Use();
            }
            else if (e.type == EventType.KeyDown && GUIUtility.keyboardControl == 0)
            {
                switch (e.keyCode)
                {
                    case KeyCode.Space: _paused = !_paused; e.Use(); break;
                    case KeyCode.N: SingleStep(); e.Use(); break;
                    case KeyCode.R: Restart(); e.Use(); break;
                    case KeyCode.Return: case KeyCode.KeypadEnter: StartFromUi(true); e.Use(); break;
                    case KeyCode.Tab: _panel = !_panel; e.Use(); break;
                    case KeyCode.Alpha1: _speed = 0.5f; e.Use(); break;
                    case KeyCode.Alpha2: _speed = 1f; e.Use(); break;
                    case KeyCode.Alpha3: _speed = 2f; e.Use(); break;
                    case KeyCode.Alpha4: _speed = 4f; e.Use(); break;
                    case KeyCode.Alpha5: _speed = 8f; e.Use(); break;
                    case KeyCode.Alpha6: _speed = 16f; e.Use(); break;
                }
            }
        }
    }
}
