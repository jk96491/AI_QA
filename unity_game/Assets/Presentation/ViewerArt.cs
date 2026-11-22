// 뷰어 그래픽 리소스: 재질·절차적 메시·캐릭터/보스 모델 (Unity 기본 도형으로 조립).
// 실제 모델로 바꾸려면 BuildBoss / BuildPlayer 만 프리팹 생성으로 교체하면 된다 (Rig 의 Transform 슬롯 유지).
using System.Collections.Generic;
using UnityEngine;

namespace Qa.Presentation
{
    public static class ViewerArt
    {
        static Material _lit, _glow, _fade;

        // 빌드에 셰이더가 포함되도록 Resources/QaView 의 재질을 템플릿으로 쓴다 (에디터 스크립트가 생성).
        static Material Template(ref Material cache, string res, string shader)
        {
            if (cache != null) return cache;
            cache = Resources.Load<Material>("QaView/" + res);
            if (cache == null)
            {
                var s = Shader.Find(shader) ?? Shader.Find("Sprites/Default");
                cache = new Material(s);
            }
            return cache;
        }

        public static Material Lit(Color c, float smooth = 0.25f, float metal = 0f)
        {
            var m = new Material(Template(ref _lit, "Lit", "Standard")) { color = c };
            if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", smooth);
            if (m.HasProperty("_Metallic")) m.SetFloat("_Metallic", metal);
            return m;
        }

        public static Material Glow(Color c, float intensity = 2f)
        {
            var m = new Material(Template(ref _glow, "Glow", "Standard")) { color = c };
            m.EnableKeyword("_EMISSION");
            if (m.HasProperty("_EmissionColor")) m.SetColor("_EmissionColor", c * intensity);
            return m;
        }

        /// <summary>반투명·무광 (바닥 표시, 충격파, 보호막 등).</summary>
        public static Material Fade(Color c)
        {
            var m = new Material(Template(ref _fade, "Fade", "Sprites/Default")) { color = c };
            m.renderQueue = 3000;
            return m;
        }

        public static void SetEmission(Material m, Color c)
        {
            if (m != null && m.HasProperty("_EmissionColor")) m.SetColor("_EmissionColor", c);
        }

        // ------------------------------------------------------------------ 도형
        public static GameObject Prim(PrimitiveType t, Transform parent, Vector3 localPos, Vector3 scale, Material m,
                                      Vector3? euler = null, string name = null)
        {
            var g = GameObject.CreatePrimitive(t);
            var col = g.GetComponent<Collider>();
            if (col != null) Object.Destroy(col);
            if (name != null) g.name = name;
            g.transform.SetParent(parent, false);
            g.transform.localPosition = localPos;
            g.transform.localScale = scale;
            if (euler.HasValue) g.transform.localEulerAngles = euler.Value;
            var r = g.GetComponent<Renderer>();
            r.sharedMaterial = m;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On;
            return g;
        }

        public static Transform Pivot(string name, Transform parent, Vector3 localPos)
        {
            var t = new GameObject(name).transform;
            t.SetParent(parent, false);
            t.localPosition = localPos;
            return t;
        }

        public static GameObject MeshObj(string name, Mesh mesh, Material m, Transform parent = null)
        {
            var g = new GameObject(name);
            if (parent != null) g.transform.SetParent(parent, false);
            g.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = g.AddComponent<MeshRenderer>();
            r.sharedMaterial = m;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            r.receiveShadows = false;
            return g;
        }

        // ------------------------------------------------------------------ 절차적 메시 (XZ 평면)
        static readonly Dictionary<string, Mesh> MeshCache = new Dictionary<string, Mesh>();

        /// <summary>반지름 1 기준 고리 (inner = 안쪽 비율).</summary>
        public static Mesh Ring(float inner, int seg = 72)
        {
            var key = "ring" + inner + "_" + seg;
            if (MeshCache.TryGetValue(key, out var cached)) return cached;
            var v = new Vector3[seg * 2];
            var tri = new int[seg * 6];
            for (int i = 0; i < seg; i++)
            {
                float a = i * Mathf.PI * 2 / seg;
                var d = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                v[i * 2] = d * inner;
                v[i * 2 + 1] = d;
                int n = (i + 1) % seg;
                tri[i * 6 + 0] = i * 2; tri[i * 6 + 1] = n * 2; tri[i * 6 + 2] = i * 2 + 1;
                tri[i * 6 + 3] = i * 2 + 1; tri[i * 6 + 4] = n * 2; tri[i * 6 + 5] = n * 2 + 1;
            }
            var m = new Mesh { name = key, vertices = v, triangles = tri };
            m.RecalculateNormals();
            MeshCache[key] = m;
            return m;
        }

        /// <summary>반지름 1 원판.</summary>
        public static Mesh Disc(int seg = 64)
        {
            var key = "disc" + seg;
            if (MeshCache.TryGetValue(key, out var cached)) return cached;
            var v = new Vector3[seg + 1];
            var tri = new int[seg * 3];
            v[0] = Vector3.zero;
            for (int i = 0; i < seg; i++)
            {
                float a = i * Mathf.PI * 2 / seg;
                v[i + 1] = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                tri[i * 3] = 0; tri[i * 3 + 1] = (i + 1) % seg + 1; tri[i * 3 + 2] = i + 1;
            }
            var m = new Mesh { name = key, vertices = v, triangles = tri };
            m.RecalculateNormals();
            MeshCache[key] = m;
            return m;
        }

        /// <summary>바닥 격자 (선).</summary>
        public static Mesh Grid(float half, float step)
        {
            var verts = new List<Vector3>();
            var idx = new List<int>();
            for (float x = -half; x <= half + 0.01f; x += step)
            {
                idx.Add(verts.Count); verts.Add(new Vector3(x, 0, -half));
                idx.Add(verts.Count); verts.Add(new Vector3(x, 0, half));
                idx.Add(verts.Count); verts.Add(new Vector3(-half, 0, x));
                idx.Add(verts.Count); verts.Add(new Vector3(half, 0, x));
            }
            var m = new Mesh { name = "grid" };
            m.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
            m.SetVertices(verts);
            m.SetIndices(idx.ToArray(), MeshTopology.Lines, 0);
            return m;
        }

        /// <summary>활 (호 모양 납작한 띠, XY 평면).</summary>
        public static Mesh Arc(float radius, float thick, float degrees, int seg = 20)
        {
            var v = new List<Vector3>();
            var tri = new List<int>();
            // 중심이 (-radius, 0) 인 호: 가운데 점이 원점, 양 끝이 위·아래로 휜다
            for (int i = 0; i <= seg; i++)
            {
                float a = Mathf.Deg2Rad * (-degrees / 2 + degrees * i / seg);
                var n = new Vector3(Mathf.Cos(a), Mathf.Sin(a), 0);
                var c = new Vector3(-radius, 0, 0);
                v.Add(c + n * (radius - thick * 0.5f));
                v.Add(c + n * (radius + thick * 0.5f));
                if (i < seg)
                {
                    int b = i * 2;
                    tri.AddRange(new[] { b, b + 2, b + 1, b + 1, b + 2, b + 3, b, b + 1, b + 2, b + 1, b + 3, b + 2 });
                }
            }
            var m = new Mesh { name = "arc" };
            m.SetVertices(v);
            m.SetTriangles(tri, 0);
            m.RecalculateNormals();
            return m;
        }

        /// <summary>XZ 평면 부채꼴 고리 (베기 궤적). 반지름 1, 각도는 +Z 기준 좌우 대칭.</summary>
        public static Mesh Sector(float inner, float degrees, int seg = 24)
        {
            var key = "sector" + inner + "_" + degrees + "_" + seg;
            if (MeshCache.TryGetValue(key, out var cached)) return cached;
            var v = new List<Vector3>();
            var col = new List<Color>();
            var tri = new List<int>();
            for (int i = 0; i <= seg; i++)
            {
                float a = Mathf.Deg2Rad * (-degrees / 2 + degrees * i / seg);
                var d = new Vector3(Mathf.Sin(a), 0, Mathf.Cos(a));
                float edge = Mathf.Sin(Mathf.PI * i / seg);   // 양 끝으로 갈수록 투명
                v.Add(d * inner); col.Add(new Color(1, 1, 1, 0));
                v.Add(d); col.Add(new Color(1, 1, 1, edge));
                if (i < seg)
                {
                    int b = i * 2;
                    tri.AddRange(new[] { b, b + 2, b + 1, b + 1, b + 2, b + 3, b, b + 1, b + 2, b + 1, b + 3, b + 2 });
                }
            }
            var m = new Mesh { name = key };
            m.SetVertices(v);
            m.SetColors(col);
            m.SetTriangles(tri, 0);
            m.RecalculateNormals();
            MeshCache[key] = m;
            return m;
        }

        // ------------------------------------------------------------------ 모델
        public sealed class Rig
        {
            public Transform Root;      // 위치·회전 (지면)
            public Transform Body;      // 숨쉬기·쓰러짐
            public Transform Weapon;    // 공격 휘두르기 회전축
            public Transform Off;       // 보조 손 (방패·화살통)
            public Transform Tip;       // 투사체 출발점
            public Transform Head;
            public Transform ArmL, ArmR;
            public Transform LegL, LegR;   // 걷기 흔들림 (없으면 null)
            public Transform Cape;         // 망토 펄럭임
            public Transform Halo;         // 마법사 발밑 마법진 / 지팡이 고리 (회전)
            public Transform Bow;          // 궁수 활 (당기기)
            public bool Hover;             // 떠다님 (마법사)
            public Renderer TipGlow;
            public readonly List<Renderer> Eyes = new List<Renderer>();
            public readonly List<Renderer> Skin = new List<Renderer>();   // 페이즈 색 변경 대상
            public float Height = 2f;
            public float Radius = 0.5f;
        }

        public static Rig BuildBoss()
        {
            var rig = new Rig { Height = 5.2f, Radius = 1.7f };
            rig.Root = new GameObject("Boss").transform;
            rig.Body = Pivot("body", rig.Root, Vector3.zero);
            var stone = Lit(new Color(0.30f, 0.28f, 0.33f), 0.15f);
            var dark = Lit(new Color(0.16f, 0.15f, 0.18f), 0.1f);
            var eye = Glow(new Color(1f, 0.55f, 0.1f), 4f);

            var torso = Prim(PrimitiveType.Sphere, rig.Body, new Vector3(0, 2.4f, 0), new Vector3(3.0f, 2.8f, 2.4f), stone);
            rig.Skin.Add(torso.GetComponent<Renderer>());
            Prim(PrimitiveType.Sphere, rig.Body, new Vector3(0, 1.2f, 0), new Vector3(2.2f, 1.4f, 1.8f), dark);
            // 다리
            Prim(PrimitiveType.Capsule, rig.Body, new Vector3(-0.8f, 0.6f, 0), new Vector3(0.9f, 0.7f, 0.9f), dark);
            Prim(PrimitiveType.Capsule, rig.Body, new Vector3(0.8f, 0.6f, 0), new Vector3(0.9f, 0.7f, 0.9f), dark);
            // 머리
            rig.Head = Pivot("head", rig.Body, new Vector3(0, 4.1f, 0.25f));
            var head = Prim(PrimitiveType.Sphere, rig.Head, Vector3.zero, new Vector3(1.5f, 1.3f, 1.4f), stone);
            rig.Skin.Add(head.GetComponent<Renderer>());
            Prim(PrimitiveType.Capsule, rig.Head, new Vector3(-0.6f, 0.75f, -0.1f), new Vector3(0.25f, 0.55f, 0.25f), dark, new Vector3(0, 0, 30));
            Prim(PrimitiveType.Capsule, rig.Head, new Vector3(0.6f, 0.75f, -0.1f), new Vector3(0.25f, 0.55f, 0.25f), dark, new Vector3(0, 0, -30));
            rig.Eyes.Add(Prim(PrimitiveType.Sphere, rig.Head, new Vector3(-0.3f, 0.1f, 0.6f), Vector3.one * 0.28f, eye).GetComponent<Renderer>());
            rig.Eyes.Add(Prim(PrimitiveType.Sphere, rig.Head, new Vector3(0.3f, 0.1f, 0.6f), Vector3.one * 0.28f, eye).GetComponent<Renderer>());
            // 팔 (어깨 회전축)
            rig.ArmL = Pivot("armL", rig.Body, new Vector3(-1.7f, 3.3f, 0));
            rig.ArmR = Pivot("armR", rig.Body, new Vector3(1.7f, 3.3f, 0));
            foreach (var arm in new[] { rig.ArmL, rig.ArmR })
            {
                var a = Prim(PrimitiveType.Capsule, arm, new Vector3(0, -1.1f, 0), new Vector3(0.9f, 1.2f, 0.9f), stone);
                rig.Skin.Add(a.GetComponent<Renderer>());
                Prim(PrimitiveType.Sphere, arm, new Vector3(0, -2.3f, 0.1f), new Vector3(1.2f, 1.0f, 1.2f), dark);
            }
            // 등 결정
            var crystal = Glow(new Color(1f, 0.45f, 0.1f), 2.5f);
            rig.Eyes.Add(Prim(PrimitiveType.Cube, rig.Body, new Vector3(0, 3.6f, -1.0f), new Vector3(0.5f, 1.2f, 0.5f), crystal, new Vector3(20, 45, 0)).GetComponent<Renderer>());
            rig.Eyes.Add(Prim(PrimitiveType.Cube, rig.Body, new Vector3(-0.7f, 3.2f, -0.9f), new Vector3(0.35f, 0.8f, 0.35f), crystal, new Vector3(25, 30, 20)).GetComponent<Renderer>());
            rig.Eyes.Add(Prim(PrimitiveType.Cube, rig.Body, new Vector3(0.7f, 3.2f, -0.9f), new Vector3(0.35f, 0.8f, 0.35f), crystal, new Vector3(25, 60, -20)).GetComponent<Renderer>());
            return rig;
        }

        public static Color ClassColor(string cls)
        {
            switch (cls)
            {
                case "warrior": return new Color(0.35f, 0.55f, 0.95f);
                case "mage": return new Color(0.70f, 0.35f, 0.95f);
                case "archer": return new Color(0.35f, 0.85f, 0.40f);
                default: return new Color(0.8f, 0.8f, 0.8f);
            }
        }

        public static Rig BuildPlayer(string cls)
        {
            switch (cls)
            {
                case "warrior": return BuildWarrior();
                case "mage": return BuildMage();
                case "archer": return BuildArcher();
                default: return BuildWarrior();
            }
        }

        static Rig NewRig(string name, float height)
        {
            var rig = new Rig { Height = height, Radius = 0.45f };
            rig.Root = new GameObject(name).transform;
            rig.Body = Pivot("body", rig.Root, Vector3.zero);
            return rig;
        }

        static void Legs(Rig rig, float hipY, float sideX, Vector3 legScale, Material leg, Material boot)
        {
            rig.LegL = Pivot("legL", rig.Body, new Vector3(-sideX, hipY, 0));
            rig.LegR = Pivot("legR", rig.Body, new Vector3(sideX, hipY, 0));
            foreach (var l in new[] { rig.LegL, rig.LegR })
            {
                Prim(PrimitiveType.Capsule, l, new Vector3(0, -hipY * 0.5f, 0), legScale, leg);
                Prim(PrimitiveType.Cube, l, new Vector3(0, -hipY + 0.08f, 0.06f), new Vector3(legScale.x * 1.1f, 0.16f, legScale.z * 1.6f), boot);
            }
        }

        /// <summary>전사: 투구(깃털)·견갑·휘장·망토·장검·카이트 방패. 다부진 체형.</summary>
        static Rig BuildWarrior()
        {
            var rig = NewRig("Warrior", 2.25f);
            var steel = Lit(new Color(0.72f, 0.75f, 0.80f), 0.75f, 0.85f);
            var darkSteel = Lit(new Color(0.35f, 0.37f, 0.42f), 0.6f, 0.8f);
            var blue = Lit(new Color(0.18f, 0.32f, 0.75f), 0.3f);
            var gold = Lit(new Color(0.95f, 0.75f, 0.25f), 0.7f, 0.9f);
            var red = Lit(new Color(0.70f, 0.10f, 0.10f), 0.2f);
            var leather = Lit(new Color(0.33f, 0.22f, 0.13f), 0.25f);
            var skin = Lit(new Color(0.93f, 0.76f, 0.62f), 0.2f);

            Legs(rig, 0.85f, 0.22f, new Vector3(0.34f, 0.45f, 0.34f), darkSteel, darkSteel);
            Prim(PrimitiveType.Capsule, rig.Body, new Vector3(0, 1.35f, 0), new Vector3(0.95f, 0.55f, 0.72f), steel);           // 몸통 갑옷
            Prim(PrimitiveType.Cube, rig.Body, new Vector3(0, 1.30f, 0.30f), new Vector3(0.55f, 0.75f, 0.06f), blue);           // 휘장
            Prim(PrimitiveType.Cube, rig.Body, new Vector3(0, 1.45f, 0.34f), new Vector3(0.18f, 0.18f, 0.04f), gold, new Vector3(0, 0, 45)); // 문장
            Prim(PrimitiveType.Cylinder, rig.Body, new Vector3(0, 1.0f, 0), new Vector3(0.82f, 0.06f, 0.65f), leather);         // 허리띠
            Prim(PrimitiveType.Cube, rig.Body, new Vector3(0, 1.0f, 0.33f), new Vector3(0.16f, 0.12f, 0.05f), gold);            // 버클
            Prim(PrimitiveType.Sphere, rig.Body, new Vector3(-0.55f, 1.78f, 0), new Vector3(0.52f, 0.38f, 0.55f), steel);       // 견갑
            Prim(PrimitiveType.Sphere, rig.Body, new Vector3(0.55f, 1.78f, 0), new Vector3(0.52f, 0.38f, 0.55f), steel);
            rig.Cape = Pivot("cape", rig.Body, new Vector3(0, 1.85f, -0.36f));
            Prim(PrimitiveType.Cube, rig.Cape, new Vector3(0, -0.65f, 0), new Vector3(0.85f, 1.3f, 0.05f), red);

            rig.Head = Pivot("head", rig.Body, new Vector3(0, 2.1f, 0));
            Prim(PrimitiveType.Sphere, rig.Head, Vector3.zero, Vector3.one * 0.48f, skin);
            Prim(PrimitiveType.Sphere, rig.Head, new Vector3(0, 0.03f, -0.01f), new Vector3(0.56f, 0.58f, 0.58f), steel);       // 투구
            Prim(PrimitiveType.Cube, rig.Head, new Vector3(0, 0.0f, 0.27f), new Vector3(0.36f, 0.05f, 0.06f), Lit(Color.black, 0f));   // 눈 틈
            Prim(PrimitiveType.Cube, rig.Head, new Vector3(0, 0.36f, -0.05f), new Vector3(0.07f, 0.22f, 0.45f), red);           // 깃털

            rig.Weapon = Pivot("sword", rig.Body, new Vector3(0.62f, 1.25f, 0.15f));
            Prim(PrimitiveType.Cylinder, rig.Weapon, new Vector3(0, 0.0f, 0), new Vector3(0.07f, 0.13f, 0.07f), leather);       // 손잡이
            Prim(PrimitiveType.Cube, rig.Weapon, new Vector3(0, 0.15f, 0), new Vector3(0.42f, 0.07f, 0.1f), gold);              // 코등이
            Prim(PrimitiveType.Cube, rig.Weapon, new Vector3(0, 0.95f, 0), new Vector3(0.13f, 1.5f, 0.035f), steel);            // 검날
            Prim(PrimitiveType.Sphere, rig.Weapon, new Vector3(0, -0.15f, 0), Vector3.one * 0.1f, gold);
            rig.Tip = Pivot("tip", rig.Weapon, new Vector3(0, 1.7f, 0));

            rig.Off = Pivot("shield", rig.Body, new Vector3(-0.68f, 1.25f, 0.2f));
            Prim(PrimitiveType.Cube, rig.Off, new Vector3(0, 0, 0.05f), new Vector3(0.06f, 0.95f, 0.7f), gold);                 // 테두리
            Prim(PrimitiveType.Cube, rig.Off, new Vector3(-0.02f, 0, 0.05f), new Vector3(0.06f, 0.85f, 0.6f), blue);
            Prim(PrimitiveType.Cube, rig.Off, new Vector3(-0.06f, 0.05f, 0.05f), new Vector3(0.04f, 0.45f, 0.1f), gold);        // 십자
            Prim(PrimitiveType.Cube, rig.Off, new Vector3(-0.06f, 0.12f, 0.05f), new Vector3(0.04f, 0.1f, 0.35f), gold);
            return rig;
        }

        /// <summary>마법사: 3단 로브·뾰족 모자(별)·흰 수염·수정 지팡이, 발밑 마법진 위에 떠 있음.</summary>
        static Rig BuildMage()
        {
            var rig = NewRig("Mage", 2.9f);
            rig.Hover = true;
            var robe = Lit(new Color(0.42f, 0.18f, 0.62f), 0.25f);
            var robeDark = Lit(new Color(0.28f, 0.10f, 0.42f), 0.2f);
            var gold = Lit(new Color(0.95f, 0.78f, 0.3f), 0.7f, 0.9f);
            var skin = Lit(new Color(0.95f, 0.8f, 0.68f), 0.2f);
            var beard = Lit(new Color(0.92f, 0.92f, 0.95f), 0.1f);
            var wood = Lit(new Color(0.40f, 0.26f, 0.14f), 0.25f);
            var crystal = Glow(new Color(0.75f, 0.45f, 1f), 3f);

            Prim(PrimitiveType.Cylinder, rig.Body, new Vector3(0, 0.38f, 0), new Vector3(0.95f, 0.38f, 0.95f), robeDark);       // 로브 아래
            Prim(PrimitiveType.Cylinder, rig.Body, new Vector3(0, 0.03f, 0), new Vector3(0.98f, 0.03f, 0.98f), gold);          // 금테
            Prim(PrimitiveType.Cylinder, rig.Body, new Vector3(0, 0.95f, 0), new Vector3(0.72f, 0.3f, 0.72f), robe);
            Prim(PrimitiveType.Capsule, rig.Body, new Vector3(0, 1.4f, 0), new Vector3(0.62f, 0.4f, 0.55f), robe);              // 상체
            Prim(PrimitiveType.Cylinder, rig.Body, new Vector3(0, 1.12f, 0), new Vector3(0.66f, 0.04f, 0.6f), gold);           // 허리끈
            Prim(PrimitiveType.Capsule, rig.Body, new Vector3(-0.42f, 1.35f, 0.05f), new Vector3(0.28f, 0.38f, 0.28f), robe, new Vector3(0, 0, -18));  // 소매
            rig.Head = Pivot("head", rig.Body, new Vector3(0, 1.95f, 0));
            Prim(PrimitiveType.Sphere, rig.Head, Vector3.zero, Vector3.one * 0.44f, skin);
            Prim(PrimitiveType.Capsule, rig.Head, new Vector3(0, -0.25f, 0.13f), new Vector3(0.28f, 0.25f, 0.18f), beard);     // 수염
            Prim(PrimitiveType.Cylinder, rig.Head, new Vector3(0, 0.2f, 0), new Vector3(1.0f, 0.025f, 1.0f), robeDark);         // 모자 챙
            Prim(PrimitiveType.Cylinder, rig.Head, new Vector3(0, 0.38f, 0), new Vector3(0.5f, 0.17f, 0.5f), robe);
            Prim(PrimitiveType.Cylinder, rig.Head, new Vector3(0, 0.68f, -0.03f), new Vector3(0.34f, 0.17f, 0.34f), robe, new Vector3(-8, 0, 0));
            Prim(PrimitiveType.Cylinder, rig.Head, new Vector3(0, 0.95f, -0.1f), new Vector3(0.18f, 0.15f, 0.18f), robe, new Vector3(-20, 0, 0));
            Prim(PrimitiveType.Cube, rig.Head, new Vector3(0, 1.1f, -0.17f), Vector3.one * 0.12f, Glow(new Color(1f, 0.9f, 0.4f), 3f), new Vector3(0, 45, 45));  // 별

            rig.Weapon = Pivot("staff", rig.Body, new Vector3(0.48f, 1.25f, 0.15f));
            Prim(PrimitiveType.Capsule, rig.Weapon, new Vector3(0, 0, 0), new Vector3(0.26f, 0.2f, 0.26f), robe);               // 손 소매
            Prim(PrimitiveType.Cylinder, rig.Weapon, new Vector3(0, 0.25f, 0), new Vector3(0.07f, 1.25f, 0.07f), wood);
            Prim(PrimitiveType.Sphere, rig.Weapon, new Vector3(0, 1.45f, 0), new Vector3(0.18f, 0.12f, 0.18f), gold);
            var orb = Prim(PrimitiveType.Cube, rig.Weapon, new Vector3(0, 1.7f, 0), new Vector3(0.2f, 0.32f, 0.2f), crystal, new Vector3(0, 45, 0));
            rig.TipGlow = orb.GetComponent<Renderer>();
            rig.Tip = orb.transform;

            rig.Halo = Pivot("circle", rig.Root, new Vector3(0, 0.03f, 0));
            var circleMat = Fade(new Color(0.7f, 0.4f, 1f, 0.45f));
            MeshObj("ring1", Ring(0.93f, 48), circleMat, rig.Halo).transform.localScale = Vector3.one * 1.1f;
            MeshObj("ring2", Ring(0.9f, 6), circleMat, rig.Halo).transform.localScale = Vector3.one * 0.85f;   // 육각
            var r3 = MeshObj("ring3", Ring(0.9f, 6), circleMat, rig.Halo);
            r3.transform.localScale = Vector3.one * 0.85f;
            r3.transform.localEulerAngles = new Vector3(0, 30, 0);
            return rig;
        }

        /// <summary>궁수: 뾰족 두건·망토·스카프·큰 활(시위)·화살통. 날렵한 체형.</summary>
        static Rig BuildArcher()
        {
            var rig = NewRig("Archer", 2.15f);
            var green = Lit(new Color(0.20f, 0.48f, 0.24f), 0.25f);
            var darkGreen = Lit(new Color(0.11f, 0.28f, 0.14f), 0.2f);
            var leather = Lit(new Color(0.45f, 0.30f, 0.17f), 0.3f);
            var darkLeather = Lit(new Color(0.25f, 0.16f, 0.09f), 0.25f);
            var skin = Lit(new Color(0.92f, 0.76f, 0.62f), 0.2f);
            var scarf = Lit(new Color(0.75f, 0.25f, 0.15f), 0.2f);
            var wood = Lit(new Color(0.55f, 0.36f, 0.18f), 0.35f);
            var feather = Lit(new Color(0.95f, 0.95f, 0.9f), 0.1f);

            Legs(rig, 0.9f, 0.16f, new Vector3(0.24f, 0.47f, 0.24f), darkLeather, darkLeather);
            Prim(PrimitiveType.Capsule, rig.Body, new Vector3(0, 1.35f, 0), new Vector3(0.6f, 0.5f, 0.45f), green);            // 몸통
            Prim(PrimitiveType.Cube, rig.Body, new Vector3(0, 1.3f, 0.17f), new Vector3(0.48f, 0.55f, 0.1f), leather);          // 조끼
            Prim(PrimitiveType.Cube, rig.Body, new Vector3(0, 1.3f, 0.0f), new Vector3(0.62f, 0.06f, 0.5f), darkLeather, new Vector3(0, 0, 35));  // 가슴띠
            Prim(PrimitiveType.Cylinder, rig.Body, new Vector3(0, 1.78f, 0), new Vector3(0.48f, 0.08f, 0.45f), scarf);           // 스카프
            rig.Cape = Pivot("cape", rig.Body, new Vector3(0, 1.8f, -0.25f));
            Prim(PrimitiveType.Cube, rig.Cape, new Vector3(0, -0.6f, 0), new Vector3(0.65f, 1.2f, 0.04f), darkGreen);
            // 화살통 + 화살
            var quiver = Pivot("quiver", rig.Body, new Vector3(0.18f, 1.45f, -0.3f));
            quiver.localEulerAngles = new Vector3(15, 0, -20);
            Prim(PrimitiveType.Cylinder, quiver, Vector3.zero, new Vector3(0.2f, 0.35f, 0.2f), leather);
            for (int i = 0; i < 4; i++)
            {
                var x = (i - 1.5f) * 0.045f;
                Prim(PrimitiveType.Cylinder, quiver, new Vector3(x, 0.45f, 0), new Vector3(0.025f, 0.15f, 0.025f), wood);
                Prim(PrimitiveType.Cube, quiver, new Vector3(x, 0.6f, 0), new Vector3(0.02f, 0.12f, 0.07f), feather);
            }

            rig.Head = Pivot("head", rig.Body, new Vector3(0, 2.0f, 0));
            Prim(PrimitiveType.Sphere, rig.Head, new Vector3(0, -0.02f, 0.04f), Vector3.one * 0.42f, skin);
            Prim(PrimitiveType.Sphere, rig.Head, new Vector3(0, 0.04f, -0.04f), new Vector3(0.56f, 0.56f, 0.58f), darkGreen);   // 두건
            Prim(PrimitiveType.Capsule, rig.Head, new Vector3(0, 0.12f, -0.32f), new Vector3(0.18f, 0.22f, 0.18f), darkGreen, new Vector3(-60, 0, 0));  // 두건 끝

            rig.Weapon = Pivot("hand", rig.Body, new Vector3(0.38f, 1.3f, 0.1f));   // 시위 당기는 손
            Prim(PrimitiveType.Sphere, rig.Weapon, Vector3.zero, Vector3.one * 0.14f, skin);
            rig.Off = Pivot("bowHand", rig.Body, new Vector3(-0.42f, 1.35f, 0.35f));
            rig.Bow = rig.Off;
            // 활: 손 위치가 호의 가운데, 양 끝이 위·아래 (YZ 평면, 등이 앞쪽)
            var bow = MeshObj("bow", Arc(0.8f, 0.07f, 130f), wood, rig.Off);
            bow.transform.localEulerAngles = new Vector3(0, -90, 0);
            // 시위 (활 양 끝 사이, 호 중심 쪽으로 물러난 위치)
            float endY = Mathf.Sin(Mathf.Deg2Rad * 65f) * 0.8f;
            float endBack = 0.8f - Mathf.Cos(Mathf.Deg2Rad * 65f) * 0.8f;
            Prim(PrimitiveType.Cube, rig.Off, new Vector3(0, 0, -endBack), new Vector3(0.012f, endY * 2f, 0.012f), feather);
            rig.Tip = Pivot("tip", rig.Off, new Vector3(0, 0, 0.1f));
            return rig;
        }
    }
}
