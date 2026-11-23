// 관찰 생성 (PLAY_PROTOCOL 4.5): semantic = 게임이 정리한 상태, hierarchy = 계층 그대로.
// 둘 다 같은 지각 필터를 쓴다. omniscient 면 숨은 것도 넣고 "hidden": true 로 표시한다.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.Play.World;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Qa.Play.Perception
{
    /// <summary>관찰 대상 장면 (Presentation 쪽 PlayView 가 구현). 로직은 이 인터페이스로만 화면을 본다.</summary>
    public interface IPlayScene
    {
        IReadOnlyList<QaTag> WorldTags { get; }
        Transform UiRoot { get; }
        Vector3 PlayerPosition { get; }
        /// <summary>세계 상태를 화면(월드 오브젝트·UI)에 반영.</summary>
        void Sync(WorldState world);
        /// <summary>전투 표시 (CombatSim 상태를 읽기만 함 — 로직은 화면에 의존하지 않는다).</summary>
        void SyncCombat(WorldState world, EntityState enemy, Qa.Sim.CombatSim sim);
        void EndCombat();
        /// <summary>창 모드 전투 장면 연출기 (없으면 null → 필드 위 간이 표시·헤드리스).</summary>
        ICombatPresenter Presenter { get; }
        /// <summary>필드(지역·필드 카메라·필드 UI) 표시 켜기/끄기 — 전투 장면 전환용.</summary>
        void SetFieldVisible(bool visible);
    }

    /// <summary>
    /// 전투 장면 연출: 세션이 만든 CombatSim 을 받아 연출하며 한 틱씩 진행한다 (Tick 안에서 sim.Step — 트리거 대기도 그 안).
    /// 연출이 판 결과를 바꾸지 않는다: 같은 sim 을 같은 순서로 Step 할 뿐이고, 화면 속도는 틱 수에만 영향.
    /// </summary>
    public interface ICombatPresenter
    {
        /// <param name="barrierNote">보스 결계 안내 문구 (회복·가져간 물약 수) — 화면 표시만</param>
        void Begin(Qa.Sim.CombatSim sim, string cls, string scenario, long seed, string bossTitle, Action<bool> setFieldVisible, string barrierNote);
        /// <summary>한 프레임 진행. 판과 마무리 연출이 끝나면 true.</summary>
        bool Tick(double realDelta, double speed);
        void OnTrigger(int index);
        /// <summary>종료·중단. 필드 표시를 즉시 되돌린다.</summary>
        void End();
    }

    public sealed class SemanticObserver
    {
        public const int MaxEntities = 32;
        readonly IPlayScene _scene;
        readonly bool _omniscient;

        public SemanticObserver(IPlayScene scene, bool omniscient)
        {
            _scene = scene;
            _omniscient = omniscient;
        }

        static double R1(double v) => Math.Round(v, 1);
        static JArray Pos(double x, double z) => new JArray(R1(x), 0.0, R1(z));

        QaTag FindTag(string id)
        {
            foreach (var t in _scene.WorldTags) if (t != null && t.id == id) return t;
            return null;
        }

        bool TagPerceivable(QaTag t, Plane[] fr) =>
            t.gameObject.activeInHierarchy && (t.alwaysKnown || Visibility.InFrustum(fr, t));

        /// <summary>행동용: 엔티티가 지금 지각 가능한가.</summary>
        public bool EntityPerceivable(string id)
        {
            if (_omniscient) return true;
            var t = FindTag(id);
            return t != null && TagPerceivable(t, Visibility.Frustum(_scene.PlayerPosition));
        }

        /// <summary>v0.4: screen.ui[].rect·entities[].screen_pos (가상 화면 1280×720) 를 싣는다.</summary>
        public bool IncludeCoords;

        public JObject Build(WorldState w, int seq)
        {
            var obs = new JObject
            {
                ["type"] = "observation",
                ["seq"] = seq,
                ["game_time"] = Math.Round(w.Time, 2),
                ["player"] = new JObject
                {
                    ["class"] = w.Class, ["zone"] = w.Zone, ["pos"] = Pos(w.PlayerX, w.PlayerZ),
                    ["hp_ratio"] = Math.Round(w.HpRatio, 2), ["level"] = w.Level, ["gold"] = w.Gold,
                    ["state"] = w.Modal == "dialog" ? "dialog" : w.PlayerState,
                    ["quickslots"] = QuickSlots(w),
                },
                ["quests"] = Quests(w),
                ["screen"] = new JObject { ["modal"] = w.TopModal, ["ui"] = UiElements() },
                ["entities"] = Entities(w),
                ["inventory"] = Inventory(w),
            };
            var evs = new JArray();
            foreach (var e in w.DrainEvents()) evs.Add(e.ToWire());
            obs["events"] = evs;
            obs["hidden_included"] = _omniscient;
            return obs;
        }

        static JArray QuickSlots(WorldState w)
        {
            var a = new JArray();
            foreach (var s in w.QuickSlots) a.Add(s);
            return a;
        }

        /// <summary>진행 중(active)·반납 가능(ready) 퀘스트와 목표 진행도.</summary>
        static JArray Quests(WorldState w)
        {
            var arr = new JArray();
            foreach (var q in w.Quests)
            {
                var st = w.QuestStateOf(q);
                if (st != QuestStates.Active && st != QuestStates.Ready) continue;
                var objs = new JArray();
                for (int i = 0; i < q.Def.Objectives.Count; i++)
                {
                    var o = q.Def.Objectives[i];
                    var jo = new JObject
                    {
                        ["id"] = o.Id, ["text"] = o.Text, ["progress"] = new JArray(w.Progress(q, i), w.Target(q, i)),
                        ["done"] = w.Progress(q, i) >= w.Target(q, i),
                    };
                    if (o.HintTargets.Length > 0) jo["hint_targets"] = new JArray(o.HintTargets);
                    else if (o.Target != null) jo["hint_targets"] = new JArray(o.Target);
                    objs.Add(jo);
                }
                arr.Add(new JObject { ["id"] = q.Def.Id, ["title"] = q.Def.Title, ["state"] = st, ["objectives"] = objs });
            }
            return arr;
        }

        static JArray Inventory(WorldState w)
        {
            var arr = new JArray();
            foreach (var s in w.Inventory)
            {
                var d = w.Data.Item(s.Id);
                arr.Add(new JObject
                {
                    ["id"] = s.Id, ["label"] = d.Label, ["count"] = s.Count,
                    ["actions"] = d.Usable ? new JArray("use") : new JArray(),
                });
            }
            return arr;
        }

        JArray Entities(WorldState w)
        {
            var fr = Visibility.Frustum(_scene.PlayerPosition);
            var list = new List<(double d, string id, JObject o)>();
            foreach (var t in _scene.WorldTags)
            {
                if (t == null || t.role == QaRole.Ui) continue;
                bool ok = TagPerceivable(t, fr);
                if (!ok && !_omniscient) continue;
                var p = t.transform.position;
                double d = GridPath.Dist(w.PlayerX, w.PlayerZ, p.x, p.z);
                var o = new JObject
                {
                    ["id"] = t.id, ["role"] = QaTag.RoleName(t.role), ["label"] = t.label,
                    ["pos"] = Pos(p.x, p.z), ["distance"] = R1(d),
                    ["actions"] = new JArray(t.actions), ["tags"] = new JArray(t.tags),
                };
                var mk = w.MarkerFor(t.id);
                if (mk != null) o["marker"] = mk;
                if (IncludeCoords && ok && VirtualScreen.EntityScreen(t, _scene.PlayerPosition, out var sc, out _))
                    o["screen_pos"] = new JArray(Mathf.RoundToInt(sc.x), Mathf.RoundToInt(sc.y));
                if (!ok) o["hidden"] = true;
                list.Add((d, t.id, o));
            }
            list.Sort((a, b) => a.d != b.d ? a.d.CompareTo(b.d) : string.CompareOrdinal(a.id, b.id));
            var arr = new JArray();
            for (int i = 0; i < list.Count && i < MaxEntities; i++) arr.Add(list[i].o);
            return arr;
        }

        // ------------------------------------------------------------------ UI
        public static string SelectableRole(Selectable s)
        {
            if (s is Button) return "button";
            if (s is Toggle) return "toggle";
            if (s is TMP_InputField) return "input";
            if (s is TMP_Dropdown) return "dropdown";
            if (s is Slider) return "slider";
            return "selectable";
        }

        public static string TextUnder(Transform t)
        {
            var parts = new List<string>();
            foreach (var tx in t.GetComponentsInChildren<TMP_Text>(false))
            {
                var s = UiIds.PlainText(tx.text);
                if (s.Length > 0) parts.Add(s);
            }
            return string.Join(" ", parts);
        }

        JArray UiElements()
        {
            var arr = new JArray();
            if (_scene.UiRoot != null) Walk(_scene.UiRoot, arr);
            return arr;
        }

        void Walk(Transform t, JArray arr)
        {
            if (t.GetComponent<QaIgnore>() != null) return;
            var sel = t.GetComponent<Selectable>();
            if (sel != null)
            {
                bool vis = Visibility.UiPerceivable(t);
                if (vis || _omniscient)
                {
                    var o = new JObject { ["id"] = UiIds.Of(t), ["role"] = SelectableRole(sel), ["text"] = TextUnder(t) };
                    o["interactable"] = vis && Visibility.Interactable(sel, out _);
                    if (!vis) o["hidden"] = true;
                    else if (IncludeCoords) o["rect"] = new JArray(VirtualScreen.UiRect((RectTransform)t));
                    arr.Add(o);
                }
                return;   // 버튼 안 글자는 버튼 text 로 합침
            }
            var txt = t.GetComponent<TMP_Text>();
            if (txt != null)
            {
                var s = UiIds.PlainText(txt.text);
                bool vis = s.Length > 0 && Visibility.UiPerceivable(t);
                if (vis || (_omniscient && s.Length > 0))
                {
                    var o = new JObject { ["id"] = UiIds.Of(t), ["role"] = "text", ["text"] = s };
                    if (!vis) o["hidden"] = true;
                    else if (IncludeCoords) o["rect"] = new JArray(VirtualScreen.UiRect((RectTransform)t));
                    arr.Add(o);
                }
            }
            for (int i = 0; i < t.childCount; i++) Walk(t.GetChild(i), arr);
        }
    }

    /// <summary>hierarchy 모드: root 부터 max_depth 까지 {id,name,active,components,text,interactable,children}.</summary>
    public sealed class HierarchyObserver
    {
        readonly IPlayScene _scene;
        readonly bool _omniscient;

        public HierarchyObserver(IPlayScene scene, bool omniscient)
        {
            _scene = scene;
            _omniscient = omniscient;
        }

        /// <summary>id 로 노드 찾기 (UI 트리 → 월드 태그). "ui" 또는 null = UI 루트.</summary>
        public Transform Find(string id)
        {
            if (string.IsNullOrEmpty(id) || id == "ui") return _scene.UiRoot;
            var r = FindIn(_scene.UiRoot, id);
            if (r != null) return r;
            foreach (var t in _scene.WorldTags) if (t != null && t.id == id) return t.transform;
            return null;
        }

        static Transform FindIn(Transform t, string id)
        {
            if (t == null) return null;
            if (UiIds.Of(t) == id) return t;
            for (int i = 0; i < t.childCount; i++)
            {
                var r = FindIn(t.GetChild(i), id);
                if (r != null) return r;
            }
            return null;
        }

        bool Perceivable(Transform t)
        {
            if (t is RectTransform) return Visibility.UiPerceivable(t);
            return t.gameObject.activeInHierarchy;
        }

        public JObject Node(Transform t, int depth)
        {
            var o = new JObject { ["id"] = UiIds.Of(t), ["name"] = t.name, ["active"] = t.gameObject.activeInHierarchy };
            var comps = new JArray();
            foreach (var c in t.GetComponents<Component>())
            {
                if (c == null || c is QaTag) continue;
                comps.Add(c.GetType().Name);
            }
            o["components"] = comps;
            var txt = t.GetComponent<TMP_Text>();
            if (txt != null) o["text"] = UiIds.PlainText(txt.text);
            var sel = t.GetComponent<Selectable>();
            if (sel != null)
            {
                if (txt == null) o["text"] = SemanticObserver.TextUnder(t);
                o["interactable"] = Perceivable(t) && Visibility.Interactable(sel, out _);
            }
            var kids = new JArray();
            if (depth > 0)
                for (int i = 0; i < t.childCount; i++)
                {
                    var c = t.GetChild(i);
                    if (c.GetComponent<QaIgnore>() != null) continue;
                    bool vis = Perceivable(c);
                    if (!vis && !_omniscient) continue;
                    var n = Node(c, depth - 1);
                    if (!vis) n["hidden"] = true;
                    kids.Add(n);
                }
            o["children"] = kids;
            return o;
        }
    }
}
