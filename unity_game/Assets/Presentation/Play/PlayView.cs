// 플레이 모드 화면: 지역(바닥·장애물·엔티티·플레이어)과 uGUI 창(HUD·대화·퀘스트).
// 세계 상태(WorldState)를 읽어 그리기만 한다. 버튼은 WorldState 명령을 부른다 (로직은 여기 없음).
// 입력 모듈을 두지 않는다 → 사람 마우스·키보드가 플레이에 끼어들지 못함 (결정성). 클릭은 ui_click 만.
using System;
using System.Collections.Generic;
using Qa.Play.Perception;
using Qa.Play.World;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Qa.Presentation.Play
{
    public sealed class PlayView : MonoBehaviour, IPlayScene, Qa.Play.Server.IActionLogView, Qa.Play.Server.IPilotNoteView
    {
        public const int MaxChoices = 4;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Register() => Qa.Play.Server.PlayBoot.SceneFactory = w => Create(w);

        Func<WorldState> _world;
        Transform _zoneRoot, _player;
        Camera _cam;
        Light _sun;
        string _builtZone;
        readonly List<QaTag> _tags = new List<QaTag>();
        Material _lit;

        // UI
        Transform _uiRoot;
        TMP_Text _hudZone, _hudGold, _dlgSpeaker, _dlgText, _questsBody, _log;
        GameObject _dialog, _quests;
        readonly Button[] _choices = new Button[MaxChoices];
        readonly TMP_Text[] _choiceText = new TMP_Text[MaxChoices];
        readonly Queue<string> _logLines = new Queue<string>();
        public const int MaxSlots = 8, MaxShopRows = 4;
        GameObject _inv, _tip, _shop;
        readonly Button[] _invSlots = new Button[MaxSlots];
        readonly TMP_Text[] _invSlotText = new TMP_Text[MaxSlots];
        readonly string[] _invSlotItem = new string[MaxSlots];
        TMP_Text _invDetail, _shopGold, _shopMsg;
        Button _invAssign;
        readonly TMP_Text[] _shopRowText = new TMP_Text[MaxShopRows];
        readonly Button[] _shopBuy = new Button[MaxShopRows];
        readonly string[] _shopRowItem = new string[MaxShopRows];
        readonly TMP_Text[] _hudQuick = new TMP_Text[2];
        GameObject _combatHud;
        TMP_Text _combatText;
        Vector3 _combatDir;
        string _combatEnemy;

        // 게임 안내 토스트 (WorldState.Notice — 관찰에는 notice 사건으로 보인다)
        GameObject _notice;
        TMP_Text _noticeText;
        int _noticeShown;
        float _noticeUntil;

        // "QA 플레이어" 메모 (pilot_note, v0.3): 별도 캔버스, 레이캐스터 없음·blocksRaycasts=false·QaTag 없음 → ui_click 가림·관찰 무관
        public const int PilotLines = 4;
        public const float PilotBubbleSeconds = 4f;
        RectTransform _pilotRoot;
        readonly TMP_Text[] _pilotLine = new TMP_Text[PilotLines];
        readonly List<KeyValuePair<string, string>> _pilotNotes = new List<KeyValuePair<string, string>>();
        GameObject _pilotPanel, _bubble, _toast;
        TMP_Text _bubbleText, _toastText;
        RectTransform _bubbleRt;
        float _bubbleUntil, _toastUntil;
        bool _fieldVisible = true;

        // 월드 이름표 (촌장·약초 등 머리 위): 표시 전용, QaIgnore — 관찰은 QaTag 의 label·marker 로 이미 나간다
        sealed class WorldLabel { public string Id, Name; public Transform T; public TextMeshPro Text; public string Marker; }
        readonly List<WorldLabel> _labels = new List<WorldLabel>();

        public IReadOnlyList<QaTag> WorldTags => _tags;
        public Transform UiRoot => _uiRoot;
        public Vector3 PlayerPosition => _player != null ? _player.position : Vector3.zero;

        public static PlayView Create(Func<WorldState> world)
        {
            var go = new GameObject("PlayView");
            DontDestroyOnLoad(go);
            var v = go.AddComponent<PlayView>();
            v._world = world;
            v.BuildCommon();
            return v;
        }

        // ------------------------------------------------------------------ 공통 (카메라·조명·UI)
        void BuildCommon()
        {
            _lit = Resources.Load<Material>("QaView/Lit");
            var camGo = new GameObject("PlayCamera");
            camGo.transform.SetParent(transform, false);
            _cam = camGo.AddComponent<Camera>();
            _cam.fieldOfView = Visibility.Fov;
            _cam.nearClipPlane = Visibility.Near;
            _cam.farClipPlane = Visibility.Far + 20f;
            _cam.clearFlags = CameraClearFlags.SolidColor;
            _cam.backgroundColor = new Color(0.55f, 0.68f, 0.78f);
            var lightGo = new GameObject("Sun");
            lightGo.transform.SetParent(transform, false);
            var l = lightGo.AddComponent<Light>();
            _sun = l;
            l.type = LightType.Directional;
            l.intensity = 1.1f;
            lightGo.transform.rotation = Quaternion.Euler(50, -30, 0);

            if (EventSystem.current == null)
            {
                var es = new GameObject("EventSystem", typeof(EventSystem));   // 입력 모듈 없음 (위 주석)
                es.transform.SetParent(transform, false);
            }
            BuildUi();
        }

        // ------------------------------------------------------------------ 지역
        void BuildZone(WorldState w)
        {
            if (_zoneRoot != null) Destroy(_zoneRoot.gameObject);
            _tags.Clear();
            _labels.Clear();
            var z = w.ZoneDef;
            _zoneRoot = new GameObject("Zone:" + z.Id).transform;
            _zoneRoot.SetParent(transform, false);

            var ground = GameObject.CreatePrimitive(PrimitiveType.Cube);
            ground.name = "Ground";
            ground.transform.SetParent(_zoneRoot, false);
            ground.transform.localScale = new Vector3((float)(z.MaxX - z.MinX), 0.1f, (float)(z.MaxZ - z.MinZ));
            ground.transform.position = new Vector3((float)(z.MinX + z.MaxX) / 2, -0.05f, (float)(z.MinZ + z.MaxZ) / 2);
            Paint(ground, z.Id == "forest" ? new Color(0.22f, 0.4f, 0.2f) : new Color(0.42f, 0.58f, 0.35f));

            foreach (var o in z.Obstacles)
            {
                var c = GameObject.CreatePrimitive(PrimitiveType.Cube);
                c.name = "Obstacle:" + o.Id;
                c.transform.SetParent(_zoneRoot, false);
                c.transform.localScale = new Vector3((float)o.SizeX, (float)o.Height, (float)o.SizeZ);
                c.transform.position = new Vector3((float)o.X, (float)o.Height / 2, (float)o.Z);
                Paint(c, o.Id.StartsWith("fence") ? new Color(0.55f, 0.4f, 0.25f) : new Color(0.75f, 0.7f, 0.62f));
            }

            foreach (var e in w.Entities)
            {
                var d = e.Def;
                var role = QaTag.ParseRole(d.Role);
                GameObject go;
                switch (role)
                {
                    case QaRole.Npc:
                        go = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                        go.transform.localScale = new Vector3(0.8f, (float)d.Height / 2, 0.8f);
                        go.transform.position = new Vector3((float)d.X, (float)d.Height / 2, (float)d.Z);
                        Paint(go, Array.IndexOf(d.Tags, "quest_giver") >= 0 ? new Color(0.95f, 0.8f, 0.2f) : new Color(0.8f, 0.3f, 0.3f));
                        break;
                    case QaRole.Enemy:
                        go = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                        go.transform.localScale = new Vector3(1.8f, (float)d.Height / 2, 1.8f);
                        go.transform.position = new Vector3((float)d.X, (float)d.Height / 2, (float)d.Z);
                        Paint(go, new Color(0.35f, 0.3f, 0.32f));
                        break;
                    case QaRole.Portal:
                        go = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                        go.transform.localScale = new Vector3((float)d.Radius * 2, 0.05f, (float)d.Radius * 2);
                        go.transform.position = new Vector3((float)d.X, 0.05f, (float)d.Z);
                        Paint(go, new Color(0.4f, 0.3f, 0.9f));
                        break;
                    default:
                        go = GameObject.CreatePrimitive(PrimitiveType.Cube);
                        go.transform.localScale = new Vector3((float)d.Radius * 2, (float)d.Height, (float)d.Radius * 2);
                        go.transform.position = new Vector3((float)d.X, (float)d.Height / 2, (float)d.Z);
                        Paint(go, new Color(0.6f, 0.45f, 0.2f));
                        break;
                }
                go.name = "Entity:" + d.Id;
                go.transform.SetParent(_zoneRoot, true);
                AddLabel(go.transform, d, role);
                // 태그 위치 = 바닥 위치 (시야 판정은 Visibility 가 높이로 경계 상자를 만든다)
                var tagGo = new GameObject(d.Id);
                tagGo.transform.SetParent(go.transform, false);
                tagGo.transform.position = new Vector3((float)d.X, 0, (float)d.Z);
                var tag = tagGo.AddComponent<QaTag>();
                tag.id = d.Id;
                tag.role = role;
                tag.label = d.Label;
                tag.actions = d.Actions;
                tag.tags = d.Tags;
                tag.alwaysKnown = d.AlwaysKnown;
                tag.radius = (float)d.Radius;
                tag.height = (float)d.Height;
                _tags.Add(tag);
            }

            var p = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            p.name = "Player";
            p.transform.SetParent(_zoneRoot, false);
            p.transform.localScale = new Vector3(0.8f, 0.9f, 0.8f);
            Paint(p, new Color(0.25f, 0.5f, 0.95f));
            _player = p.transform;
            _builtZone = z.Id;
        }

        static Color LabelColor(QaRole role)
        {
            switch (role)
            {
                case QaRole.Npc: return new Color(1f, 0.95f, 0.75f);
                case QaRole.Enemy: return new Color(1f, 0.45f, 0.4f);
                case QaRole.Item: return new Color(0.6f, 1f, 0.6f);
                case QaRole.Portal: return new Color(0.7f, 0.75f, 1f);
                default: return new Color(0.9f, 0.9f, 0.9f);
            }
        }

        void AddLabel(Transform entity, EntityDef d, QaRole role)
        {
            if (string.IsNullOrEmpty(d.Label)) return;
            var go = new GameObject("Label");
            go.AddComponent<QaIgnore>();
            go.transform.SetParent(entity, false);
            go.transform.position = new Vector3((float)d.X, (float)d.Height + 0.7f, (float)d.Z);
            var t = go.AddComponent<TextMeshPro>();
            var f = PlayFont.Get();
            if (f != null) t.font = f;
            t.text = d.Label;
            t.fontSize = role == QaRole.Enemy ? 7f : 5.5f;
            t.alignment = TextAlignmentOptions.Center;
            t.color = LabelColor(role);
            t.outlineWidth = 0.25f;
            t.outlineColor = new Color32(0, 0, 0, 200);
            t.rectTransform.sizeDelta = new Vector2(12f, 2f);
            _labels.Add(new WorldLabel { Id = d.Id, Name = d.Label, T = go.transform, Text = t });
        }

        static string MarkerGlyph(string m) =>
            m == "quest_available" ? "<color=#FFD040>!</color> " : m == "quest_turn_in" ? "<color=#FFD040>?</color> " : m == "objective" ? "<color=#80E0FF>◆</color> " : "";

        void SyncLabels(WorldState w)
        {
            foreach (var l in _labels)
            {
                if (l.T == null) continue;
                var mk = w.MarkerFor(l.Id);
                if (mk == l.Marker) continue;
                l.Marker = mk;
                l.Text.text = MarkerGlyph(mk) + l.Name;
            }
        }

        void FaceLabels()
        {
            if (_cam == null) return;
            var rot = _cam.transform.rotation;
            foreach (var l in _labels) if (l.T != null) l.T.rotation = rot;
        }

        void Paint(GameObject go, Color c)
        {
            var col = go.GetComponent<Collider>();
            if (col != null) Destroy(col);   // 물리 미사용
            var r = go.GetComponent<Renderer>();
            if (r == null) return;
            if (_lit != null) r.sharedMaterial = new Material(_lit) { color = c };
            else r.material.color = c;
        }

        // ------------------------------------------------------------------ 동기화
        public void Sync(WorldState w)
        {
            if (w == null) return;
            if (_builtZone != w.Zone || _player == null) BuildZone(w);
            _player.position = new Vector3((float)w.PlayerX, 0.9f, (float)w.PlayerZ);
            var ground = new Vector3((float)w.PlayerX, 0f, (float)w.PlayerZ);
            Visibility.CameraPose(ground, out var cp, out var cr);
            _cam.transform.SetPositionAndRotation(cp, cr);
            foreach (var t in _tags)
            {
                var e = w.Entity(t.id);
                var go = t.transform.parent.gameObject;
                if (go.activeSelf != (e != null)) go.SetActive(e != null);
            }

            if (w.NoticeCount != _noticeShown)
            {
                _noticeShown = w.NoticeCount;
                if (w.Notice != null)
                {
                    _noticeText.text = w.Notice;
                    _notice.SetActive(true);
                    _noticeUntil = Time.unscaledTime + 6f;
                }
            }

            SyncLabels(w);
            LayoutPilotPanel(w.Modal);
            _hudZone.text = w.ZoneDef.Label;
            _hudGold.text = "골드 " + w.Gold;
            for (int i = 0; i < _hudQuick.Length; i++)
            {
                var it = i < w.QuickSlots.Length ? w.QuickSlots[i] : null;
                _hudQuick[i].text = "퀵슬롯" + (i + 1) + ": " + (it == null ? "비어 있음" : w.Data.Item(it).Label + " x" + w.CountOf(it));
            }

            // 대화
            bool dlg = w.Modal == "dialog" && w.Dialogue != null;
            _dialog.SetActive(dlg);
            if (dlg)
            {
                _dlgSpeaker.text = w.Dialogue.Speaker;
                _dlgText.text = w.Dialogue.Text;
                for (int i = 0; i < MaxChoices; i++)
                {
                    bool on = i < w.Dialogue.Choices.Count;
                    _choices[i].gameObject.SetActive(on);
                    _choiceText[i].text = on ? w.Dialogue.Choices[i] : "";
                }
            }

            // 퀘스트 창
            _quests.SetActive(w.Modal == "quests");
            var sb = new System.Text.StringBuilder();
            foreach (var q in w.Quests)
            {
                var st = w.QuestStateOf(q);
                if (st != QuestStates.Active && st != QuestStates.Ready) continue;
                sb.Append("■ ").Append(q.Def.Title).Append("\n");
                for (int i = 0; i < q.Def.Objectives.Count; i++)
                {
                    int pr = w.Progress(q, i), tg = w.Target(q, i);
                    sb.Append("   ").Append(pr >= tg ? "✔ " : "- ").Append(q.Def.Objectives[i].Text);
                    if (tg > 1) sb.Append(" (").Append(pr).Append("/").Append(tg).Append(")");
                    sb.Append("\n");
                }
            }
            _questsBody.text = sb.Length == 0 ? "진행 중인 퀘스트가 없습니다." : sb.ToString().TrimEnd();

            // 인벤토리 창
            _inv.SetActive(w.Modal == "inventory");
            for (int i = 0; i < MaxSlots; i++)
            {
                bool on = i < w.Inventory.Count;
                _invSlots[i].gameObject.SetActive(on);
                _invSlotItem[i] = on ? w.Inventory[i].Id : null;
                if (!on) continue;
                var st = w.Inventory[i];
                _invSlots[i].GetComponent<QaTag>().id = "ui.inventory.slot." + st.Id;
                _invSlotText[i].text = (w.InventorySelected == st.Id ? "▶ " : "") + w.Data.Item(st.Id).Label + " x" + st.Count;
            }
            if (w.Inventory.Count == 0) _invDetail.text = "가방이 비어 있습니다.";
            else if (w.InventorySelected == null) _invDetail.text = "아이템을 선택하세요.";
            else
            {
                var def = w.Data.Item(w.InventorySelected);
                _invDetail.text = def.Label + ": " + def.Description;
            }
            _invAssign.interactable = w.CanAssignSelected;

            // 안내 팝업 (인벤토리 위)
            _tip.SetActive(w.Tip != null);

            // 상점
            _shop.SetActive(w.Modal == "shop");
            var items = w.ShopItems;
            for (int i = 0; i < MaxShopRows; i++)
            {
                bool on = i < items.Count;
                _shopRowText[i].gameObject.SetActive(on);
                _shopBuy[i].gameObject.SetActive(on);
                _shopRowItem[i] = on ? items[i] : null;
                if (!on) continue;
                var def = w.Data.Item(items[i]);
                _shopRowText[i].GetComponent<QaTag>().id = "ui.shop.item." + def.Id;
                _shopBuy[i].GetComponent<QaTag>().id = "ui.shop.buy." + def.Id;
                _shopRowText[i].text = def.Label + " — " + def.Price + "G  (" + def.Description + ")";
                _shopBuy[i].interactable = w.BuyEnabled(def.Id);
            }
            _shopGold.text = "보유 골드 " + w.Gold + "G";
            _shopMsg.text = w.ShopMessage ?? "";
        }

        // ------------------------------------------------------------------ 전투 표시
        public void SyncCombat(WorldState w, EntityState enemy, Qa.Sim.CombatSim sim)
        {
            if (_builtZone != w.Zone || _player == null) BuildZone(w);
            var ep = new Vector3((float)enemy.Def.X, 0f, (float)enemy.Def.Z);
            if (_combatEnemy != enemy.Id)
            {
                // 전투 시작 위치에서 적 → 플레이어 방향을 고정하고 1차원 거리를 그 선 위에 그린다
                var d = new Vector3((float)w.PlayerX, 0f, (float)w.PlayerZ) - ep;
                _combatDir = d.sqrMagnitude > 1e-4f ? d.normalized : Vector3.back;
                _combatEnemy = enemy.Id;
            }
            var pp = ep + _combatDir * (float)sim.Distance;
            _player.position = pp + Vector3.up * 0.9f;
            Visibility.CameraPose(pp, out var cp, out var cr);
            _cam.transform.SetPositionAndRotation(cp, cr);
            var pl = sim.PlayerState;
            var bs = sim.BossState;
            _combatHud.SetActive(true);
            _combatText.text = "전투: " + enemy.Def.Label + "   보스 HP " + Mathf.RoundToInt((float)bs.HpRatio * 100) + "%   |   내 HP " +
                               Mathf.RoundToInt((float)pl.HpRatio * 100) + "%  사망 " + sim.Deaths + "   |   " + sim.CurrentBlock + "   |   " +
                               Mathf.RoundToInt((float)sim.Time) + "s";
        }

        public void EndCombat()
        {
            _combatEnemy = null;
            if (_combatHud != null) _combatHud.SetActive(false);
            SetFieldVisible(true);
        }

        public ICombatPresenter Presenter => BattleViewer.PlayInstance;

        public void SetFieldVisible(bool visible)
        {
            _fieldVisible = visible;
            if (_zoneRoot != null) _zoneRoot.gameObject.SetActive(visible);
            _cam.enabled = visible;
            _sun.enabled = visible;
            _uiRoot.GetComponent<Canvas>().enabled = visible;
        }

        /// <summary>관람용 행동 로그 (관찰 대상 아님: QaIgnore).</summary>
        public void AddLog(string line)
        {
            _logLines.Enqueue(line);
            while (_logLines.Count > 5) _logLines.Dequeue();
            _log.text = string.Join("\n", _logLines);
        }

        // ------------------------------------------------------------------ 플레이어 메모 (pilot_note)
        // H1: "QA 플레이어" 패널 위치. 창이 없으면 왼쪽 아래, 대화창(아래쪽 42%)이면 왼쪽 위(HUD 아래),
        // 인벤토리·상점·퀘스트 창(가운데)이면 왼쪽 가장자리 좁은 세로 띠 (상점 창 왼쪽 끝 15% = 192px 안쪽).
        string _pilotLayout;
        RectTransform _logRt;   // 관람용 행동 로그 (왼쪽 가운데) — 패널 자리에 맞춰 줄이거나 숨긴다
        void LayoutPilotPanel(string modal)
        {
            if (_pilotPanel == null) return;
            string mode = modal == null ? "bottom" : modal == "dialog" ? "top" : "strip";
            if (mode == _pilotLayout) return;
            _pilotLayout = mode;
            var rt = (RectTransform)_pilotPanel.transform;
            float lineH;
            int lines;
            switch (mode)
            {
                case "top":
                    rt.anchorMin = new Vector2(0, 1); rt.anchorMax = new Vector2(0, 1);
                    rt.offsetMin = new Vector2(12, -64 - 184); rt.offsetMax = new Vector2(452, -64);
                    lineH = 40; lines = 2;
                    break;
                case "strip":
                    rt.anchorMin = new Vector2(0, 0); rt.anchorMax = new Vector2(0, 1);
                    rt.offsetMin = new Vector2(8, 12); rt.offsetMax = new Vector2(186, -64);
                    lineH = 140; lines = 7;
                    break;
                default:
                    rt.anchorMin = new Vector2(0, 0); rt.anchorMax = new Vector2(0, 0);
                    rt.offsetMin = new Vector2(12, 12); rt.offsetMax = new Vector2(452, 196);
                    lineH = 40; lines = 2;
                    break;
            }
            if (_logRt != null)
            {
                _logRt.gameObject.SetActive(mode != "strip");                        // 가운데 창이 열려 있으면 숨김 (세로 띠와 겹침)
                _logRt.anchorMax = new Vector2(0.35f, mode == "top" ? 0.64f : 0.75f); // 대화 중: 왼쪽 위 패널(0.655~) 아래까지만
            }
            for (int i = 0; i < PilotLines; i++)
            {
                var lt = (RectTransform)_pilotLine[i].transform;
                float top = -26 - i * lineH;
                lt.offsetMin = new Vector2(12, top - lineH);
                lt.offsetMax = new Vector2(-12, top);
                _pilotLine[i].maxVisibleLines = lines;
            }
        }

        public void ShowPilotNote(string kind, string text)
        {
            if (_pilotRoot == null) BuildPilotUi();
            _pilotNotes.Add(new KeyValuePair<string, string>(kind, text));
            while (_pilotNotes.Count > PilotLines) _pilotNotes.RemoveAt(0);
            _pilotPanel.SetActive(true);
            for (int i = 0; i < PilotLines; i++)
            {
                bool on = i < _pilotNotes.Count;
                _pilotLine[i].gameObject.SetActive(on);
                if (!on) continue;
                bool latest = i == _pilotNotes.Count - 1;
                var k = _pilotNotes[i].Key;
                var col = KindColor(k);
                string hex = ColorUtility.ToHtmlStringRGB(col);
                string body = k == "finding" ? "<b>" + Esc(_pilotNotes[i].Value) + "</b>" : Esc(_pilotNotes[i].Value);
                _pilotLine[i].text = "<color=#" + hex + "><b>[" + KindLabel(k) + "]</b></color> " + body;
                _pilotLine[i].alpha = latest ? 1f : 0.55f;
            }
            if (kind == "finding")
            {
                _toastText.text = "<b>발견</b>  " + Esc(text);
                _toast.SetActive(true);
                _toastUntil = Time.unscaledTime + PilotBubbleSeconds;
            }
            else
            {
                _bubbleText.text = Esc(text);
                _bubbleText.color = kind == "plan" ? KindColor("plan") : Color.white;
                _bubble.SetActive(_fieldVisible);
                _bubbleUntil = Time.unscaledTime + PilotBubbleSeconds;
            }
        }

        static string KindLabel(string k) => k == "plan" ? "계획" : k == "finding" ? "발견" : "생각";

        static Color KindColor(string k) =>
            k == "plan" ? new Color(0.45f, 0.8f, 1f) : k == "finding" ? new Color(1f, 0.6f, 0.2f) : new Color(0.85f, 0.85f, 0.85f);

        static string Esc(string s) => s.Replace("<", "\u2039").Replace(">", "\u203A");   // TMP 리치 텍스트 태그로 해석되지 않게

        void LateUpdate()
        {
            FaceLabels();
            float now = Time.unscaledTime;
            if (_notice != null && _notice.activeSelf && now > _noticeUntil) _notice.SetActive(false);
            if (_pilotRoot == null) return;
            if (_toast.activeSelf && now > _toastUntil) _toast.SetActive(false);
            if (!_bubble.activeSelf) return;
            if (now > _bubbleUntil || !_fieldVisible || _player == null) { _bubble.SetActive(false); return; }
            var sp = _cam.WorldToScreenPoint(_player.position + Vector3.up * 1.6f);
            if (sp.z <= 0) { _bubble.SetActive(false); return; }
            RectTransformUtility.ScreenPointToLocalPointInRectangle(_pilotRoot, sp, null, out var lp);
            _bubbleRt.anchoredPosition = lp;
        }

        void BuildPilotUi()
        {
            // 필드 캔버스와 분리: 전투 장면(필드 캔버스 꺼짐) 중에도 보인다. GraphicRaycaster 를 달지 않는다.
            var go = new GameObject("PilotCanvas", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(CanvasGroup));
            go.transform.SetParent(transform, false);
            go.AddComponent<QaIgnore>();
            var cv = go.GetComponent<Canvas>();
            cv.renderMode = RenderMode.ScreenSpaceOverlay;
            cv.sortingOrder = 50;
            var sc = go.GetComponent<CanvasScaler>();
            sc.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            sc.referenceResolution = new Vector2(1280, 720);
            sc.matchWidthOrHeight = 0.5f;
            var cg = go.GetComponent<CanvasGroup>();
            cg.blocksRaycasts = false;
            cg.interactable = false;
            _pilotRoot = (RectTransform)go.transform;

            // 패널: 왼쪽 아래 (퀵슬롯 HUD 는 위쪽)
            var panel = Rect("PilotPanel", _pilotRoot, new Vector2(0, 0), new Vector2(0, 0), new Vector2(12, 12), new Vector2(452, 196));
            Img(panel, new Color(0.05f, 0.06f, 0.1f, 0.62f), false);
            var title = Text("Title", panel, "QA 플레이어", 15, new Vector2(0, 1), new Vector2(1, 1), new Vector2(12, -24), new Vector2(-12, -4), null);
            title.color = new Color(1f, 0.85f, 0.4f);
            title.fontStyle = FontStyles.Bold;
            for (int i = 0; i < PilotLines; i++)
            {
                float top = -26 - i * 40;
                var t = Text("Line" + i, panel, "", 15, new Vector2(0, 1), new Vector2(1, 1), new Vector2(12, top - 40), new Vector2(-12, top), null);
                t.alignment = TextAlignmentOptions.TopLeft;
                t.textWrappingMode = TextWrappingModes.Normal;
                t.maxVisibleLines = 2;
                t.overflowMode = TextOverflowModes.Ellipsis;
                t.richText = true;
                _pilotLine[i] = t;
                t.gameObject.SetActive(false);
            }
            _pilotPanel = panel.gameObject;

            // 말풍선: 플레이어 머리 위 (thought·plan)
            _bubbleRt = Rect("Bubble", _pilotRoot, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            _bubbleRt.sizeDelta = new Vector2(360, 64);
            _bubbleRt.pivot = new Vector2(0.5f, 0f);
            Img(_bubbleRt, new Color(0.08f, 0.08f, 0.12f, 0.82f), false);
            _bubbleText = Text("Text", _bubbleRt, "", 16, Vector2.zero, Vector2.one, new Vector2(10, 4), new Vector2(-10, -4), null);
            _bubbleText.alignment = TextAlignmentOptions.Center;
            _bubbleText.textWrappingMode = TextWrappingModes.Normal;
            _bubbleText.maxVisibleLines = 2;
            _bubbleText.overflowMode = TextOverflowModes.Ellipsis;
            _bubble = _bubbleRt.gameObject;
            _bubble.SetActive(false);

            // 토스트: 화면 위쪽 (finding)
            var toast = Rect("FindingToast", _pilotRoot, new Vector2(0.2f, 1), new Vector2(0.8f, 1), new Vector2(0, -136), new Vector2(0, -68));
            Img(toast, new Color(0.45f, 0.2f, 0.02f, 0.9f), false);
            _toastText = Text("Text", toast, "", 18, Vector2.zero, Vector2.one, new Vector2(14, 4), new Vector2(-14, -4), null);
            _toastText.alignment = TextAlignmentOptions.Center;
            _toastText.color = new Color(1f, 0.88f, 0.7f);
            _toastText.textWrappingMode = TextWrappingModes.Normal;
            _toastText.maxVisibleLines = 2;
            _toastText.overflowMode = TextOverflowModes.Ellipsis;
            _toast = toast.gameObject;
            _toast.SetActive(false);
        }

        // ------------------------------------------------------------------ UI 구성
        void BuildUi()
        {
            var canvasGo = new GameObject("PlayCanvas", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            canvasGo.transform.SetParent(transform, false);
            var canvas = canvasGo.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = canvasGo.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1280, 720);
            scaler.matchWidthOrHeight = 0.5f;
            _uiRoot = canvasGo.transform;

            // HUD
            var hud = Rect("Hud", _uiRoot, new Vector2(0, 1), new Vector2(1, 1), new Vector2(0, -56), Vector2.zero);
            Tag(hud, "ui.hud");
            Img(hud, new Color(0, 0, 0, 0.45f), false);
            _hudZone = Text("Zone", hud, "", 24, new Vector2(0, 0), new Vector2(0.3f, 1), new Vector2(16, 0), Vector2.zero, "ui.hud.zone");
            _hudGold = Text("Gold", hud, "", 22, new Vector2(0.22f, 0), new Vector2(0.34f, 1), Vector2.zero, Vector2.zero, "ui.hud.gold");
            _hudQuick[0] = Text("Quick0", hud, "", 18, new Vector2(0.34f, 0), new Vector2(0.52f, 1), Vector2.zero, Vector2.zero, "ui.hud.quickslot.0");
            _hudQuick[1] = Text("Quick1", hud, "", 18, new Vector2(0.52f, 0), new Vector2(0.7f, 1), Vector2.zero, Vector2.zero, "ui.hud.quickslot.1");
            MakeButton("InventoryButton", hud, "인벤토리", new Vector2(1, 0), new Vector2(1, 1), new Vector2(-340, 8), new Vector2(-186, -8), "ui.hud.inventory",
                () => _world()?.OpenWindow("inventory"));
            MakeButton("QuestsButton", hud, "퀘스트", new Vector2(1, 0), new Vector2(1, 1), new Vector2(-170, 8), new Vector2(-16, -8), "ui.hud.quests",
                () => _world()?.OpenWindow("quests"));

            // 퀘스트 창 (모달: 전체 화면 배경이 입력을 막는다)
            var q = Rect("QuestsWindow", _uiRoot, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            Tag(q, "ui.quests");
            Img(q, new Color(0, 0, 0, 0.35f), true);
            var qp = Rect("Panel", q, new Vector2(0.3f, 0.25f), new Vector2(0.7f, 0.75f), Vector2.zero, Vector2.zero);
            Img(qp, new Color(0.12f, 0.12f, 0.16f, 0.95f), true);
            Text("Title", qp, "퀘스트", 28, new Vector2(0, 1), new Vector2(1, 1), new Vector2(20, -60), new Vector2(-20, -12), "ui.quests.title");
            _questsBody = Text("Body", qp, "", 22, new Vector2(0, 0), new Vector2(1, 1), new Vector2(20, 70), new Vector2(-20, -70), "ui.quests.body");
            MakeButton("Close", qp, "닫기", new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(-70, 14), new Vector2(70, 60), "ui.quests.close",
                () => _world()?.CloseWindow("quests"));
            _quests = q.gameObject;
            _quests.SetActive(false);

            // 인벤토리 창 (모달)
            var inv = Rect("InventoryWindow", _uiRoot, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            Tag(inv, "ui.inventory");
            Img(inv, new Color(0, 0, 0, 0.35f), true);
            var ip = Rect("Panel", inv, new Vector2(0.2f, 0.15f), new Vector2(0.8f, 0.85f), Vector2.zero, Vector2.zero);
            Img(ip, new Color(0.12f, 0.12f, 0.16f, 0.95f), true);
            Text("Title", ip, "인벤토리", 28, new Vector2(0, 1), new Vector2(1, 1), new Vector2(20, -60), new Vector2(-20, -12), "ui.inventory.title");
            for (int i = 0; i < MaxSlots; i++)
            {
                int k = i;
                float top = -70 - i * 50;
                _invSlots[i] = MakeButton("Slot" + i, ip, "", new Vector2(0, 1), new Vector2(0.45f, 1), new Vector2(20, top - 44), new Vector2(0, top),
                    "ui.inventory.slot." + i, () => { var it = _invSlotItem[k]; if (it != null) _world()?.SelectSlot(it); });
                _invSlotText[i] = _invSlots[i].GetComponentInChildren<TMP_Text>();
                _invSlotText[i].alignment = TextAlignmentOptions.MidlineLeft;
            }
            _invDetail = Text("Detail", ip, "", 20, new Vector2(0.48f, 0.35f), new Vector2(1, 1), new Vector2(10, 0), new Vector2(-20, -70), "ui.inventory.detail");
            _invDetail.alignment = TextAlignmentOptions.TopLeft;
            _invAssign = MakeButton("Assign", ip, "퀵슬롯 1에 등록", new Vector2(0.48f, 0), new Vector2(1, 0), new Vector2(10, 80), new Vector2(-20, 130), "ui.inventory.assign",
                () => _world()?.AssignQuickSlot(0));
            MakeButton("Close", ip, "닫기", new Vector2(0.48f, 0), new Vector2(1, 0), new Vector2(10, 16), new Vector2(-20, 66), "ui.inventory.close",
                () => _world()?.CloseWindow("inventory"));
            _inv = inv.gameObject;
            _inv.SetActive(false);

            // 상점 창 (모달)
            var sh = Rect("ShopWindow", _uiRoot, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            Tag(sh, "ui.shop");
            Img(sh, new Color(0, 0, 0, 0.35f), true);
            var sp = Rect("Panel", sh, new Vector2(0.15f, 0.15f), new Vector2(0.85f, 0.85f), Vector2.zero, Vector2.zero);
            Img(sp, new Color(0.14f, 0.12f, 0.1f, 0.95f), true);
            Text("Title", sp, "상점", 28, new Vector2(0, 1), new Vector2(0.5f, 1), new Vector2(20, -60), new Vector2(0, -12), "ui.shop.title");
            _shopGold = Text("Gold", sp, "", 22, new Vector2(0.5f, 1), new Vector2(1, 1), new Vector2(0, -60), new Vector2(-20, -12), "ui.shop.gold");
            for (int i = 0; i < MaxShopRows; i++)
            {
                int k = i;
                float top = -80 - i * 60;
                _shopRowText[i] = Text("Item" + i, sp, "", 20, new Vector2(0, 1), new Vector2(0.75f, 1), new Vector2(20, top - 50), new Vector2(0, top), "ui.shop.item." + i);
                _shopBuy[i] = MakeButton("Buy" + i, sp, "구매", new Vector2(0.75f, 1), new Vector2(1, 1), new Vector2(10, top - 50), new Vector2(-20, top),
                    "ui.shop.buy." + i, () => { var it = _shopRowItem[k]; if (it != null) _world()?.Buy(it); });
            }
            _shopMsg = Text("Message", sp, "", 22, new Vector2(0, 0), new Vector2(1, 0), new Vector2(20, 76), new Vector2(-20, 120), "ui.shop.message");
            _shopMsg.color = new Color(1f, 0.85f, 0.4f);
            MakeButton("Close", sp, "닫기", new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(-70, 14), new Vector2(70, 60), "ui.shop.close",
                () => _world()?.CloseWindow("shop"));
            _shop = sh.gameObject;
            _shop.SetActive(false);

            // 대화 창 (모달)
            var d = Rect("DialogWindow", _uiRoot, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            Tag(d, "ui.dialog");
            Img(d, new Color(0, 0, 0, 0.35f), true);
            var dp = Rect("Panel", d, new Vector2(0.1f, 0.02f), new Vector2(0.9f, 0.42f), Vector2.zero, Vector2.zero);
            Img(dp, new Color(0.1f, 0.1f, 0.14f, 0.95f), true);
            _dlgSpeaker = Text("Speaker", dp, "", 26, new Vector2(0, 1), new Vector2(1, 1), new Vector2(24, -50), new Vector2(-24, -10), "ui.dialog.speaker");
            _dlgText = Text("Text", dp, "", 24, new Vector2(0, 1), new Vector2(0.6f, 1), new Vector2(24, -230), new Vector2(-12, -56), "ui.dialog.text");
            for (int i = 0; i < MaxChoices; i++)
            {
                int k = i;
                float top = -60 - i * 58;
                _choices[i] = MakeButton("Choice" + i, dp, "", new Vector2(0.6f, 1), new Vector2(1, 1), new Vector2(8, top - 50), new Vector2(-24, top),
                    "ui.dialog.choice." + i, () => _world()?.ChooseDialogue(k));
                _choiceText[i] = _choices[i].GetComponentInChildren<TMP_Text>();
            }
            _dialog = d.gameObject;
            _dialog.SetActive(false);

            // 안내 팝업 (인벤토리를 처음 열 때 위에 뜬다 — 아래 버튼을 가림)
            var tp = Rect("TipPopup", _uiRoot, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            Tag(tp, "ui.tip");
            Img(tp, new Color(0, 0, 0, 0.25f), true);
            var tpp = Rect("Panel", tp, new Vector2(0.35f, 0.35f), new Vector2(0.65f, 0.65f), Vector2.zero, Vector2.zero);
            Img(tpp, new Color(0.2f, 0.25f, 0.35f, 0.98f), true);
            var tt = Text("Text", tpp, "안내: 아이템을 골라 퀵슬롯에 등록하면 전투에서 바로 쓸 수 있습니다.", 20, Vector2.zero, Vector2.one, new Vector2(16, 70), new Vector2(-16, -16), "ui.tip.text");
            tt.alignment = TextAlignmentOptions.TopLeft;
            MakeButton("Ok", tpp, "확인", new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(-60, 12), new Vector2(60, 58), "ui.tip.ok",
                () => _world()?.CloseTip());
            _tip = tp.gameObject;
            _tip.SetActive(false);

            // 전투 표시 (관람용, 관찰 제외 — 전투 중 observe 는 busy)
            var ch = Rect("CombatHud", _uiRoot, new Vector2(0.15f, 0.82f), new Vector2(0.85f, 0.9f), Vector2.zero, Vector2.zero);
            ch.gameObject.AddComponent<QaIgnore>();
            Img(ch, new Color(0.4f, 0.05f, 0.05f, 0.75f), false);
            _combatText = Text("Text", ch, "", 22, Vector2.zero, Vector2.one, new Vector2(16, 0), new Vector2(-16, 0), null);
            _combatText.alignment = TextAlignmentOptions.Center;
            _combatHud = ch.gameObject;
            _combatHud.SetActive(false);

            // 게임 안내 토스트 (관찰 제외 — 같은 내용이 관찰 events 의 notice 사건으로 간다)
            var nt = Rect("NoticeToast", _uiRoot, new Vector2(0.22f, 0.7f), new Vector2(0.78f, 0.78f), Vector2.zero, Vector2.zero);
            nt.gameObject.AddComponent<QaIgnore>();
            Img(nt, new Color(0.1f, 0.25f, 0.15f, 0.88f), false);
            _noticeText = Text("Text", nt, "", 20, Vector2.zero, Vector2.one, new Vector2(14, 0), new Vector2(-14, 0), null);
            _noticeText.alignment = TextAlignmentOptions.Center;
            _notice = nt.gameObject;
            _notice.SetActive(false);

            // 관람용 행동 로그 (관찰 제외)
            var lg = Rect("ActionLog", _uiRoot, new Vector2(0, 0.45f), new Vector2(0.35f, 0.75f), new Vector2(12, 0), Vector2.zero);
            _logRt = lg;
            lg.gameObject.AddComponent<QaIgnore>();
            _log = Text("Lines", lg, "", 16, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero, null);
            _log.raycastTarget = false;
            _log.color = new Color(1, 1, 1, 0.8f);
        }

        static RectTransform Rect(string name, Transform parent, Vector2 aMin, Vector2 aMax, Vector2 oMin, Vector2 oMax)
        {
            var go = new GameObject(name, typeof(RectTransform));
            var rt = (RectTransform)go.transform;
            rt.SetParent(parent, false);
            rt.anchorMin = aMin;
            rt.anchorMax = aMax;
            rt.offsetMin = oMin;
            rt.offsetMax = oMax;
            return rt;
        }

        static void Tag(Transform t, string id)
        {
            var tag = t.gameObject.AddComponent<QaTag>();
            tag.id = id;
            tag.role = QaRole.Ui;
        }

        static Image Img(Transform t, Color c, bool raycast)
        {
            var img = t.gameObject.AddComponent<Image>();
            img.color = c;
            img.raycastTarget = raycast;
            return img;
        }

        static TMP_Text Text(string name, Transform parent, string text, float size, Vector2 aMin, Vector2 aMax, Vector2 oMin, Vector2 oMax, string id)
        {
            var rt = Rect(name, parent, aMin, aMax, oMin, oMax);
            var t = rt.gameObject.AddComponent<TextMeshProUGUI>();
            var f = PlayFont.Get();
            if (f != null) t.font = f;
            t.text = text;
            t.fontSize = size;
            t.color = Color.white;
            t.alignment = TextAlignmentOptions.MidlineLeft;
            t.raycastTarget = false;
            if (id != null) Tag(rt, id);
            return t;
        }

        static Button MakeButton(string name, Transform parent, string label, Vector2 aMin, Vector2 aMax, Vector2 oMin, Vector2 oMax, string id, Action onClick)
        {
            var rt = Rect(name, parent, aMin, aMax, oMin, oMax);
            var img = Img(rt, new Color(0.25f, 0.35f, 0.55f, 1f), true);
            var b = rt.gameObject.AddComponent<Button>();
            b.targetGraphic = img;
            b.onClick.AddListener(() => onClick());
            var t = Text("Label", rt, label, 22, Vector2.zero, Vector2.one, new Vector2(12, 0), new Vector2(-12, 0), null);
            t.alignment = TextAlignmentOptions.Center;
            Tag(rt, id);
            return b;
        }
    }

    /// <summary>한글 TMP 글꼴: OS 글꼴(맑은 고딕)로 동적 글꼴 자산을 만든다. 없으면 TMP 기본.</summary>
    public static class PlayFont
    {
        static TMP_FontAsset _font;
        static bool _tried;

        public static TMP_FontAsset Get()
        {
            if (_tried) return _font;
            _tried = true;
            try
            {
                _font = TMP_FontAsset.CreateFontAsset("Malgun Gothic", "Regular", 48);
            }
            catch (Exception ex)
            {
                Debug.LogWarning("[QA] 한글 글꼴 생성 실패: " + ex.Message);
            }
            if (_font == null) Debug.LogWarning("[QA] Malgun Gothic 없음 → TMP 기본 글꼴 (한글이 네모로 보일 수 있음, 관찰 텍스트에는 영향 없음)");
            return _font;
        }
    }
}
