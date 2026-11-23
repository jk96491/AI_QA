// 블랙보드: 관측값·파라미터·선택 상태를 BT 노드들이 공유 (game_sim/bt/blackboard.py 대응).
using System.Collections.Generic;
using Qa.Data;
using Qa.Sim;

namespace Qa.BT
{
    public sealed class Blackboard
    {
        const double Eps = SimConst.Eps;

        public readonly ClassSpec Spec;
        public ParamValues Params = new ParamValues();
        public Observation Obs;
        public BtAction Action;
        public string CurrentBlock = "none";
        public double BlockSince;

        readonly List<SkillDef>[] _byRole;
        readonly BtAction[] _useAction;   // SkillDef.Index → 캐시된 행동
        public readonly SkillDef BasicSkill;

        public Blackboard(ClassSpec spec)
        {
            Spec = spec;
            var roles = (SkillRole[])System.Enum.GetValues(typeof(SkillRole));
            _byRole = new List<SkillDef>[roles.Length];
            foreach (var r in roles) _byRole[(int)r] = spec.SkillsByRole(r);
            _useAction = new BtAction[spec.Skills.Count];
            foreach (var s in spec.Skills) _useAction[s.Index] = BtAction.Use(s);
            BasicSkill = spec.BasicSkill;
        }

        // ----- 파라미터 -----
        /// <summary>필수 파라미터 (없으면 KeyException).</summary>
        public double P(string key) => Params[key];
        public double P(string key, double fallback) => Params.Get(key, fallback);

        // ----- 스킬 헬퍼 -----
        public List<SkillDef> Skills(SkillRole role) => _byRole[(int)role];
        public BtAction UseAction(SkillDef s) => _useAction[s.Index];

        /// <summary>쿨타임·자원 기준 (GCD 무시).</summary>
        public bool Available(SkillDef s) => Obs.SkillAvailable[s.Index];
        public bool UsableNow(SkillDef s) => Obs.GcdReady && Available(s);
        public bool InRange(SkillDef s) => s.IsSelfTarget || Obs.Distance <= s.Range + Eps;

        /// <summary>사용 후에도 resource_reserve 비율 이상의 자원이 남는가 (버스트용 비축).</summary>
        public bool KeepsReserve(SkillDef s)
        {
            double reserve = P("resource_reserve", 0.0) * Obs.MaxResource;
            return Obs.Resource - s.Cost >= reserve - Eps;
        }

        /// <summary>버스트 스킬 중 하나가 sec 초 안에 쿨이 돈다 (자원은 보지 않음).</summary>
        public bool BurstSoon(double sec)
        {
            foreach (var s in Skills(SkillRole.Burst)) if (Obs.CooldownLeft[s.Index] <= sec + Eps) return true;
            return false;
        }

        /// <summary>같은 역할 스킬 중 지금 쓸 수 있는 것 가운데 점수(피해 / max(시전, GCD)) 최대. 동점이면 데이터 순서. 없으면 null.</summary>
        public SkillDef BestUsable(SkillRole role, bool respectReserve, double gcd)
        {
            SkillDef best = null;
            double bs = double.NegativeInfinity;
            foreach (var s in Spec.Skills)
            {
                if (s.Role != role || !UsableNow(s) || !InRange(s)) continue;
                if (respectReserve && !KeepsReserve(s)) continue;
                double sc = s.Damage / System.Math.Max(gcd, s.CastTime);
                if (sc > bs + 1e-9) { bs = sc; best = s; }
            }
            return best;
        }

        public bool AnyAvailable(SkillRole role)
        {
            foreach (var s in Skills(role)) if (Available(s)) return true;
            return false;
        }
    }
}
