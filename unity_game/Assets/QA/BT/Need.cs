// 필요도 N 함수 (원문 7장, game_sim/bt/need.py 대응).
// 점수 S = N × w. N 은 매 결정마다 상태로 계산, w 는 구간(판) 내내 고정. N 이 null 이면 후보 제외.
using System;
using Qa.Data;

namespace Qa.BT
{
    public abstract class NeedFunction
    {
        public abstract double? Value(Blackboard bb);
    }

    /// <summary>쿨 준비 시 0.8, 아니면 후보 제외.</summary>
    public sealed class BurstNeed : NeedFunction
    {
        public const double Base = 0.8;
        public static double? Compute(bool burstReady) => burstReady ? Base : (double?)null;
        public override double? Value(Blackboard bb) => Compute(bb.AnyAvailable(SkillRole.Burst));
    }

    /// <summary>체력이 φ 아래면 딜 의지 감소: 0.5 × min(1, hp/φ). 적이 사거리 밖이면 제외.</summary>
    public sealed class DpsNeed : NeedFunction
    {
        public const double Base = 0.5;
        public static double Compute(double hp, double phi) => Base * Math.Min(1.0, hp / phi);

        public override double? Value(Blackboard bb)
        {
            if (!bb.InRange(bb.BasicSkill)) return null;
            return Compute(bb.Obs.HpRatio, bb.P("dps_hp_floor"));
        }
    }

    /// <summary>체력이 θ 아래로 내려가면 상승: max(0, (θ − hp)/θ).</summary>
    public sealed class SurvivalNeed : NeedFunction
    {
        public static double Compute(double hp, double theta) => Math.Max(0.0, (theta - hp) / theta);
        public override double? Value(Blackboard bb) => Compute(bb.Obs.HpRatio, bb.P("survival_hp_threshold"));
    }
}
