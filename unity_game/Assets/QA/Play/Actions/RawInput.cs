// 저수준 입력 행동 (PLAY_PROTOCOL v0.4 C4, input_mode "raw") — 비전 없는 computer use 시험용.
// 좌표는 가상 화면 1280×720 (VirtualScreen). id 를 고르지 않고 "그 좌표에 있는 것"이 입력을 받는다:
//   UI → EventSystem 레이캐스트 첫 대상 (가려졌으면 가린 쪽이 받는다), 아니면 월드 물체 → 상호작용/다가가기, 아니면 바닥 → 그 점으로 이동.
// 키는 게임 키 바인딩(KeyMap)대로 WorldState 명령을 부른다. 결과에 hit(맞은 대상 id, 없으면 null).
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.Play.Perception;
using Qa.Play.World;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Qa.Play.Actions
{
    /// <summary>action_result 에 hit 를 싣는 행동.</summary>
    public interface IHitAction
    {
        bool HasHit { get; }
        string Hit { get; }
    }

    /// <summary>게임 키 바인딩 (play_description.keys 로 공개).</summary>
    public static class KeyMap
    {
        public static readonly (string Key, string Does)[] Keys =
        {
            ("i", "인벤토리 열기/닫기"), ("q", "퀘스트 창 열기/닫기"), ("escape", "안내 팝업·창 닫기 (대화 제외)"),
            ("enter", "안내 팝업 확인"), ("e", "상호작용 범위 안 가장 가까운 대상과 상호작용"),
            ("1", "퀵슬롯 1 아이템 사용"), ("2", "퀵슬롯 2 아이템 사용"),
            ("w", "위(앞)로 이동 — key_hold"), ("a", "왼쪽 이동 — key_hold"), ("s", "아래(뒤) 이동 — key_hold"), ("d", "오른쪽 이동 — key_hold"),
        };

        public static bool Known(string k)
        {
            foreach (var x in Keys) if (x.Key == k) return true;
            return false;
        }

        public static JArray ToWire()
        {
            var a = new JArray();
            foreach (var x in Keys) a.Add(new JObject { ["key"] = x.Key, ["does"] = x.Does });
            return a;
        }
    }

    public abstract class RawActionBase : PlayActionBase, IHitAction
    {
        public bool HasHit { get; protected set; }
        public string Hit { get; protected set; }

        protected static double Num(JObject args, string key)
        {
            var t = args[key];
            if (t == null || (t.Type != JTokenType.Integer && t.Type != JTokenType.Float)) throw new ActionArgException("args." + key + " 는 숫자");
            return (double)t;
        }

        protected static void Coord(JObject args, string kx, string ky, out double x, out double y)
        {
            x = Num(args, kx);
            y = Num(args, ky);
            if (x < 0 || x >= VirtualScreen.W || y < 0 || y >= VirtualScreen.H)
                throw new ActionArgException("좌표 (" + x + "," + y + ") 가 화면 밖 — 가상 화면 " + VirtualScreen.W + "x" + VirtualScreen.H + ", 왼쪽 위 원점");
        }

        static readonly List<RaycastResult> Hits = new List<RaycastResult>();

        /// <summary>그 화면 점의 첫 UI 대상 (없으면 null).</summary>
        protected static GameObject UiAt(double vx, double vy)
        {
            var es = EventSystem.current;
            if (es == null) return null;
            var ped = new PointerEventData(es) { position = VirtualScreen.ToScreen(vx, vy) };
            Hits.Clear();
            es.RaycastAll(ped, Hits);
            return Hits.Count > 0 ? Hits[0].gameObject : null;
        }

        protected static string OwnerId(Transform t)
        {
            for (var c = t; c != null; c = c.parent)
                if (c.GetComponent<QaTag>() != null) return UiIds.Of(c);
            return UiIds.Of(t);
        }

        /// <summary>그 화면 점의 월드 엔티티 (지각 가능한 것 중 화면상 가장 가까운 것).</summary>
        protected static QaTag EntityAt(ActionContext ctx, double vx, double vy)
        {
            QaTag best = null;
            float bd = float.PositiveInfinity;
            var v = new Vector2((float)vx, (float)vy);
            foreach (var t in ctx.Scene.WorldTags)
            {
                if (t == null || t.role == QaRole.Ui || !t.gameObject.activeInHierarchy) continue;
                if (ctx.World.Entity(t.id) == null || !ctx.Perceivable(t.id)) continue;
                if (!VirtualScreen.EntityScreen(t, ctx.Scene.PlayerPosition, out var c, out var r)) continue;
                float d = Vector2.Distance(c, v);
                if (d <= r && (d < bd - 1e-4f || (Math.Abs(d - bd) < 1e-4f && string.CompareOrdinal(t.id, best.id) < 0))) { best = t; bd = d; }
            }
            return best;
        }

        /// <summary>포인터 이벤트 (enter→down→up→click→exit) — UiClick 과 같은 경로.</summary>
        protected static void Press(GameObject go, double vx, double vy)
        {
            var es = EventSystem.current;
            var ped = new PointerEventData(es)
            {
                position = VirtualScreen.ToScreen(vx, vy), button = PointerEventData.InputButton.Left, clickCount = 1,
                pointerEnter = go, pointerPress = go, rawPointerPress = go,
            };
            ExecuteEvents.Execute(go, ped, ExecuteEvents.pointerEnterHandler);
            ExecuteEvents.Execute(go, ped, ExecuteEvents.pointerDownHandler);
            ExecuteEvents.Execute(go, ped, ExecuteEvents.pointerUpHandler);
            ExecuteEvents.Execute(go, ped, ExecuteEvents.pointerClickHandler);
            ExecuteEvents.Execute(go, ped, ExecuteEvents.pointerExitHandler);
        }
    }

    /// <summary>다른 행동에 넘겨 진행하는 raw 행동 (클릭 → 이동/상호작용/교전).</summary>
    public abstract class DelegatingRaw : RawActionBase
    {
        IPlayAction _inner;
        public override bool DetectsEncounters => _inner != null && _inner.DetectsEncounters;

        protected ActionStatus Run(IPlayAction inner, ActionContext ctx, JObject args)
        {
            _inner = inner;
            var st = inner.Start(ctx, args);
            ImmediateEncounter = inner.ImmediateEncounter;
            Copy();
            return st;
        }

        public override ActionStatus Step(ActionContext ctx)
        {
            if (_inner == null) return ActionStatus.Done;
            var st = _inner.Step(ctx);
            Copy();
            return st;
        }

        public override ActionStatus OnEncounter()
        {
            var st = _inner.OnEncounter();
            Copy();
            return st;
        }

        void Copy()
        {
            Reason = _inner.Reason;
            ReasonDetail = _inner.ReasonDetail;
            InterruptedBy = _inner.InterruptedBy;
        }
    }

    // ------------------------------------------------------------------ pointer_click
    public sealed class PointerClick : DelegatingRaw
    {
        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            Coord(args, "x", "y", out var x, out var y);
            var button = Str(args, "button", false) ?? "left";
            if (button != "left" && button != "right") throw new ActionArgException("args.button 은 left|right");
            HasHit = true;
            var w = ctx.World;
            var ui = UiAt(x, y);
            if (ui != null)
            {
                Hit = OwnerId(ui.transform);
                var sel = ui.GetComponentInParent<Selectable>();
                if (sel != null && sel.IsInteractable() && button == "left")
                {
                    Hit = OwnerId(sel.transform);
                    Press(sel.gameObject, x, y);
                    w.Emit("ui_clicked", new JObject { ["ui_id"] = Hit, ["x"] = x, ["y"] = y });
                }
                return ActionStatus.Done;   // 비활성 버튼·창 배경을 눌러도 오류가 아니다 (실제 입력처럼 아무 일 없음)
            }
            if (w.Modal != null) { Hit = null; return ActionStatus.Done; }
            var tag = EntityAt(ctx, x, y);
            if (tag != null)
            {
                Hit = tag.id;
                var e = w.Entity(tag.id);
                if (e.Def.Role == "enemy") return Run(new Engage(), ctx, new JObject { ["target"] = tag.id });
                if (w.DistanceTo(e) <= w.Data.Limits.InteractRange && e.Def.Actions.Length > 0)
                    return Run(new Interact(), ctx, new JObject { ["target"] = tag.id, ["verb"] = e.Def.Actions[0] });
                return Run(new MoveTo(), ctx, new JObject { ["target"] = tag.id });   // 멀면 다가가기 (한 번 더 누르면 상호작용)
            }
            Hit = null;
            if (!VirtualScreen.VirtualToGround(x, y, ctx.Scene.PlayerPosition, out var g)) return ActionStatus.Done;
            return Run(new MoveTo(), ctx, new JObject { ["pos"] = new JArray(Math.Round(g.x, 2), 0.0, Math.Round(g.z, 2)) });
        }
    }

    // ------------------------------------------------------------------ pointer_move / drag / text_input
    public sealed class PointerMove : RawActionBase
    {
        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            Coord(args, "x", "y", out var x, out var y);
            HasHit = true;
            var ui = UiAt(x, y);
            if (ui != null) { Hit = OwnerId(ui.transform); return ActionStatus.Done; }
            var tag = ctx.World.Modal == null ? EntityAt(ctx, x, y) : null;
            Hit = tag?.id;
            return ActionStatus.Done;
        }
    }

    public sealed class Drag : RawActionBase
    {
        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            Coord(args, "x0", "y0", out var x0, out var y0);
            Coord(args, "x1", "y1", out var x1, out var y1);
            HasHit = true;
            var from = UiAt(x0, y0);
            Hit = from != null ? OwnerId(from.transform) : null;
            if (from == null) return ActionStatus.Done;
            var es = EventSystem.current;
            var ped = new PointerEventData(es) { position = VirtualScreen.ToScreen(x0, y0), button = PointerEventData.InputButton.Left, pointerDrag = from };
            ExecuteEvents.Execute(from, ped, ExecuteEvents.beginDragHandler);
            ped.position = VirtualScreen.ToScreen(x1, y1);
            ExecuteEvents.Execute(from, ped, ExecuteEvents.dragHandler);
            var to = UiAt(x1, y1);
            if (to != null) ExecuteEvents.Execute(to, ped, ExecuteEvents.dropHandler);
            ExecuteEvents.Execute(from, ped, ExecuteEvents.endDragHandler);
            return ActionStatus.Done;
        }
    }

    public sealed class TextInput : RawActionBase
    {
        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            Str(args, "text", true);
            return Fail("invalid_state", "포커스된 입력 칸 없음 (이 게임에는 입력 칸이 없다)");
        }
    }

    // ------------------------------------------------------------------ key_press
    public sealed class KeyPress : DelegatingRaw
    {
        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            var k = Str(args, "key", true).ToLowerInvariant();
            if (!KeyMap.Known(k) || k == "w" || k == "a" || k == "s" || k == "d")
                throw new ActionArgException("key_press 키 '" + k + "' 없음 (이동 w/a/s/d 는 key_hold). 키 목록: play_description.keys");
            var w = ctx.World;
            switch (k)
            {
                case "i": if (w.Modal == "inventory") w.CloseWindow("inventory"); else w.OpenWindow("inventory"); return ActionStatus.Done;
                case "q": if (w.Modal == "quests") w.CloseWindow("quests"); else w.OpenWindow("quests"); return ActionStatus.Done;
                case "escape":
                    if (w.Tip != null) w.CloseTip();
                    else if (w.Modal != null && w.Modal != "dialog") w.CloseWindow(w.Modal);
                    return ActionStatus.Done;
                case "enter":
                    if (w.Tip != null) w.CloseTip();
                    return ActionStatus.Done;
                case "1":
                case "2":
                {
                    int slot = k == "1" ? 0 : 1;
                    var item = slot < w.QuickSlots.Length ? w.QuickSlots[slot] : null;
                    if (item == null) return Fail("invalid_state", "퀵슬롯 " + k + " 비어 있음");
                    return Run(new UseItem(), ctx, new JObject { ["item_id"] = item });
                }
                case "e":
                {
                    if (w.Modal != null) return Fail("blocked_by_modal", "ui." + w.TopModal);
                    EntityState best = null;
                    double bd = double.PositiveInfinity;
                    foreach (var e in w.Entities)
                    {
                        if (!e.Active || e.Def.Actions.Length == 0 || e.Def.Role == "enemy" || !ctx.Perceivable(e.Id)) continue;
                        double d = w.DistanceTo(e);
                        if (d > w.Data.Limits.InteractRange) continue;
                        if (d < bd - 1e-9 || (Math.Abs(d - bd) < 1e-9 && string.CompareOrdinal(e.Id, best.Id) < 0)) { best = e; bd = d; }
                    }
                    HasHit = true;
                    if (best == null) { Hit = null; return Fail("no_target", "상호작용 범위 안 대상 없음"); }
                    Hit = best.Id;
                    return Run(new Interact(), ctx, new JObject { ["target"] = best.Id, ["verb"] = best.Def.Actions[0] });
                }
            }
            return ActionStatus.Done;
        }
    }

    // ------------------------------------------------------------------ key_hold (w/a/s/d 이동)
    public sealed class KeyHold : RawActionBase
    {
        double _dx, _dz, _seconds, _elapsed;
        public override bool DetectsEncounters => true;

        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            var k = Str(args, "key", true).ToLowerInvariant();
            _seconds = Num(args, "seconds");
            var lim = ctx.World.Data.Limits;
            if (_seconds <= 0 || _seconds > lim.MaxActionSeconds) throw new ActionArgException("args.seconds 는 0 초과 ~" + lim.MaxActionSeconds);
            // 카메라는 항상 +z 를 본다 (Visibility.CamOffset) → 화면 위 = +z
            switch (k)
            {
                case "w": _dx = 0; _dz = 1; break;
                case "s": _dx = 0; _dz = -1; break;
                case "a": _dx = -1; _dz = 0; break;
                case "d": _dx = 1; _dz = 0; break;
                default: throw new ActionArgException("key_hold 키는 w|a|s|d");
            }
            if (ctx.World.Modal != null) return Fail("blocked_by_modal", "ui." + ctx.World.TopModal);
            ctx.World.PlayerState = "moving";
            return ActionStatus.Running;
        }

        public override ActionStatus Step(ActionContext ctx)
        {
            var w = ctx.World;
            var lim = w.Data.Limits;
            double step = lim.MoveSpeed * lim.Dt;
            double nx = w.PlayerX + _dx * step, nz = w.PlayerZ + _dz * step;
            if (!w.Grid.IsFree(nx, nz))
            {
                w.PlayerState = "idle";
                ReasonDetail = "blocked after " + Math.Round(_elapsed, 2) + "s";
                return ActionStatus.Done;
            }
            w.PlayerX = nx;
            w.PlayerZ = nz;
            _elapsed += lim.Dt;
            if (_elapsed >= _seconds - 1e-9) { w.PlayerState = "idle"; return ActionStatus.Done; }
            return ActionStatus.Running;
        }
    }
}
