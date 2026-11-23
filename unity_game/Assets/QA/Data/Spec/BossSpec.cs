// 보스 정의서와 패치 시나리오 (game_sim/spec/boss_spec.py, scenario.py 확장). UnityEngine 비의존.
// 보스 BT 상수는 여기(정의서 JSON)에만 있고 describe 로 공개하지 않는다 → 학습 대상이 아님.
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace Qa.Data
{
    public sealed class BossSpec
    {
        public string Name;
        public double MaxHp;
        public double Reach;               // 근접 공격 사거리(m)
        public double MoveSpeed;           // 추격 속도(m/s)
        public double AutoDamage;
        public double AutoInterval;
        public double AoeDamage;           // 거리 무관 광역기
        public double AoeInterval;
        public double AoeJitter;
        public double GimmickFirstAt;
        public double GimmickInterval;
        public double GimmickJitter;
        public double GimmickWindow;       // 경고 후 대응 제한 시간(초)
        public double GimmickDamageRatio;  // 미대응 시 플레이어 최대 체력 대비 피해
        public double DamageVariance;      // 피해 ±비율
        public double[] PhaseThresholds = { 0.75, 0.5, 0.25 };
        public double[] PhaseDamageMult = { 1.0, 1.1, 1.25, 1.4 };
        public double[] PhaseSpeedMult = { 1.0, 1.05, 1.1, 1.2 };

        // ----- 보스 BT 기술 (damage 0 이면 사용 안 함) -----
        // 내려찍기: 사거리 안 → 준비 동작 후, 그때도 사거리(+range_bonus) 안이면 피해
        public double CleaveDamage, CleaveCooldown, CleaveWindup, CleaveRangeBonus = 0.5;
        // 도약: phase_min 이상, 플레이어가 min_distance 보다 멀면 → 준비 후 플레이어 앞에 착지하며 피해
        public double LeapDamage, LeapCooldown, LeapWindup, LeapMinDistance = 7.0;
        public int LeapPhaseMin = 1;
        // 처형: phase_min 이상, 플레이어 체력 hp_below 미만 + 사거리 안 → 준비 후 사거리 안이면 큰 피해
        public double ExecuteDamage, ExecuteCooldown, ExecuteWindup, ExecuteHpBelow = 0.35;
        public int ExecutePhaseMin = 2;
        // 투척: 사거리 밖(거리 > reach + throw_min_gap)이면 → 준비 후 원거리 피해 (회피기로 피할 수 있음)
        public double ThrowDamage, ThrowCooldown, ThrowWindup, ThrowMinGap = 1.0;
        public int ThrowPhaseMin = 0;
        // 격노: 전투 enrage_time 초 이후 모든 피해 × enrage_damage_mult (0 이면 없음)
        public double EnrageTime, EnrageDamageMult = 1.0;

        // ---- 2D 아레나 패턴 (0.8.0, BOSS_PATTERN_REQUEST). arena_radius = 0 이면 전부 꺼짐 = 0.7.x 와 같은 1차원 전투 ----
        public double ArenaRadius;
        public double RockfallCount, RockfallAimed, RockfallRadius = 2.2, RockfallWindup = 1.6, RockfallDamage, RockfallCooldown = 14;
        public int RockfallPhaseMin;
        public double PoolRadius = 3.0, PoolDuration = 18, PoolDps, PoolCooldown = 9, PoolMax = 4;
        public int PoolPhaseMin;
        public double VolleyCount, VolleyArcDeg = 70, VolleySpeed = 9, VolleyDamage, VolleyCooldown = 12;
        public int VolleyPhaseMin;
        public double ChargeWidth = 2.5, ChargeWindup = 1.3, ChargeDamage, ChargeCooldown = 15, ChargeKnockback = 3.0;
        public int ChargePhaseMin;
        /// <summary>이 페이즈부터 낙석과 장판을 함께 (99 = 안 함).</summary>
        public int ComboPhaseMin = 99;
        public double[] PhaseCooldownMult = { 1.0, 1.0, 1.0, 1.0 };
        public bool HasArena => ArenaRadius > 0;

        public static readonly HashSet<string> Keys = new HashSet<string>
        {
            "name", "max_hp", "reach", "move_speed", "auto_damage", "auto_interval", "aoe_damage", "aoe_interval",
            "aoe_jitter", "gimmick_first_at", "gimmick_interval", "gimmick_jitter", "gimmick_window",
            "gimmick_damage_ratio", "damage_variance", "phase_thresholds", "phase_damage_mult", "phase_speed_mult",
            "cleave_damage", "cleave_cooldown", "cleave_windup", "cleave_range_bonus",
            "leap_damage", "leap_cooldown", "leap_windup", "leap_min_distance", "leap_phase_min",
            "execute_damage", "execute_cooldown", "execute_windup", "execute_hp_below", "execute_phase_min",
            "throw_damage", "throw_cooldown", "throw_windup", "throw_min_gap", "throw_phase_min",
            "enrage_time", "enrage_damage_mult",
            "arena_radius", "rockfall_count", "rockfall_aimed", "rockfall_radius", "rockfall_windup", "rockfall_damage",
            "rockfall_cooldown", "rockfall_phase_min", "pool_radius", "pool_duration", "pool_dps", "pool_cooldown", "pool_max",
            "pool_phase_min", "volley_count", "volley_arc_deg", "volley_speed", "volley_damage", "volley_cooldown",
            "volley_phase_min", "charge_width", "charge_windup", "charge_damage", "charge_cooldown", "charge_knockback",
            "charge_phase_min", "combo_phase_min", "phase_cooldown_mult",
        };

        public static BossSpec FromJson(JObject d, string source)
        {
            var bad = SpecJson.UnknownKeys(d, Keys);
            if (bad.Count > 0) throw new SpecException(source, "알 수 없는 보스 필드: " + string.Join(", ", bad));
            var b = new BossSpec
            {
                Name = SpecJson.Str(d, "name", "default"),
                MaxHp = SpecJson.Num(d, "max_hp", source),
                Reach = SpecJson.Num(d, "reach", source),
                MoveSpeed = SpecJson.Num(d, "move_speed", source),
                AutoDamage = SpecJson.Num(d, "auto_damage", source),
                AutoInterval = SpecJson.Num(d, "auto_interval", source),
                AoeDamage = SpecJson.Num(d, "aoe_damage", source),
                AoeInterval = SpecJson.Num(d, "aoe_interval", source),
                AoeJitter = SpecJson.Num(d, "aoe_jitter", source),
                GimmickFirstAt = SpecJson.Num(d, "gimmick_first_at", source),
                GimmickInterval = SpecJson.Num(d, "gimmick_interval", source),
                GimmickJitter = SpecJson.Num(d, "gimmick_jitter", source),
                GimmickWindow = SpecJson.Num(d, "gimmick_window", source),
                GimmickDamageRatio = SpecJson.Num(d, "gimmick_damage_ratio", source),
                DamageVariance = SpecJson.Num(d, "damage_variance", source),
            };
            b.PhaseThresholds = SpecJson.NumArray(d, "phase_thresholds", b.PhaseThresholds, source);
            b.PhaseDamageMult = SpecJson.NumArray(d, "phase_damage_mult", b.PhaseDamageMult, source);
            b.PhaseSpeedMult = SpecJson.NumArray(d, "phase_speed_mult", b.PhaseSpeedMult, source);

            b.CleaveDamage = SpecJson.Num(d, "cleave_damage", 0, source);
            b.CleaveCooldown = SpecJson.Num(d, "cleave_cooldown", 0, source);
            b.CleaveWindup = SpecJson.Num(d, "cleave_windup", 0, source);
            b.CleaveRangeBonus = SpecJson.Num(d, "cleave_range_bonus", b.CleaveRangeBonus, source);
            b.LeapDamage = SpecJson.Num(d, "leap_damage", 0, source);
            b.LeapCooldown = SpecJson.Num(d, "leap_cooldown", 0, source);
            b.LeapWindup = SpecJson.Num(d, "leap_windup", 0, source);
            b.LeapMinDistance = SpecJson.Num(d, "leap_min_distance", b.LeapMinDistance, source);
            b.LeapPhaseMin = (int)SpecJson.Num(d, "leap_phase_min", b.LeapPhaseMin, source);
            b.ExecuteDamage = SpecJson.Num(d, "execute_damage", 0, source);
            b.ExecuteCooldown = SpecJson.Num(d, "execute_cooldown", 0, source);
            b.ExecuteWindup = SpecJson.Num(d, "execute_windup", 0, source);
            b.ExecuteHpBelow = SpecJson.Num(d, "execute_hp_below", b.ExecuteHpBelow, source);
            b.ExecutePhaseMin = (int)SpecJson.Num(d, "execute_phase_min", b.ExecutePhaseMin, source);
            b.ThrowDamage = SpecJson.Num(d, "throw_damage", 0, source);
            b.ThrowCooldown = SpecJson.Num(d, "throw_cooldown", 0, source);
            b.ThrowWindup = SpecJson.Num(d, "throw_windup", 0, source);
            b.ThrowMinGap = SpecJson.Num(d, "throw_min_gap", b.ThrowMinGap, source);
            b.ThrowPhaseMin = (int)SpecJson.Num(d, "throw_phase_min", b.ThrowPhaseMin, source);
            b.EnrageTime = SpecJson.Num(d, "enrage_time", 0, source);
            b.EnrageDamageMult = SpecJson.Num(d, "enrage_damage_mult", b.EnrageDamageMult, source);
            b.ArenaRadius = SpecJson.Num(d, "arena_radius", 0, source);
            b.RockfallCount = SpecJson.Num(d, "rockfall_count", 0, source);
            b.RockfallAimed = SpecJson.Num(d, "rockfall_aimed", 0, source);
            b.RockfallRadius = SpecJson.Num(d, "rockfall_radius", b.RockfallRadius, source);
            b.RockfallWindup = SpecJson.Num(d, "rockfall_windup", b.RockfallWindup, source);
            b.RockfallDamage = SpecJson.Num(d, "rockfall_damage", 0, source);
            b.RockfallCooldown = SpecJson.Num(d, "rockfall_cooldown", b.RockfallCooldown, source);
            b.RockfallPhaseMin = (int)SpecJson.Num(d, "rockfall_phase_min", 0, source);
            b.PoolRadius = SpecJson.Num(d, "pool_radius", b.PoolRadius, source);
            b.PoolDuration = SpecJson.Num(d, "pool_duration", b.PoolDuration, source);
            b.PoolDps = SpecJson.Num(d, "pool_dps", 0, source);
            b.PoolCooldown = SpecJson.Num(d, "pool_cooldown", b.PoolCooldown, source);
            b.PoolMax = SpecJson.Num(d, "pool_max", b.PoolMax, source);
            b.PoolPhaseMin = (int)SpecJson.Num(d, "pool_phase_min", 0, source);
            b.VolleyCount = SpecJson.Num(d, "volley_count", 0, source);
            b.VolleyArcDeg = SpecJson.Num(d, "volley_arc_deg", b.VolleyArcDeg, source);
            b.VolleySpeed = SpecJson.Num(d, "volley_speed", b.VolleySpeed, source);
            b.VolleyDamage = SpecJson.Num(d, "volley_damage", 0, source);
            b.VolleyCooldown = SpecJson.Num(d, "volley_cooldown", b.VolleyCooldown, source);
            b.VolleyPhaseMin = (int)SpecJson.Num(d, "volley_phase_min", 0, source);
            b.ChargeWidth = SpecJson.Num(d, "charge_width", b.ChargeWidth, source);
            b.ChargeWindup = SpecJson.Num(d, "charge_windup", b.ChargeWindup, source);
            b.ChargeDamage = SpecJson.Num(d, "charge_damage", 0, source);
            b.ChargeCooldown = SpecJson.Num(d, "charge_cooldown", b.ChargeCooldown, source);
            b.ChargeKnockback = SpecJson.Num(d, "charge_knockback", b.ChargeKnockback, source);
            b.ChargePhaseMin = (int)SpecJson.Num(d, "charge_phase_min", 0, source);
            b.ComboPhaseMin = (int)SpecJson.Num(d, "combo_phase_min", b.ComboPhaseMin, source);
            b.PhaseCooldownMult = SpecJson.NumArray(d, "phase_cooldown_mult", b.PhaseCooldownMult, source);
            return b;
        }
    }

    /// <summary>시나리오 = 보스 정의서 JSON 에 적용하는 패치: scale(필드 × 배율), set(필드 = 값).</summary>
    public sealed class Scenario
    {
        public string Name;
        public string Description;
        public string Boss = "default";
        public JObject Scale = new JObject();
        public JObject Set = new JObject();

        public static Scenario FromJson(string name, JObject d)
        {
            return new Scenario
            {
                Name = name,
                Description = SpecJson.Str(d, "description", ""),
                Boss = SpecJson.Str(d, "boss", "default"),
                Scale = d["scale"] as JObject ?? new JObject(),
                Set = d["set"] as JObject ?? new JObject(),
            };
        }

        /// <summary>보스 원본 JSON 에 패치를 적용한 새 JSON (원본은 바꾸지 않음).</summary>
        public JObject Apply(JObject bossJson, string source)
        {
            var outp = (JObject)bossJson.DeepClone();
            if (Scale.Count == 0 && Set.Count == 0) return outp;
            foreach (var p in Scale.Properties())
            {
                var cur = outp[p.Name];
                if (cur == null || (cur.Type != JTokenType.Float && cur.Type != JTokenType.Integer))
                    throw new SpecException(source, "scenario " + Name + ": scale 대상 " + p.Name + " 이 보스 숫자 필드가 아님");
                outp[p.Name] = cur.Value<double>() * p.Value.Value<double>();
            }
            foreach (var p in Set.Properties())
            {
                if (!BossSpec.Keys.Contains(p.Name))
                    throw new SpecException(source, "scenario " + Name + ": set 대상 " + p.Name + " 이 보스 필드가 아님");
                outp[p.Name] = p.Value.DeepClone();
            }
            outp["name"] = SpecJson.Str(bossJson, "name", Boss) + "@" + Name;
            return outp;
        }
    }
}
