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

        public bool AnyAvailable(SkillRole role)
        {
            foreach (var s in Skills(role)) if (Available(s)) return true;
            return false;
        }
    }
}
