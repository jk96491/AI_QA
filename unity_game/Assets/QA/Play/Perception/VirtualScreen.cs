// 가상 화면 좌표계 (PLAY_PROTOCOL v0.4 C2): 1280×720, 왼쪽 위 원점, 정수 픽셀. 창 크기·헤드리스와 무관.
// - UI: 실제 화면 좌표를 Screen 크기로 정규화해 가상 화면으로 (CanvasScaler 기준 해상도와 같은 1280×720).
// - 월드: Visibility 의 고정 16:9 가상 카메라 행렬로 투영 (렌더러 없이 수학만 → 결정적).
using UnityEngine;

namespace Qa.Play.Perception
{
    public static class VirtualScreen
    {
        public const int W = 1280, H = 720;

        static Matrix4x4 ViewProj(Vector3 player)
        {
            Visibility.CameraPose(player, out var pos, out var rot);
            var view = Matrix4x4.Scale(new Vector3(1, 1, -1)) * Matrix4x4.TRS(pos, rot, Vector3.one).inverse;
            var proj = Matrix4x4.Perspective(Visibility.Fov, Visibility.Aspect, Visibility.Near, Visibility.Far);
            return proj * view;
        }

        /// <summary>UI 요소의 가상 화면 사각형 [x, y, w, h] (왼쪽 위 원점).</summary>
        public static int[] UiRect(RectTransform rt)
        {
            var c = new Vector3[4];
            rt.GetWorldCorners(c);   // 오버레이 캔버스: 화면 픽셀 (왼쪽 아래 원점)
            float sw = Mathf.Max(1, Screen.width), sh = Mathf.Max(1, Screen.height);
            float x0 = Mathf.Min(c[0].x, c[2].x) / sw * W, x1 = Mathf.Max(c[0].x, c[2].x) / sw * W;
            float y0 = H - Mathf.Max(c[0].y, c[2].y) / sh * H, y1 = H - Mathf.Min(c[0].y, c[2].y) / sh * H;
            return new[] { Mathf.RoundToInt(x0), Mathf.RoundToInt(y0), Mathf.RoundToInt(x1 - x0), Mathf.RoundToInt(y1 - y0) };
        }

        /// <summary>가상 좌표 → 실제 화면 픽셀 (EventSystem 레이캐스트용, 왼쪽 아래 원점).</summary>
        public static Vector2 ToScreen(double vx, double vy) =>
            new Vector2((float)(vx / W * Screen.width), (float)((1.0 - vy / H) * Screen.height));

        /// <summary>월드 점 → 가상 화면 (카메라 앞이고 화면 안일 때만).</summary>
        public static bool WorldToVirtual(Vector3 world, Vector3 player, out Vector2 v)
        {
            var clip = ViewProj(player) * new Vector4(world.x, world.y, world.z, 1f);
            v = Vector2.zero;
            if (clip.w <= 1e-4f) return false;
            float nx = clip.x / clip.w, ny = clip.y / clip.w;
            v = new Vector2((nx * 0.5f + 0.5f) * W, (1f - (ny * 0.5f + 0.5f)) * H);
            return v.x >= 0 && v.x <= W && v.y >= 0 && v.y <= H;
        }

        /// <summary>가상 화면 점을 지나는 시선이 바닥(y=0)과 만나는 점.</summary>
        public static bool VirtualToGround(double vx, double vy, Vector3 player, out Vector3 ground)
        {
            var inv = ViewProj(player).inverse;
            float nx = (float)(vx / W * 2 - 1), ny = (float)((1 - vy / H) * 2 - 1);
            var a = inv * new Vector4(nx, ny, -1f, 1f);
            var b = inv * new Vector4(nx, ny, 1f, 1f);
            Vector3 p0 = new Vector3(a.x, a.y, a.z) / a.w, p1 = new Vector3(b.x, b.y, b.z) / b.w;
            ground = Vector3.zero;
            var d = p1 - p0;
            if (Mathf.Abs(d.y) < 1e-6f) return false;
            float t = -p0.y / d.y;
            if (t < 0) return false;
            ground = p0 + d * t;
            ground.y = 0;
            return true;
        }

        /// <summary>엔티티의 화면 중심(몸 가운데)과 화면상 반지름(px).</summary>
        public static bool EntityScreen(QaTag t, Vector3 player, out Vector2 center, out float radiusPx)
        {
            var p = t.transform.position;
            radiusPx = 0;
            if (!WorldToVirtual(new Vector3(p.x, t.height * 0.5f, p.z), player, out center)) return false;
            if (WorldToVirtual(new Vector3(p.x + Mathf.Max(0.4f, t.radius), t.height * 0.5f, p.z), player, out var edge))
                radiusPx = Mathf.Max(18f, Vector2.Distance(center, edge) * 1.3f);
            else radiusPx = 18f;
            return true;
        }
    }
}
