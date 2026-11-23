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

    /// <summary>쿨 준비 시 0.8 (+0.3: Setup 버프·표식 중 — 콤보 창), 아니면 후보 제외.</summary>
    public sealed class BurstNeed : NeedFunction
    {
        public const double Base = 0.8, ComboBonus = 0.3;
        public static double? Compute(bool burstReady) => burstReady ? Base : (double?)null;
        public override double? Value(Blackboard bb)
        {
            var n = Compute(bb.AnyAvailable(SkillRole.Burst));
            if (n == null) return null;
            return n.Value + (bb.Obs.BuffActive || bb.Obs.TargetMarked ? ComboBonus : 0.0);
        }
    }

    /// <summary>위험도 danger (아레나 패턴, 0.8.1 에서 생존 N 에서 옮김). 위험 없으면 후보 제외.</summary>
    public sealed class EvadeNeed : NeedFunction
    {
        public override double? Value(Blackboard bb) => bb.Obs.Danger > 1e-9 ? bb.Obs.Danger : (double?)null;
    }

    /// <summary>Setup 스킬 준비 + (버스트가 combo_window 초 안에 준비 / 자원 부족) → 0.6, 아니면 후보 제외.</summary>
    public sealed class SetupNeed : NeedFunction
    {
        public const double Base = 0.6;
        public override double? Value(Blackboard bb)
        {
            bool any = false;
            foreach (var s in bb.Skills(SkillRole.Setup)) if (bb.Available(s)) { any = true; break; }
            if (!any) return null;
            if (bb.BurstSoon(bb.P("combo_window", 4.0)) && !bb.Obs.BuffActive && !bb.Obs.TargetMarked) return Base;
            if (bb.Obs.ResourceRatio < 0.3 && bb.InRange(bb.BasicSkill)) return Base;   // 자원 쌓기는 칠 수 있을 때만 (멀면 approach 블록이 돌진으로 붙는다)
            return null;
        }
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

    /// <summary>체력이 θ 아래로 내려가면 상승: max(0, (θ − hp)/θ). (0.8.1: 위험도는 evade 블록으로 분리)</summary>
    public sealed class SurvivalNeed : NeedFunction
    {
        public static double Compute(double hp, double theta) => Math.Max(0.0, (theta - hp) / theta);
        public override double? Value(Blackboard bb) => Compute(bb.Obs.HpRatio, bb.P("survival_hp_threshold"));
    }
}
