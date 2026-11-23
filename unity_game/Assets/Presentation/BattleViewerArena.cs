// 2D 아레나 보스 패턴 연출 (0.8.0, BOSS_PATTERN_REQUEST 4장). 로직은 Qa.Sim.Arena — 여기는 그 상태를 읽어 그리기만 한다.
//   낙석: 빨간 경고 원이 windup 동안 차오름 → 착지 바위·먼지·흔들림
//   독 장판: 초록 웅덩이 맥동, 사라지기 2초 전 깜빡임
//   탄막: 발광 투사체
//   돌진: 바닥 직선 경고 띠 → 보스 질주
//   결계: 아레나 경계 원
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.Sim;
using UnityEngine;

namespace Qa.Presentation
{
    public sealed partial class BattleViewer
    {
        sealed class HazardGo
        {
            public GameObject Root, Fill, Ring;
            public Material FillMat, RingMat;
            public bool Seen;
        }

        readonly Dictionary<int, HazardGo> _hazards = new Dictionary<int, HazardGo>();
        GameObject _barrier;
        Material _barrierMat;
        Transform _hazardRoot;

        bool HasArena => _sim != null && _sim.ArenaState != null;

        static Vector3 V(double x, double z, float y = 0f) => new Vector3((float)x, y, (float)z);

        /// <summary>판 시작: 좌표를 아레나에서 가져오고 이전 판 표시를 지운다.</summary>
        void ArenaBegin()
        {
            ClearHazards();
            if (!HasArena)
            {
                if (_barrier != null) _barrier.SetActive(false);
                return;
            }
            var a = _sim.ArenaState;
            _bossTo = _bossFrom = V(a.Bx, a.Bz);
            _playerTo = _playerFrom = V(a.Px, a.Pz);
            _camFocus = (_bossTo + _playerTo) * 0.5f;
            if (_barrier == null)
            {
                _barrierMat = ViewerArt.Fade(new Color(0.45f, 0.65f, 1f, 0.55f));
                _barrier = ViewerArt.MeshObj("Barrier", ViewerArt.Ring(0.96f, 128), _barrierMat, _world);
                _barrier.transform.position = Vector3.up * 0.03f;
            }
            _barrier.transform.localScale = Vector3.one * (float)a.Radius;
            _barrier.SetActive(true);
        }

        /// <summary>StepOnce 대체 (아레나 판): 한 틱 진행 후 좌표·패턴 표시 갱신.</summary>
        void ArenaStepOnce()
        {
            _sim.Step();
            var a = _sim.ArenaState;
            _playerFrom = _playerTo;
            _bossFrom = _bossTo;
            _playerTo = V(a.Px, a.Pz);
            _bossTo = V(a.Bx, a.Bz);
            _leapArc = false;
            ConsumeEvents();
            SyncHazards();
        }

        void ClearHazards()
        {
            foreach (var h in _hazards.Values) if (h.Root != null) Destroy(h.Root);
            _hazards.Clear();
        }

        HazardGo Get(int id, System.Func<HazardGo> make)
        {
            if (!_hazards.TryGetValue(id, out var h)) _hazards[id] = h = make();
            h.Seen = true;
            return h;
        }

        HazardGo MakeCircle(string name, Color fill, Color ring)
        {
            if (_hazardRoot == null) { _hazardRoot = new GameObject("Hazards").transform; _hazardRoot.SetParent(_world, false); }
            var root = new GameObject(name);
            root.transform.SetParent(_hazardRoot, false);
            var h = new HazardGo { Root = root, FillMat = ViewerArt.Fade(fill), RingMat = ViewerArt.Fade(ring) };
            h.Fill = ViewerArt.MeshObj("Fill", ViewerArt.Disc(), h.FillMat, root.transform);
            h.Ring = ViewerArt.MeshObj("Ring", ViewerArt.Ring(0.9f), h.RingMat, root.transform);
            h.Fill.transform.localPosition = Vector3.up * 0.005f;
            return h;
        }

        HazardGo MakeShot()
        {
            if (_hazardRoot == null) { _hazardRoot = new GameObject("Hazards").transform; _hazardRoot.SetParent(_world, false); }
            var go = FxSystem.Orb(new Color(0.75f, 1f, 0.35f), 0.55f, 4f);
            go.transform.SetParent(_hazardRoot, false);
            return new HazardGo { Root = go };
        }

        HazardGo MakeBand()
        {
            if (_hazardRoot == null) { _hazardRoot = new GameObject("Hazards").transform; _hazardRoot.SetParent(_world, false); }
            var root = new GameObject("ChargeBand");
            root.transform.SetParent(_hazardRoot, false);
            var h = new HazardGo { Root = root, FillMat = ViewerArt.Fade(new Color(1f, 0.2f, 0.1f, 0.45f)), RingMat = ViewerArt.Fade(new Color(1f, 0.35f, 0.15f, 0.25f)) };
            h.Ring = ViewerArt.Prim(PrimitiveType.Cube, root.transform, Vector3.zero, Vector3.one, h.RingMat, null, "Band");
            h.Fill = ViewerArt.Prim(PrimitiveType.Cube, root.transform, Vector3.zero, Vector3.one, h.FillMat, null, "Fill");
            return h;
        }

        /// <summary>아레나 상태 → 표시 오브젝트 (id 별로 유지, 사라진 것은 제거).</summary>
        void SyncHazards()
        {
            if (!HasArena) return;
            var a = _sim.ArenaState;
            foreach (var h in _hazards.Values) h.Seen = false;

            foreach (var r in a.Rocks)
            {
                var h = Get(r.Id, () => MakeCircle("Rock", new Color(1f, 0.12f, 0.08f, 0.4f), new Color(1f, 0.3f, 0.15f, 0.95f)));
                float prog = Mathf.Clamp01(1f - (float)(r.Left / r.Total));
                h.Root.transform.position = V(r.X, r.Z, 0.05f);
                h.Ring.transform.localScale = Vector3.one * (float)r.R;
                h.Fill.transform.localScale = Vector3.one * (float)r.R * Mathf.Max(0.05f, prog);
            }
            foreach (var p in a.Pools)
            {
                var h = Get(p.Id, () => MakeCircle("Pool", new Color(0.3f, 0.9f, 0.2f, 0.42f), new Color(0.5f, 1f, 0.3f, 0.8f)));
                h.Root.transform.position = V(p.X, p.Z, 0.035f);
                h.Ring.transform.localScale = Vector3.one * (float)p.R;
                h.Fill.transform.localScale = Vector3.one * (float)p.R;
                h.Root.name = p.Left < 2.0 ? "PoolEnding" : "Pool";
            }
            foreach (var s in a.Shots)
            {
                var h = Get(s.Id, MakeShot);
                h.Root.transform.position = V(s.X, s.Z, 1.2f);
            }
            if (a.ChargeNow != null)
            {
                var c = a.ChargeNow;
                var h = Get(c.Id, MakeBand);
                var dir = new Vector3((float)c.Dx, 0, (float)c.Dz);
                float len = (float)c.Len, prog = Mathf.Clamp01(1f - (float)(c.Left / c.Total));
                h.Root.transform.position = V(c.Sx, c.Sz, 0.04f);
                h.Root.transform.rotation = Quaternion.LookRotation(dir);
                h.Ring.transform.localPosition = new Vector3(0, 0, len / 2);
                h.Ring.transform.localScale = new Vector3((float)c.W, 0.02f, len);
                h.Fill.transform.localPosition = new Vector3(0, 0.005f, len * prog / 2);
                h.Fill.transform.localScale = new Vector3((float)c.W, 0.02f, len * Mathf.Max(0.02f, prog));
            }

            var gone = new List<int>();
            foreach (var kv in _hazards) if (!kv.Value.Seen) gone.Add(kv.Key);
            foreach (var id in gone) { Destroy(_hazards[id].Root); _hazards.Remove(id); }
        }

        /// <summary>매 프레임: 장판 맥동·깜빡임, 결계 일렁임.</summary>
        void AnimateArena(float time)
        {
            if (!HasArena) return;
            foreach (var h in _hazards.Values)
            {
                if (h.FillMat == null || h.Root == null) continue;
                if (h.Root.name == "Pool" || h.Root.name == "PoolEnding")
                {
                    float pulse = 0.36f + Mathf.Sin(time * 4f) * 0.08f;
                    if (h.Root.name == "PoolEnding" && Mathf.Repeat(time * 6f, 1f) < 0.5f) pulse *= 0.3f;
                    var c = h.FillMat.color; c.a = pulse; h.FillMat.color = c;
                }
            }
            if (_barrierMat != null)
            {
                var c = _barrierMat.color; c.a = 0.45f + Mathf.Sin(time * 2f) * 0.12f; _barrierMat.color = c;
            }
        }

        /// <summary>아레나 이벤트 (OnEvent 에서 처리 안 한 종류). 처리했으면 true.</summary>
        bool OnArenaEvent(string kind, JObject pl)
        {
            switch (kind)
            {
                case "projectile_land":
                {
                    var pos = pl["pos"] as JArray;
                    var p = pos != null ? V((double)pos[0], (double)pos[1]) : Vector3.zero;
                    if ((string)pl["kind"] == "rockfall")
                    {
                        float r = pl["radius"] != null ? (float)pl["radius"] : 2f;
                        var rock = ViewerArt.Prim(PrimitiveType.Sphere, _world, p + Vector3.up * 0.5f, Vector3.one * 1.3f, ViewerArt.Lit(new Color(0.42f, 0.36f, 0.3f), 0.05f), null, "Boulder");
                        Destroy(rock, 1.4f);
                        _fx.Shockwave(p + Vector3.up * 0.05f, 0.2f, r * 1.1f, new Color(0.75f, 0.65f, 0.5f, 0.6f), 0.5f);
                        _fx.Burst(p + Vector3.up * 0.4f, new Color(0.8f, 0.7f, 0.55f, 0.7f), 2.2f, 0.45f);
                        _shake = Mathf.Max(_shake, 0.18f);
                    }
                    else if ((bool?)pl["hit"] == true)
                        _fx.Burst(p + Vector3.up * 1.2f, new Color(0.75f, 1f, 0.35f, 0.8f), 1.0f, 0.3f);
                    return true;
                }
                case "player_hit":
                {
                    string src = (string)pl["source"];
                    string label = src == "rockfall" ? "낙석" : src == "volley" ? "탄막" : src == "charge" ? "돌진" : src;
                    _fx.Text(HeadPos(_player), label + " -" + ((double)pl["damage"]).ToString("0"), new Color(1f, 0.45f, 0.35f), 17, 1.1f);
                    _hurtT = 0f;
                    LogLine("<color=#FF8060>" + label + " 피격 " + ((double)pl["damage"]).ToString("0") + "</color>");
                    return true;
                }
                case "dodge":
                    _fx.Text(HeadPos(_player), "회피", new Color(0.55f, 1f, 0.6f), 16, 0.9f);
                    return true;
                case "charge":
                    _fx.Text(BossChest(), "돌진!", new Color(1f, 0.5f, 0.3f), 20, 1.0f);
                    _shake = Mathf.Max(_shake, (bool?)pl["hit"] == true ? 0.4f : 0.2f);
                    return true;
                case "telegraph":
                {
                    var k = (string)pl["kind"];
                    if (k == "rockfall") LogLine("<color=#FF9070>낙석 경고</color>");
                    else if (k == "charge") { LogLine("<color=#FF7050>돌진 준비</color>"); _fx.Text(BossChest(), "돌진 준비", new Color(1f, 0.45f, 0.3f), 17, 1.0f); }
                    else if (k == "volley") _fx.Text(BossChest(), "탄막", new Color(0.75f, 1f, 0.35f), 16, 0.8f);
                    return true;
                }
                case "zone_spawn":
                    LogLine("<color=#80FF60>독 장판</color>");
                    return true;
                case "zone_expire":
                    return true;
            }
            return false;
        }
    }
}
