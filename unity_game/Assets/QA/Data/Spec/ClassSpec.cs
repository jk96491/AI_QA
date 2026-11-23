// 직업 정의서 (game_sim/spec/class_spec.py, skill_def.py 대응). UnityEngine 비의존.
using System;
using System.Collections.Generic;
using System.Globalization;
using Newtonsoft.Json.Linq;

namespace Qa.Data
{
    /// <summary>프로토콜 error 응답으로 변환되는 파라미터 오류 (code = unknown_param / param_out_of_range / bad_request).</summary>
    public sealed class ParamException : Exception
    {
        public readonly string Code;
        public ParamException(string code, string message) : base(message) { Code = code; }
    }

    public enum SkillRole { Basic, Dps, Burst, Defense, GapClose, Mobility, Setup }

    public sealed class SkillDef
    {
        public string Name;
        public int Index;                 // 정의서 순서 (직업 안에서 0..n-1)
        public SkillRole Role;
        public double Damage;
        public double Cooldown;
        public double Cost;
        public double CastTime;
        public double Range = 3.0;        // 0 이하 = 자기 대상
        public double ResourceGain;       // 적중 시 자원 획득 (전사 분노)
        public double Shield;             // 받는 피해 감소율
        public double Evade;              // 피해 무효 시간(초)
        public double EffectDuration;
        public double Retreat;            // 뒤로 이동 거리(m)
        public bool GapClose;             // 보스 앞으로 순간 이동
        // ---- 0.8.1 (PLAYER_SKILL_BT_REQUEST) ----
        public double Dash;               // Mobility: 안전 지점 쪽으로 즉시 이동 거리(m) (아레나 없으면 후퇴)
        public double BuffDamage;         // Setup: effect_duration 동안 주는 피해 × (1 + buff_damage) (음수 = 감소)
        public double ResourceOnUse;      // 사용 즉시 자원 획득
        public double RegenMult = 1.0;    // Setup: effect_duration 동안 자원 재생 배율
        public double TargetVuln;         // Setup: vuln_duration 동안 보스가 받는 피해 × (1 + target_vuln)
        public double VulnDuration;
        public double BossStun;           // Defense: 보스 행동 정지(초)
        public bool IsComboSetup => Role == SkillRole.Setup && (BuffDamage > 0 || TargetVuln > 0);

        public bool IsSelfTarget => Range <= 0;

        static readonly HashSet<string> Keys = new HashSet<string>
        {
            "name", "role", "damage", "cooldown", "cost", "cast_time", "range", "resource_gain",
            "shield", "evade", "effect_duration", "retreat", "gap_close",
            "dash", "buff_damage", "resource_on_use", "regen_mult", "target_vuln", "vuln_duration", "boss_stun",
        };

        public static SkillRole ParseRole(string s, string source)
        {
            switch (s)
            {
                case "basic": return SkillRole.Basic;
                case "dps": return SkillRole.Dps;
                case "burst": return SkillRole.Burst;
                case "defense": return SkillRole.Defense;
                case "gap_close": return SkillRole.GapClose;
                case "mobility": return SkillRole.Mobility;
                case "setup": return SkillRole.Setup;
                default: throw new SpecException(source, "알 수 없는 skill role " + s);
            }
        }

        public static SkillDef FromJson(JObject d, string source)
        {
            var name = SpecJson.Str(d, "name", null);
            if (name == null) throw new SpecException(source, "skill.name 누락");
            var src = source + " skill " + name;
            var bad = SpecJson.UnknownKeys(d, Keys);
            if (bad.Count > 0) throw new SpecException(src, "알 수 없는 필드: " + string.Join(", ", bad));
            return new SkillDef
            {
                Name = name,
                Role = ParseRole(SpecJson.Str(d, "role", ""), src),
                Damage = SpecJson.Num(d, "damage", 0, src),
                Cooldown = SpecJson.Num(d, "cooldown", 0, src),
                Cost = SpecJson.Num(d, "cost", 0, src),
                CastTime = SpecJson.Num(d, "cast_time", 0, src),
                Range = SpecJson.Num(d, "range", 3.0, src),
                ResourceGain = SpecJson.Num(d, "resource_gain", 0, src),
                Shield = SpecJson.Num(d, "shield", 0, src),
                Evade = SpecJson.Num(d, "evade", 0, src),
                EffectDuration = SpecJson.Num(d, "effect_duration", 0, src),
                Retreat = SpecJson.Num(d, "retreat", 0, src),
                GapClose = SpecJson.Bool(d, "gap_close", false),
                Dash = SpecJson.Num(d, "dash", 0, src),
                BuffDamage = SpecJson.Num(d, "buff_damage", 0, src),
                ResourceOnUse = SpecJson.Num(d, "resource_on_use", 0, src),
                RegenMult = SpecJson.Num(d, "regen_mult", 1.0, src),
                TargetVuln = SpecJson.Num(d, "target_vuln", 0, src),
                VulnDuration = SpecJson.Num(d, "vuln_duration", 0, src),
                BossStun = SpecJson.Num(d, "boss_stun", 0, src),
            };
        }
    }

    public sealed class PlayerStats
    {
        public double MaxHp, Armor, MaxResource, StartResource, ResourceRegen, MoveSpeed;
        public int Potions;
        public double PotionHealRatio, PotionCooldown;
        public double CritChance = 0.1;
        // 마지막 피격 후 RegenDelay 초가 지나면 초당 최대 체력의 HpRegenRatio 만큼 회복 (후퇴·회복)
        public double HpRegenRatio = 0.02;
        public double RegenDelay = 4.0;

        static readonly HashSet<string> Keys = new HashSet<string>
        {
            "max_hp", "armor", "max_resource", "start_resource", "resource_regen", "move_speed",
            "potions", "potion_heal_ratio", "potion_cooldown", "crit_chance", "hp_regen_ratio", "regen_delay",
        };

        public static PlayerStats FromJson(JObject d, string source)
        {
            var src = source + " stats";
            var bad = SpecJson.UnknownKeys(d, Keys);
            if (bad.Count > 0) throw new SpecException(src, "알 수 없는 필드: " + string.Join(", ", bad));
            return new PlayerStats
            {
                MaxHp = SpecJson.Num(d, "max_hp", src),
                Armor = SpecJson.Num(d, "armor", src),
                MaxResource = SpecJson.Num(d, "max_resource", src),
                StartResource = SpecJson.Num(d, "start_resource", src),
                ResourceRegen = SpecJson.Num(d, "resource_regen", src),
                MoveSpeed = SpecJson.Num(d, "move_speed", src),
                Potions = (int)SpecJson.Num(d, "potions", src),
                PotionHealRatio = SpecJson.Num(d, "potion_heal_ratio", src),
                PotionCooldown = SpecJson.Num(d, "potion_cooldown", src),
                CritChance = SpecJson.Num(d, "crit_chance", 0.1, src),
                HpRegenRatio = SpecJson.Num(d, "hp_regen_ratio", 0.02, src),
                RegenDelay = SpecJson.Num(d, "regen_delay", 4.0, src),
            };
        }
    }

    public sealed class ClassSpec
    {
        public string Name;
        public string DisplayName;
        public bool Ranged;
        public string SpecVersion;
        public PlayerStats Stats;
        // BT 고정 규칙 (학습 대상 아님, describe 로 공개하지 않음). 0 이면 규칙 없음.
        // 생존 블록을 SurvivalMaxHold 초 넘게 계속 유지하면 SurvivalLockout 초 동안 생존 블록을 후보에서 뺀다.
        public double SurvivalMaxHold;
        public double SurvivalLockout;
        public List<SkillDef> Skills = new List<SkillDef>();
        /// <summary>정의서 순서 유지 (describe 응답 순서).</summary>
        public List<ParamDef> ParamList = new List<ParamDef>();
        readonly Dictionary<string, ParamDef> _params = new Dictionary<string, ParamDef>(StringComparer.Ordinal);

        public bool HasParam(string name) => _params.ContainsKey(name);
        public SkillDef BasicSkill => SkillsByRole(SkillRole.Basic)[0];
        public ParamDef Param(string name) => _params[name];

        public SkillDef Skill(string name)
        {
            foreach (var s in Skills) if (s.Name == name) return s;
            throw new KeyException("class " + Name + " 에 스킬 " + name + " 없음");
        }

        /// <summary>역할별 스킬, 피해 내림차순 (동률은 정의서 순서 — 안정 정렬).</summary>
        public List<SkillDef> SkillsByRole(SkillRole role)
        {
            var outp = new List<SkillDef>();
            foreach (var s in Skills) if (s.Role == role) outp.Add(s);
            // List.Sort 는 불안정 → 삽입 정렬로 안정 정렬 (스킬 수가 적음)
            for (int i = 1; i < outp.Count; i++)
            {
                var x = outp[i];
                int j = i - 1;
                while (j >= 0 && outp[j].Damage < x.Damage) { outp[j + 1] = outp[j]; j--; }
                outp[j + 1] = x;
            }
            return outp;
        }

        /// <summary>정의서 default = 손 튜닝 기준선.</summary>
        public ParamValues DefaultParams()
        {
            var v = new ParamValues();
            foreach (var p in ParamList) v.Set(p.Name, p.Default);
            return v;
        }

        /// <summary>
        /// base 위에 updates 를 덮어쓴 새 값. 모르는 이름 → unknown_param, 범위 밖 → param_out_of_range,
        /// 숫자 아님 → bad_request. 실패하면 base 는 그대로.
        /// </summary>
        public ParamValues ResolveParams(ParamValues @base, JObject updates)
        {
            var outp = @base.Clone();
            if (updates == null) return outp;
            foreach (var prop in updates.Properties())
            {
                if (!_params.TryGetValue(prop.Name, out var def))
                    throw new ParamException("unknown_param", "class '" + Name + "' 에 파라미터 '" + prop.Name + "' 없음");
                var t = prop.Value;
                if (t.Type != JTokenType.Float && t.Type != JTokenType.Integer)
                    throw new ParamException("bad_request", "파라미터 '" + prop.Name + "' 값이 숫자가 아님: " + t.ToString());
                double v = t.Value<double>();
                if (double.IsNaN(v) || double.IsInfinity(v) || !def.Contains(v))
                    throw new ParamException("param_out_of_range", string.Format(CultureInfo.InvariantCulture,
                        "{0}={1:G6} 가 범위 [{2:G6}, {3:G6}] 밖", prop.Name, v, def.Low, def.High));
                outp.Set(prop.Name, v);
            }
            return outp;
        }

        public JObject ToWire()
        {
            var ps = new JArray();
            foreach (var p in ParamList) ps.Add(p.ToWire());
            return new JObject
            {
                ["name"] = Name,
                ["display_name"] = DisplayName,
                ["ranged"] = Ranged,
                ["spec_version"] = SpecVersion,
                ["params"] = ps,
            };
        }

        public static ClassSpec FromJson(JObject d, string source)
        {
            var name = SpecJson.Str(d, "class", null);
            if (name == null) throw new SpecException(source, "class 이름 누락");
            if (!(d["stats"] is JObject stats)) throw new SpecException(source, "stats 누락");
            if (!(d["skills"] is JArray skills)) throw new SpecException(source, "skills 누락");
            if (!(d["params"] is JObject ps)) throw new SpecException(source, "params 누락");
            var spec = new ClassSpec
            {
                Name = name,
                DisplayName = SpecJson.Str(d, "display_name", name),
                Ranged = SpecJson.Bool(d, "ranged", false),
                SpecVersion = SpecJson.Str(d, "spec_version", "0.1"),
                Stats = PlayerStats.FromJson(stats, source),
            };
            if (d["bt_rules"] is JObject rules)
            {
                var src = source + " bt_rules";
                var bad = SpecJson.UnknownKeys(rules, new HashSet<string> { "survival_max_hold", "survival_lockout" });
                if (bad.Count > 0) throw new SpecException(src, "알 수 없는 필드: " + string.Join(", ", bad));
                spec.SurvivalMaxHold = SpecJson.Num(rules, "survival_max_hold", 0, src);
                spec.SurvivalLockout = SpecJson.Num(rules, "survival_lockout", 0, src);
                if (spec.SurvivalMaxHold < 0 || spec.SurvivalLockout < 0) throw new SpecException(src, "음수 불가");
            }
            foreach (var s in skills)
            {
                if (!(s is JObject so)) throw new SpecException(source, "skills 항목은 객체");
                var sd = SkillDef.FromJson(so, source);
                sd.Index = spec.Skills.Count;
                spec.Skills.Add(sd);
            }
            foreach (var prop in ps.Properties())
            {
                if (!(prop.Value is JObject po)) throw new SpecException(source, "params." + prop.Name + " 는 객체");
                var def = ParamDef.FromJson(prop.Name, po, source);
                spec.ParamList.Add(def);
                spec._params[def.Name] = def;
            }
            return spec;
        }
    }

    public sealed class KeyException : Exception
    {
        public KeyException(string message) : base(message) { }
    }

    /// <summary>
    /// 파라미터 값 모음. 이름 → 값 조회만 하고 순회 순서에 의존하는 로직을 두지 않는다 (결정성).
    /// </summary>
    public sealed class ParamValues
    {
        readonly Dictionary<string, double> _v = new Dictionary<string, double>(StringComparer.Ordinal);

        public double this[string name]
        {
            get
            {
                if (_v.TryGetValue(name, out var x)) return x;
                throw new KeyException("파라미터 " + name + " 없음");
            }
        }

        public bool Has(string name) => _v.ContainsKey(name);
        public double Get(string name, double fallback) => _v.TryGetValue(name, out var x) ? x : fallback;
        public void Set(string name, double value) => _v[name] = value;

        public ParamValues Clone()
        {
            var c = new ParamValues();
            foreach (var kv in _v) c._v[kv.Key] = kv.Value;
            return c;
        }
    }
}
