// 2D 원형 아레나 + 위치 기반 보스 패턴 (0.8.0, BOSS_PATTERN_REQUEST). 보스 spec.arena_radius > 0 일 때만 CombatSim 이 만든다.
//
// - 기존 1차원 규칙(사거리·내려찍기·도약·카이팅)은 그대로 "거리" 로 동작한다. 아레나는 두 점 좌표를 들고
//   거리가 바뀌면 (플레이어가 움직였으면 플레이어를, 보스가 움직였으면 보스를) 두 점을 잇는 선 위에서 옮긴다.
// - 패턴: B1 낙석(경고 원 → 착지), B2 독 장판(지속 지대), B3 부채꼴 탄막(직진 투사체), B4 돌진(직선 경고 띠 → 질주+넉백),
//   B6 페이즈 조합(phase_cooldown_mult, combo_phase_min 부터 낙석+장판). B5 하울링 = 기존 광역기(aoe_*) 그대로.
// - 위험도 Danger(0~1) = min(1, DangerGain × 예상 피해 / 현재 체력) — BT 생존 블록 필요도에 더해진다.
//   안전 지점 = 후보 8방향 × 2거리 중 위험 0 이고 보스와의 거리가 지금과 가장 비슷한 점 (동점이면 고정 순서) → 결정적.
// - 난수는 판의 Rng 하나 (무작위 낙석 위치만). 꺼진 보스는 이 클래스가 없으므로 난수 소비도 0.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.Data;

namespace Qa.Sim
{
    public sealed class Arena
    {
        const double Eps = SimConst.Eps;
        public const double DangerGain = 10.0;
        public const double ShotHitRadius = 0.7;
        public const int MaxEach = 16;          // 종류별 동시 개수 상한 (속도)
        public const double DangerHorizon = 1.5; // 탄이 이 시간 안에 닿을 경로면 위험

        public sealed class Rock { public int Id; public double X, Z, R, Left, Total; public bool Aimed; }
        public sealed class Pool { public int Id; public double X, Z, R, Left, Total; }
        public sealed class Shot { public int Id, Volley; public double X, Z, Vx, Vz; }
        public sealed class Charge { public int Id; public double Sx, Sz, Dx, Dz, Len, W, Left, Total; }

        readonly BossSpec _s;
        readonly Rng _rng;
        readonly EventLog _log;
        public readonly double Radius;
        public double Px, Pz, Bx, Bz;

        public readonly List<Rock> Rocks = new List<Rock>();
        public readonly List<Pool> Pools = new List<Pool>();
        public readonly List<Shot> Shots = new List<Shot>();
        public Charge ChargeNow;
        double _rockCd, _poolCd, _volleyCd, _chargeCd;
        int _nextId;
        readonly HashSet<int> _volleyHit = new HashSet<int>();   // 이미 맞힌 탄막 (한 번의 탄막은 한 발만 맞는다 — 틈 사이 판정)

        public double Danger { get; private set; }
        public double SafeX, SafeZ;

        // 집계 (보고서·화면용, 결과 JSON 에는 넣지 않는다 — 프로토콜 불변)
        public readonly Dictionary<string, int> Spawned = new Dictionary<string, int>(StringComparer.Ordinal);
        public readonly Dictionary<string, int> Hits = new Dictionary<string, int>(StringComparer.Ordinal);

        /// <summary>(종류, 원 피해) → 실제 받은 피해. CombatSim 이 방어 계산·집계.</summary>
        public Func<string, double, double> OnHit;

        public Arena(BossSpec s, Rng rng, EventLog log, double startDistance)
        {
            _s = s;
            _rng = rng;
            _log = log;
            Radius = s.ArenaRadius;
            Bx = 0; Bz = 0;
            Px = 0; Pz = -Math.Min(startDistance, Radius - 0.5);
            _rockCd = s.RockfallCooldown * 0.5;
            _poolCd = s.PoolCooldown * 0.5;
            _volleyCd = s.VolleyCooldown * 0.5;
            _chargeCd = s.ChargeCooldown * 0.5;
        }

        public double Distance => Len(Px - Bx, Pz - Bz);
        static double Len(double x, double z) => Math.Sqrt(x * x + z * z);
        bool Inside(double x, double z, double margin) => Len(x, z) <= Radius - margin + Eps;

        void Count(Dictionary<string, int> d, string k) { d.TryGetValue(k, out var n); d[k] = n + 1; }

        // ------------------------------------------------------------------ 거리 ↔ 좌표
        void Dir(out double ux, out double uz)
        {
            double dx = Px - Bx, dz = Pz - Bz, l = Len(dx, dz);
            if (l < 1e-6) { ux = 0; uz = -1; return; }
            ux = dx / l; uz = dz / l;
        }

        /// <summary>플레이어가 움직여 거리가 d 가 됐다: 보스 기준 같은 방향으로 놓고, 경계 밖이면 보스 둘레로 돌아 안쪽 방향을 찾는다.</summary>
        public double PlayerMoved(double d)
        {
            if (Math.Abs(d - Distance) < 1e-9) return d;
            Dir(out var ux, out var uz);
            if (!Inside(Bx + ux * d, Bz + uz * d, 0.5))
            {
                bool found = false;
                for (int k = 1; k <= 45 && !found; k++)
                {
                    foreach (int sg in new[] { 1, -1 })
                    {
                        double a = sg * k * 4.0 * Math.PI / 180.0, c = Math.Cos(a), sn = Math.Sin(a);
                        double rx = ux * c - uz * sn, rz = ux * sn + uz * c;
                        if (Inside(Bx + rx * d, Bz + rz * d, 0.5)) { ux = rx; uz = rz; found = true; break; }
                    }
                }
            }
            Px = Bx + ux * d;
            Pz = Bz + uz * d;
            Clamp(ref Px, ref Pz, 0.5);
            return Distance;
        }

        /// <summary>보스가 움직여 거리가 d 가 됐다.</summary>
        public double BossMoved(double d)
        {
            if (Math.Abs(d - Distance) < 1e-9) return d;
            Dir(out var ux, out var uz);
            Bx = Px - ux * d;
            Bz = Pz - uz * d;
            Clamp(ref Bx, ref Bz, 1.0);
            return Distance;
        }

        void Clamp(ref double x, ref double z, double margin)
        {
            double l = Len(x, z), r = Radius - margin;
            if (l > r && l > 1e-9) { x *= r / l; z *= r / l; }
        }

        /// <summary>이동기(구르기·순간이동): 안전 지점 쪽으로 최대 dist 만큼 즉시. 위험이 없으면 보스 반대쪽으로. 새 거리 반환.</summary>
        public double Dash(double dist)
        {
            double tx = SafeX, tz = SafeZ;
            if (Danger <= Eps) { Dir(out var ux, out var uz); tx = Px + ux * dist; tz = Pz + uz * dist; }
            double dx = tx - Px, dz = tz - Pz, l = Len(dx, dz);
            if (l > dist && l > 1e-9) { dx *= dist / l; dz *= dist / l; }
            Px += dx; Pz += dz;
            Clamp(ref Px, ref Pz, 0.5);
            return Distance;
        }

        /// <summary>회피 이동: 안전 지점 쪽으로 speed·dt. 새 거리 반환.</summary>
        public double MoveToSafe(double speed, double dt)
        {
            double dx = SafeX - Px, dz = SafeZ - Pz, l = Len(dx, dz), step = speed * dt;
            if (l <= step || l < 1e-9) { Px = SafeX; Pz = SafeZ; }
            else { Px += dx / l * step; Pz += dz / l * step; }
            Clamp(ref Px, ref Pz, 0.5);
            return Distance;
        }

        // ------------------------------------------------------------------ 틱
        /// <summary>보스 이동 뒤 1틱: 패턴 생성·진행·피해, 위험도·안전 지점 갱신. 새 거리 반환.</summary>
        public double Tick(double dt, double t, int phase, double damageMult, bool targetAlive, double playerHp)
        {
            var s = _s;
            double cm = s.PhaseCooldownMult[Math.Min(phase, s.PhaseCooldownMult.Length - 1)];
            if (targetAlive)
            {
                _rockCd -= dt; _poolCd -= dt; _volleyCd -= dt; _chargeCd -= dt;

                if (s.RockfallDamage > 0 && s.RockfallCount > 0 && phase >= s.RockfallPhaseMin && _rockCd <= Eps)
                {
                    _rockCd = s.RockfallCooldown * cm;
                    SpawnRocks(t);
                    if (phase >= s.ComboPhaseMin && s.PoolDps > 0) SpawnPool(t);
                }
                if (s.PoolDps > 0 && phase >= s.PoolPhaseMin && _poolCd <= Eps)
                {
                    _poolCd = s.PoolCooldown * cm;
                    SpawnPool(t);
                }
                if (s.VolleyDamage > 0 && s.VolleyCount > 0 && phase >= s.VolleyPhaseMin && _volleyCd <= Eps)
                {
                    _volleyCd = s.VolleyCooldown * cm;
                    SpawnVolley(t);
                }
                if (s.ChargeDamage > 0 && phase >= s.ChargePhaseMin && _chargeCd <= Eps && ChargeNow == null)
                {
                    _chargeCd = s.ChargeCooldown * cm;
                    SpawnCharge(t);
                }
            }

            // --- 낙석 착지
            for (int i = Rocks.Count - 1; i >= 0; i--)
            {
                var r = Rocks[i];
                r.Left -= dt;
                if (r.Left > Eps) continue;
                Rocks.RemoveAt(i);
                bool hit = targetAlive && Len(Px - r.X, Pz - r.Z) <= r.R + Eps;
                if (_log.Enabled) _log.Record(t, "projectile_land", new JObject { ["kind"] = "rockfall", ["id"] = r.Id, ["pos"] = P2(r.X, r.Z), ["radius"] = r.R, ["hit"] = hit });
                if (hit) Hit("rockfall", s.RockfallDamage * damageMult, t);
            }
            // --- 독 장판
            bool inPool = false;
            for (int i = Pools.Count - 1; i >= 0; i--)
            {
                var p = Pools[i];
                p.Left -= dt;
                if (p.Left <= Eps)
                {
                    Pools.RemoveAt(i);
                    if (_log.Enabled) _log.Record(t, "zone_expire", new JObject { ["id"] = p.Id });
                    continue;
                }
                if (targetAlive && Len(Px - p.X, Pz - p.Z) <= p.R + Eps) inPool = true;
            }
            if (inPool) Hit("pool", s.PoolDps * dt * damageMult, t, quiet: true);
            // --- 탄막
            for (int i = Shots.Count - 1; i >= 0; i--)
            {
                var b = Shots[i];
                double ox = b.X, oz = b.Z;
                b.X += b.Vx * dt; b.Z += b.Vz * dt;
                if (targetAlive && !_volleyHit.Contains(b.Volley) && SegDist(ox, oz, b.X, b.Z, Px, Pz) <= ShotHitRadius + Eps)
                {
                    Shots.RemoveAt(i);
                    _volleyHit.Add(b.Volley);
                    if (_log.Enabled) _log.Record(t, "projectile_land", new JObject { ["kind"] = "volley", ["id"] = b.Id, ["pos"] = P2(b.X, b.Z), ["hit"] = true });
                    Hit("volley", s.VolleyDamage * damageMult, t);
                    continue;
                }
                if (!Inside(b.X, b.Z, -1.0))
                {
                    Shots.RemoveAt(i);
                    if (_log.Enabled) _log.Record(t, "projectile_land", new JObject { ["kind"] = "volley", ["id"] = b.Id, ["pos"] = P2(b.X, b.Z), ["hit"] = false });
                }
            }
            // --- 돌진
            if (ChargeNow != null)
            {
                var c = ChargeNow;
                c.Left -= dt;
                if (c.Left <= Eps)
                {
                    ChargeNow = null;
                    double side = 0;
                    bool hit = targetAlive && InBand(c, Px, Pz, 0.0, out side);
                    double ex = c.Sx + c.Dx * c.Len, ez = c.Sz + c.Dz * c.Len;
                    Clamp(ref ex, ref ez, 1.0);
                    Bx = ex; Bz = ez;
                    if (_log.Enabled) _log.Record(t, "charge", new JObject { ["id"] = c.Id, ["to"] = P2(Bx, Bz), ["hit"] = hit });
                    if (hit)
                    {
                        double sg = side >= 0 ? 1.0 : -1.0;
                        Px += -c.Dz * sg * s.ChargeKnockback;
                        Pz += c.Dx * sg * s.ChargeKnockback;
                        Clamp(ref Px, ref Pz, 0.5);
                        Hit("charge", s.ChargeDamage * damageMult, t);
                    }
                    if (Distance < 1.0)   // 보스 몸에 겹치지 않게 (보스 쪽으로 1m 띄움)
                    {
                        Dir(out var ux, out var uz);
                        Bx = Px - ux * 1.0; Bz = Pz - uz * 1.0;
                        Clamp(ref Bx, ref Bz, 1.0);
                    }
                }
            }

            // --- 위험도·안전 지점
            if (targetAlive)
            {
                Danger = DangerAt(Px, Pz, playerHp, damageMult);
                if (Danger > Eps) FindSafe(playerHp, damageMult);
                else { SafeX = Px; SafeZ = Pz; }
            }
            else Danger = 0;
            return Distance;
        }

        static JArray P2(double x, double z) => new JArray(Math.Round(x, 2), Math.Round(z, 2));

        void Hit(string kind, double raw, double t, bool quiet = false)
        {
            double taken = OnHit != null ? OnHit(kind, raw) : raw;
            Count(Hits, quiet ? kind + "_ticks" : kind);   // 장판은 틱마다 (기록도 생략 — 이벤트 폭증 방지)
            if (_log.Enabled && !quiet) _log.Record(t, "player_hit", new JObject { ["source"] = kind, ["damage"] = Math.Round(taken, 1) });
        }

        // ------------------------------------------------------------------ 생성
        int NewId() => ++_nextId;

        void SpawnRocks(double t)
        {
            var s = _s;
            int n = (int)s.RockfallCount, aimed = Math.Min(n, (int)s.RockfallAimed);
            for (int i = 0; i < n && Rocks.Count < MaxEach; i++)
            {
                double x, z;
                if (i < aimed) { x = Px; z = Pz; }
                else
                {
                    double rr = (Radius - 1.0) * Math.Sqrt(_rng.NextDouble()), a = _rng.NextDouble() * 2 * Math.PI;
                    x = rr * Math.Cos(a); z = rr * Math.Sin(a);
                }
                var r = new Rock { Id = NewId(), X = x, Z = z, R = s.RockfallRadius, Left = s.RockfallWindup, Total = s.RockfallWindup, Aimed = i < aimed };
                Rocks.Add(r);
                if (_log.Enabled) _log.Record(t, "telegraph", new JObject { ["kind"] = "rockfall", ["shape"] = "circle", ["id"] = r.Id, ["pos"] = P2(x, z), ["radius"] = r.R, ["t_land"] = Math.Round(t + r.Left, 2) });
            }
            Count(Spawned, "rockfall");
        }

        void SpawnPool(double t)
        {
            var s = _s;
            while (Pools.Count >= Math.Max(1, (int)s.PoolMax)) Pools.RemoveAt(0);
            var p = new Pool { Id = NewId(), X = Px, Z = Pz, R = s.PoolRadius, Left = s.PoolDuration, Total = s.PoolDuration };
            Pools.Add(p);
            Count(Spawned, "pool");
            if (_log.Enabled) _log.Record(t, "zone_spawn", new JObject { ["kind"] = "pool", ["id"] = p.Id, ["pos"] = P2(p.X, p.Z), ["radius"] = p.R, ["duration"] = p.Total });
        }

        void SpawnVolley(double t)
        {
            var s = _s;
            Dir(out var ux, out var uz);
            int k = (int)s.VolleyCount, vid = NewId();
            double arc = s.VolleyArcDeg * Math.PI / 180.0;
            for (int i = 0; i < k && Shots.Count < MaxEach; i++)
            {
                double a = k == 1 ? 0 : -arc / 2 + arc * i / (k - 1);
                double c = Math.Cos(a), sn = Math.Sin(a);
                double vx = (ux * c - uz * sn) * s.VolleySpeed, vz = (ux * sn + uz * c) * s.VolleySpeed;
                Shots.Add(new Shot { Id = NewId(), Volley = vid, X = Bx, Z = Bz, Vx = vx, Vz = vz });
            }
            Count(Spawned, "volley");
            if (_log.Enabled) _log.Record(t, "telegraph", new JObject { ["kind"] = "volley", ["shape"] = "fan", ["pos"] = P2(Bx, Bz), ["dir"] = P2(ux, uz), ["count"] = k, ["arc_deg"] = s.VolleyArcDeg });
        }

        void SpawnCharge(double t)
        {
            var s = _s;
            Dir(out var ux, out var uz);
            var c = new Charge { Id = NewId(), Sx = Bx, Sz = Bz, Dx = ux, Dz = uz, Len = Distance + 4.0, W = s.ChargeWidth, Left = s.ChargeWindup, Total = s.ChargeWindup };
            ChargeNow = c;
            Count(Spawned, "charge");
            if (_log.Enabled) _log.Record(t, "telegraph", new JObject { ["kind"] = "charge", ["shape"] = "band", ["id"] = c.Id, ["pos"] = P2(c.Sx, c.Sz), ["dir"] = P2(ux, uz), ["length"] = Math.Round(c.Len, 2), ["width"] = c.W, ["t_land"] = Math.Round(t + c.Left, 2) });
        }

        // ------------------------------------------------------------------ 위험도
        static bool InBand(Charge c, double x, double z, double margin, out double side)
        {
            double rx = x - c.Sx, rz = z - c.Sz;
            double along = rx * c.Dx + rz * c.Dz;
            side = rx * -c.Dz + rz * c.Dx;
            return along >= -margin && along <= c.Len + margin && Math.Abs(side) <= c.W / 2 + margin + Eps;
        }

        static double SegDist(double ax, double az, double bx, double bz, double px, double pz)
        {
            double dx = bx - ax, dz = bz - az, l2 = dx * dx + dz * dz;
            double u = l2 < 1e-12 ? 0 : Math.Max(0, Math.Min(1, ((px - ax) * dx + (pz - az) * dz) / l2));
            return Len(px - (ax + dx * u), pz - (az + dz * u));
        }

        /// <summary>그 지점에 서 있을 때의 위험도 (0~1).</summary>
        public double DangerAt(double x, double z, double playerHp, double damageMult)
        {
            var s = _s;
            double expect = 0;
            const double m = 0.3;
            foreach (var r in Rocks) if (Len(x - r.X, z - r.Z) <= r.R + m) expect += s.RockfallDamage;
            foreach (var p in Pools) if (Len(x - p.X, z - p.Z) <= p.R + m) expect += s.PoolDps * 6.0;   // 머무는 동안 계속 + 비전투 회복도 막힘
            if (ChargeNow != null && InBand(ChargeNow, x, z, m, out _)) expect += s.ChargeDamage;
            foreach (var b in Shots)
            {
                if (_volleyHit.Contains(b.Volley)) continue;
                double v2 = b.Vx * b.Vx + b.Vz * b.Vz;
                if (v2 < 1e-9) continue;
                double rx = x - b.X, rz = z - b.Z, tt = (rx * b.Vx + rz * b.Vz) / v2;
                if (tt < 0 || tt > DangerHorizon) continue;
                if (Len(rx - b.Vx * tt, rz - b.Vz * tt) <= ShotHitRadius + m) expect += s.VolleyDamage;
            }
            if (expect <= 0) return 0;
            return Math.Min(1.0, DangerGain * expect * damageMult / Math.Max(1.0, playerHp));
        }

        static readonly double[] Rings = { 2.5, 5.0 };

        void FindSafe(double playerHp, double damageMult)
        {
            double cur = Distance, best = double.PositiveInfinity, bestDanger = double.PositiveInfinity;
            double bx = Px, bz = Pz, fx = Px, fz = Pz;
            foreach (var ring in Rings)
                for (int k = 0; k < 8; k++)
                {
                    double a = k * Math.PI / 4;
                    double x = Px + Math.Cos(a) * ring, z = Pz + Math.Sin(a) * ring;
                    if (!Inside(x, z, 0.5)) continue;
                    double dg = DangerAt(x, z, playerHp, damageMult);
                    double score = Math.Abs(Len(x - Bx, z - Bz) - cur) + 0.3 * ring;
                    if (dg <= Eps)
                    {
                        if (score < best - 1e-9) { best = score; bx = x; bz = z; }
                    }
                    else if (dg < bestDanger - 1e-9) { bestDanger = dg; fx = x; fz = z; }
                }
            if (!double.IsPositiveInfinity(best)) { SafeX = bx; SafeZ = bz; }
            else { SafeX = fx; SafeZ = fz; }
        }
    }
}
