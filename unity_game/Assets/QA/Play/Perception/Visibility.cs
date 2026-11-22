// 지각 가능성 판정 (PLAY_MODE_REQUEST 3.4).
// 월드: 고정 16:9 가상 카메라 frustum 수학 판정 — 창 크기·렌더러 상태와 무관해 헤드리스·결정성에 안전.
// UI : activeInHierarchy, CanvasGroup alpha, 화면 안, 텍스트 비지 않음. interactable = Selectable + EventSystem 레이캐스트.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Qa.Play.Perception
{
    public static class Visibility
    {
        public const float Fov = 50f, Aspect = 16f / 9f, Near = 0.3f, Far = 40f;
        public static readonly Vector3 CamOffset = new Vector3(0f, 12f, -10f);

        /// <summary>플레이어 위치 → 카메라 자세 (뷰와 지각이 같은 식을 쓴다).</summary>
        public static void CameraPose(Vector3 player, out Vector3 pos, out Quaternion rot)
        {
            pos = player + CamOffset;
            rot = Quaternion.LookRotation(player + Vector3.up * 1.0f - pos, Vector3.up);
        }

        public static Plane[] Frustum(Vector3 player)
        {
            CameraPose(player, out var pos, out var rot);
            var view = Matrix4x4.Scale(new Vector3(1, 1, -1)) * Matrix4x4.TRS(pos, rot, Vector3.one).inverse;
            var proj = Matrix4x4.Perspective(Fov, Aspect, Near, Far);
            return GeometryUtility.CalculateFrustumPlanes(proj * view);
        }

        public static bool InFrustum(Plane[] planes, QaTag tag)
        {
            var p = tag.transform.position;
            var b = new Bounds(new Vector3(p.x, tag.height * 0.5f, p.z), new Vector3(tag.radius * 2, tag.height, tag.radius * 2));
            return GeometryUtility.TestPlanesAABB(planes, b);
        }

        // ------------------------------------------------------------------ UI
        public static float Alpha(Transform t)
        {
            float a = 1f;
            foreach (var g in t.GetComponentsInParent<CanvasGroup>(true))
            {
                a *= g.alpha;
                if (g.ignoreParentGroups) break;
            }
            return a;
        }

        public static Vector2 ScreenCenter(RectTransform rt)
        {
            var c = rt.TransformPoint(rt.rect.center);
            var canvas = rt.GetComponentInParent<Canvas>();
            var cam = canvas != null && canvas.renderMode != RenderMode.ScreenSpaceOverlay ? canvas.worldCamera : null;
            return RectTransformUtility.WorldToScreenPoint(cam, c);
        }

        public static bool OnScreen(RectTransform rt)
        {
            var s = ScreenCenter(rt);
            return s.x >= 0 && s.y >= 0 && s.x <= Screen.width && s.y <= Screen.height;
        }

        public static bool UiPerceivable(Transform t)
        {
            if (!t.gameObject.activeInHierarchy) return false;
            if (t.GetComponentInParent<QaIgnore>() != null) return false;
            var canvas = t.GetComponentInParent<Canvas>();
            if (canvas == null || !canvas.isActiveAndEnabled) return false;
            if (Alpha(t) <= 0.01f) return false;
            return !(t is RectTransform rt) || OnScreen(rt);
        }

        static readonly List<RaycastResult> Hits = new List<RaycastResult>();

        /// <summary>요소 중심에서 레이캐스트한 첫 대상 (없으면 null).</summary>
        public static GameObject FirstHit(RectTransform rt)
        {
            var es = EventSystem.current;
            if (es == null) return null;
            var ped = new PointerEventData(es) { position = ScreenCenter(rt) };
            Hits.Clear();
            es.RaycastAll(ped, Hits);
            return Hits.Count > 0 ? Hits[0].gameObject : null;
        }

        /// <summary>클릭 가능 여부. 가려졌으면 blocker = 가린 오브젝트.</summary>
        public static bool Interactable(Selectable s, out GameObject blocker)
        {
            blocker = null;
            if (!s.IsInteractable()) return false;
            var hit = FirstHit((RectTransform)s.transform);
            if (hit == null) return false;
            if (hit.transform == s.transform || hit.transform.IsChildOf(s.transform)) return true;
            blocker = hit;
            return false;
        }
    }
}
