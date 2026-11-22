// 뷰어 효과: 짧게 살다 사라지는 오브젝트(충격파·폭발·투사체·기둥)와 떠오르는 글자.
// 시간은 '화면 시간'(실제 시간 × 재생 속도)으로 흐른다. 판 로직과 무관.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace Qa.Presentation
{
    public sealed class FxSystem
    {
        sealed class Fx
        {
            public GameObject Go;
            public Material Mat;
            public float Age, Life;
            public Action<Fx, float> Tick;   // (fx, 0..1)
            public Action OnEnd;
            public Color Color;
            public Vector3 A;
        }

        public struct FloatText
        {
            public Vector3 World;
            public string Text;
            public Color Color;
            public float Age, Life;
            public int Size;
            public float Rise;
        }

        readonly List<Fx> _fx = new List<Fx>();
        public readonly List<FloatText> Texts = new List<FloatText>();
        readonly Transform _root;

        public FxSystem(Transform root) { _root = root; }

        public void Clear()
        {
            foreach (var f in _fx) Kill(f);
            _fx.Clear();
            Texts.Clear();
        }

        static readonly HashSet<Material> KillSet = new HashSet<Material>();

        /// <summary>오브젝트와, 효과마다 새로 만든 재질(자식 포함)을 한 번씩 정리.</summary>
        static void Kill(Fx f)
        {
            KillSet.Clear();
            if (f.Mat != null) KillSet.Add(f.Mat);
            if (f.Go != null)
            {
                foreach (var r in f.Go.GetComponentsInChildren<Renderer>(true))
                    if (r.sharedMaterial != null) KillSet.Add(r.sharedMaterial);
                UnityEngine.Object.Destroy(f.Go);
            }
            foreach (var m in KillSet) UnityEngine.Object.Destroy(m);
            KillSet.Clear();
        }

        public void Tick(float dt)
        {
            for (int i = _fx.Count - 1; i >= 0; i--)
            {
                var f = _fx[i];
                f.Age += dt;
                float t = Mathf.Clamp01(f.Age / f.Life);
                f.Tick?.Invoke(f, t);
                if (t >= 1f)
                {
                    f.OnEnd?.Invoke();
                    Kill(f);
                    _fx.RemoveAt(i);
                }
            }
            for (int i = Texts.Count - 1; i >= 0; i--)
            {
                var x = Texts[i];
                x.Age += dt;
                if (x.Age >= x.Life) Texts.RemoveAt(i);
                else Texts[i] = x;
            }
        }

        Fx Add(GameObject go, Material mat, float life, Action<Fx, float> tick, Color c)
        {
            if (go != null) go.transform.SetParent(_root, true);
            var f = new Fx { Go = go, Mat = mat, Life = Mathf.Max(0.05f, life), Tick = tick, Color = c };
            _fx.Add(f);
            tick?.Invoke(f, 0f);
            return f;
        }

        static void Alpha(Fx f, float a)
        {
            var c = f.Color;
            c.a *= a;
            f.Mat.color = c;
        }

        // ------------------------------------------------------------------ 효과 모음
        public void Text(Vector3 world, string text, Color color, int size = 18, float life = 1.1f, float rise = 1.6f)
        {
            Texts.Add(new FloatText { World = world, Text = text, Color = color, Life = life, Size = size, Rise = rise });
        }

        /// <summary>화면 시간 delay 뒤에 action 실행.</summary>
        public void Delay(float delay, Action action)
        {
            var f = Add(null, null, Mathf.Max(0.01f, delay), null, Color.clear);
            f.OnEnd = action;
        }

        /// <summary>바닥에 퍼지는 고리.</summary>
        public void Shockwave(Vector3 center, float fromR, float toR, Color c, float life, float inner = 0.85f)
        {
            var mat = ViewerArt.Fade(c);
            var go = ViewerArt.MeshObj("shock", ViewerArt.Ring(inner), mat);
            go.transform.position = center + Vector3.up * 0.06f;
            Add(go, mat, life, (f, t) =>
            {
                float r = Mathf.Lerp(fromR, toR, 1f - (1f - t) * (1f - t));
                f.Go.transform.localScale = new Vector3(r, 1, r);
                Alpha(f, 1f - t);
            }, c);
        }

        /// <summary>커지며 사라지는 구 (폭발·타격).</summary>
        public void Burst(Vector3 pos, Color c, float size, float life)
        {
            var mat = ViewerArt.Fade(c);
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            UnityEngine.Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = mat;
            go.transform.position = pos;
            Add(go, mat, life, (f, t) =>
            {
                f.Go.transform.localScale = Vector3.one * Mathf.Lerp(size * 0.3f, size, Mathf.Sqrt(t));
                Alpha(f, 1f - t);
            }, c);
        }

        /// <summary>빛기둥 (부활·물약).</summary>
        public void Pillar(Vector3 pos, Color c, float height, float radius, float life)
        {
            var mat = ViewerArt.Fade(c);
            var go = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            UnityEngine.Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = mat;
            go.transform.position = pos + Vector3.up * height * 0.5f;
            Add(go, mat, life, (f, t) =>
            {
                float w = radius * (1f - t * 0.6f);
                f.Go.transform.localScale = new Vector3(w, height * 0.5f * (0.4f + t), w);
                Alpha(f, Mathf.Sin(t * Mathf.PI));
            }, c);
        }

        /// <summary>from → to(t) 로 날아가는 발광 구. 도착하면 onHit.</summary>
        public void Projectile(Vector3 from, Func<Vector3> to, Color c, float size, float life, float arc, Action onHit)
        {
            var mat = ViewerArt.Glow(c, 3f);
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            UnityEngine.Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = mat;
            go.transform.localScale = Vector3.one * size;
            var f = Add(go, mat, life, null, c);
            f.A = from;
            f.Tick = (x, t) =>
            {
                var target = to();
                var p = Vector3.Lerp(x.A, target, t) + Vector3.up * (arc * 4f * t * (1f - t));
                x.Go.transform.position = p;
            };
            f.OnEnd = onHit;
            f.Tick(f, 0f);
        }

        /// <summary>하늘에서 떨어지는 운석 → 착탄 시 onHit.</summary>
        public void Meteor(Func<Vector3> target, float life, Action onHit)
        {
            var c = new Color(1f, 0.45f, 0.1f);
            var mat = ViewerArt.Glow(c, 5f);
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            UnityEngine.Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = mat;
            go.transform.localScale = Vector3.one * 1.6f;
            var f = Add(go, mat, life, null, c);
            f.Tick = (x, t) =>
            {
                var p = target() + new Vector3(-6f, 18f, 4f) * (1f - t) + Vector3.up * 2.5f;
                x.Go.transform.position = p;
                x.Go.transform.localScale = Vector3.one * Mathf.Lerp(0.8f, 1.8f, t);
            };
            f.OnEnd = onHit;
            f.Tick(f, 0f);
        }

        /// <summary>대상 주변을 도는 칼날 고리 (칼날폭풍).</summary>
        public void Spin(Func<Vector3> center, Color c, float radius, float life)
        {
            var mat = ViewerArt.Fade(c);
            var go = ViewerArt.MeshObj("spin", ViewerArt.Ring(0.7f, 6), mat);
            Add(go, mat, life, (f, t) =>
            {
                f.Go.transform.position = center() + Vector3.up * 1.1f;
                f.Go.transform.localScale = new Vector3(radius, 1, radius);
                f.Go.transform.Rotate(0, 900f * Time.deltaTime, 0, Space.World);
                Alpha(f, Mathf.Sin(t * Mathf.PI));
            }, c);
        }

        /// <summary>베기 궤적: 바라보는 방향(forward) 기준 부채꼴이 휘둘러지며 사라진다.</summary>
        public void Slash(Func<Vector3> center, Func<Quaternion> facing, float radius, float degrees, float tiltZ, Color c, float life, bool reverse = false)
        {
            var mat = ViewerArt.Fade(c);
            var go = ViewerArt.MeshObj("slash", ViewerArt.Sector(0.55f, degrees), mat);
            Add(go, mat, life, (f, t) =>
            {
                float sweep = Mathf.Lerp(-degrees * 0.6f, degrees * 0.6f, Mathf.SmoothStep(0, 1, Mathf.Min(1f, t * 1.6f))) * (reverse ? -1 : 1);
                f.Go.transform.SetPositionAndRotation(center(), facing() * Quaternion.Euler(0, sweep, tiltZ));
                f.Go.transform.localScale = new Vector3(radius, 1, radius) * (0.85f + t * 0.25f);
                Alpha(f, 1f - t * t);
            }, c);
        }

        /// <summary>발사체 (visual 은 진행 방향을 바라봄 = +Z). trail.a > 0 이면 꼬리 입자.</summary>
        public void Shot(GameObject visual, Vector3 from, Func<Vector3> to, float life, float arc, Color trail, float trailSize, Action onHit)
        {
            var f = Add(visual, null, life, null, trail);
            f.A = from;
            Vector3 last = from;
            float trailAcc = 0f;
            f.Tick = (x, t) =>
            {
                var target = to();
                var p = Vector3.Lerp(x.A, target, t) + Vector3.up * (arc * 4f * t * (1f - t));
                var d = p - last;
                if (d.sqrMagnitude > 1e-6f) x.Go.transform.rotation = Quaternion.LookRotation(d);
                x.Go.transform.position = p;
                trailAcc += d.magnitude;
                if (trail.a > 0 && trailAcc > 0.25f)
                {
                    trailAcc = 0f;
                    Burst(p, trail, trailSize, 0.25f);
                }
                last = p;
            };
            f.OnEnd = onHit;
            f.Tick(f, 0f);
        }

        /// <summary>화살 모양 (+Z 방향).</summary>
        public static GameObject Arrow(Color glow, float length = 0.9f)
        {
            var root = new GameObject("arrow");
            var shaft = ViewerArt.Glow(glow, 1.5f);
            ViewerArt.Prim(PrimitiveType.Cylinder, root.transform, Vector3.zero, new Vector3(0.04f, length * 0.5f, 0.04f), shaft, new Vector3(90, 0, 0));
            ViewerArt.Prim(PrimitiveType.Cube, root.transform, new Vector3(0, 0, length * 0.5f), new Vector3(0.09f, 0.09f, 0.18f), ViewerArt.Glow(Color.white, 2f), new Vector3(0, 0, 45));
            ViewerArt.Prim(PrimitiveType.Cube, root.transform, new Vector3(0, 0, -length * 0.45f), new Vector3(0.02f, 0.14f, 0.16f), ViewerArt.Lit(Color.white));
            return root;
        }

        /// <summary>빛나는 구 (마력탄·화염구).</summary>
        public static GameObject Orb(Color c, float size, float intensity = 3f)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            UnityEngine.Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = ViewerArt.Glow(c, intensity);
            go.transform.localScale = Vector3.one * size;
            return go;
        }

        /// <summary>바닥 마법진 (두 고리 + 육각형이 반대로 돈다).</summary>
        public void MagicCircle(Func<Vector3> center, float radius, Color c, float life)
        {
            var mat = ViewerArt.Fade(c);
            var root = new GameObject("magicCircle");
            ViewerArt.MeshObj("r1", ViewerArt.Ring(0.94f, 64), mat, root.transform);
            var r2 = ViewerArt.MeshObj("r2", ViewerArt.Ring(0.92f, 64), mat, root.transform);
            r2.transform.localScale = Vector3.one * 0.78f;
            var h1 = ViewerArt.MeshObj("h1", ViewerArt.Ring(0.9f, 6), mat, root.transform);
            h1.transform.localScale = Vector3.one * 0.74f;
            var h2 = ViewerArt.MeshObj("h2", ViewerArt.Ring(0.9f, 3), mat, root.transform);
            h2.transform.localScale = Vector3.one * 0.74f;
            Add(root, mat, life, (f, t) =>
            {
                f.Go.transform.position = center() + Vector3.up * 0.05f;
                float grow = Mathf.Min(1f, t * 5f);
                f.Go.transform.localScale = Vector3.one * radius * grow;
                f.Go.transform.rotation = Quaternion.Euler(0, t * 180f, 0);
                h1.transform.localRotation = Quaternion.Euler(0, -t * 540f, 0);
                h2.transform.localRotation = Quaternion.Euler(0, t * 360f, 0);
                Alpha(f, t < 0.85f ? 1f : (1f - t) / 0.15f);
            }, c);
        }

        /// <summary>대상 주위를 도는 칼날들 (칼날폭풍).</summary>
        public void Orbit(Func<Vector3> center, int count, float radius, Color c, float life)
        {
            var root = new GameObject("orbit");
            var mat = ViewerArt.Glow(c, 2f);
            for (int i = 0; i < count; i++)
            {
                var pivot = new GameObject("b").transform;
                pivot.SetParent(root.transform, false);
                pivot.localRotation = Quaternion.Euler(0, 360f * i / count, 0);
                ViewerArt.Prim(PrimitiveType.Cube, pivot, new Vector3(0, 0, radius), new Vector3(0.08f, 0.35f, 1.1f), mat, new Vector3(0, 0, 70));
            }
            var trailMat = ViewerArt.Fade(new Color(c.r, c.g, c.b, 0.35f));
            var ring = ViewerArt.MeshObj("whirl", ViewerArt.Ring(0.75f), trailMat, root.transform);
            ring.transform.localScale = Vector3.one * (radius + 0.6f);
            Add(root, mat, life, (f, t) =>
            {
                f.Go.transform.position = center() + Vector3.up * 1.1f;
                f.Go.transform.rotation = Quaternion.Euler(0, t * life * 1080f, 0);
                f.Go.transform.localScale = Vector3.one * Mathf.Min(1f, t * 6f);
            }, c);
        }

        /// <summary>두 점을 잇는 빛줄기 (조준선).</summary>
        public void Beam(Func<Vector3> from, Func<Vector3> to, Color c, float width, float life)
        {
            var mat = ViewerArt.Fade(c);
            var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            UnityEngine.Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = mat;
            Add(go, mat, life, (f, t) =>
            {
                var a = from();
                var b = to();
                var d = b - a;
                if (d.sqrMagnitude < 1e-4f) return;
                f.Go.transform.SetPositionAndRotation((a + b) * 0.5f, Quaternion.LookRotation(d));
                float w = width * (0.6f + 0.4f * Mathf.Sin(t * 40f));
                f.Go.transform.localScale = new Vector3(w, w, d.magnitude);
                Alpha(f, Mathf.Min(1f, t * 4f) * (t < 0.9f ? 1f : (1f - t) * 10f));
            }, c);
        }

        /// <summary>사방으로 튀는 불꽃 조각.</summary>
        public void Sparks(Vector3 pos, Color c, int n, float speed, float life)
        {
            for (int i = 0; i < n; i++)
            {
                var mat = ViewerArt.Glow(c, 3f);
                var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
                UnityEngine.Object.Destroy(go.GetComponent<Collider>());
                go.GetComponent<Renderer>().sharedMaterial = mat;
                var v = (UnityEngine.Random.onUnitSphere + Vector3.up * 0.8f).normalized * speed * UnityEngine.Random.Range(0.5f, 1f);
                var f = Add(go, mat, life * UnityEngine.Random.Range(0.6f, 1f), null, c);
                f.A = pos;
                f.Tick = (x, t) =>
                {
                    float tt = t * x.Life;
                    x.Go.transform.position = x.A + v * tt + Vector3.down * 9f * tt * tt;
                    x.Go.transform.localScale = Vector3.one * 0.12f * (1f - t);
                    x.Go.transform.rotation = Quaternion.Euler(t * 720f, t * 500f, 0);
                };
                f.Tick(f, 0f);
            }
        }

        /// <summary>대상 위치에서 위로 솟는 빛 입자 (시전 모으기·회복).</summary>
        public void Gather(Func<Vector3> center, Color c, float radius, float life, int n = 10)
        {
            for (int i = 0; i < n; i++)
            {
                float a = i * Mathf.PI * 2 / n;
                float delay = (float)i / n;
                var off = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a)) * radius;
                var go = Orb(c, 0.12f, 4f);
                var f = Add(go, go.GetComponent<Renderer>().sharedMaterial, life, null, c);
                f.Tick = (x, t) =>
                {
                    float k = Mathf.Repeat(t * 2f + delay, 1f);
                    x.Go.transform.position = center() + Vector3.Lerp(off, Vector3.zero, k) + Vector3.up * (k * 0.6f);
                    x.Go.transform.localScale = Vector3.one * 0.14f * (1f - k * 0.5f);
                };
                f.Tick(f, 0f);
            }
        }

        /// <summary>잔상 (회피·점멸).</summary>
        public void Ghost(Vector3 pos, Quaternion rot, Color c, float life)
        {
            var mat = ViewerArt.Fade(c);
            var go = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            UnityEngine.Object.Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = mat;
            go.transform.SetPositionAndRotation(pos + Vector3.up * 0.95f, rot);
            go.transform.localScale = new Vector3(0.8f, 0.85f, 0.6f);
            Add(go, mat, life, (f, t) => Alpha(f, 1f - t), c);
        }
    }
}
