// ui_click: 요소 중심 화면 좌표로 EventSystem 포인터 이벤트(enter→down→up→click)를 보낸다.
// onClick.Invoke() 를 직접 부르지 않는다 — 가림 버그를 놓치지 않기 위해. 실제 처리(대화 선택 등)는 버튼 → WorldState.
using Newtonsoft.Json.Linq;
using Qa.Play.Perception;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Qa.Play.Actions
{
    public sealed class UiClick : PlayActionBase
    {
        readonly HierarchyObserver _finder;

        public UiClick(HierarchyObserver finder) { _finder = finder; }

        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            var id = Str(args, "ui_id", true);
            var t = id == "ui" ? null : _finder.Find(id);
            if (t == null || !(t is RectTransform) || !Visibility.UiPerceivable(t)) return Fail("unknown_target", id);
            var sel = t.GetComponent<Selectable>();
            if (sel == null) return Fail("not_interactable", "not a selectable");
            if (!sel.IsInteractable()) return Fail("not_interactable", "disabled");
            if (!Visibility.Interactable(sel, out var blocker))
                return Fail("not_interactable", blocker != null ? "blocked by " + UiIds.Of(Owner(blocker.transform)) : "no raycast hit");

            var es = EventSystem.current;
            var ped = new PointerEventData(es)
            {
                position = Visibility.ScreenCenter((RectTransform)t),
                button = PointerEventData.InputButton.Left,
                clickCount = 1,
            };
            var go = t.gameObject;
            ped.pointerEnter = go;
            ped.pointerPress = go;
            ped.rawPointerPress = go;
            ExecuteEvents.Execute(go, ped, ExecuteEvents.pointerEnterHandler);
            ExecuteEvents.Execute(go, ped, ExecuteEvents.pointerDownHandler);
            ExecuteEvents.Execute(go, ped, ExecuteEvents.pointerUpHandler);
            ExecuteEvents.Execute(go, ped, ExecuteEvents.pointerClickHandler);
            ExecuteEvents.Execute(go, ped, ExecuteEvents.pointerExitHandler);
            ctx.World.Emit("ui_clicked", new JObject { ["ui_id"] = id });
            return ActionStatus.Done;
        }

        /// <summary>가린 오브젝트를 보고할 id: QaTag 가 붙은 가장 가까운 조상 (창 배경 등).</summary>
        static Transform Owner(Transform t)
        {
            for (var c = t; c != null; c = c.parent)
                if (c.GetComponent<QaTag>() != null) return c;
            return t;
        }
    }
}
