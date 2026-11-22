// 아래층 행동 블록 (고정 서브트리, 원문 6장 / game_sim/bt/blocks.py 대응).
// 블록 내부 구조는 고정이고, 상수는 블랙보드 파라미터(potion_hp, kite_distance 등)로만 참조한다.
using System;
using Qa.Data;
using Qa.Sim;

namespace Qa.BT
{
    public abstract class Block
    {
        public abstract string BlockName { get; }
        public abstract Node Build();

        // ---------------------------------------------------------------- 공통 리프 함수
        protected static Func<Blackboard, BtAction> UseBest(SkillRole role, bool respectReserve = false)
        {
            return bb =>
            {
                foreach (var s in bb.Skills(role))
                {
                    if (!bb.UsableNow(s) || !bb.InRange(s)) continue;
                    if (respectReserve && !bb.KeepsReserve(s)) continue;
                    return bb.UseAction(s);
                }
                return null;
            };
        }

        protected static BtAction MoveToward(Blackboard bb) => BtAction.MoveToward;
        protected static BtAction MoveAway(Blackboard bb) => BtAction.MoveAway;
        protected static BtAction Wait(Blackboard bb) => BtAction.Idle;

        protected static bool GcdPendingInRange(Blackboard bb) => !bb.Obs.GcdReady && bb.InRange(bb.BasicSkill);

        /// <summary>원거리: 보스와 거리가 kite_distance 보다 가까우면 거리 벌리기.</summary>
        protected static bool TooClose(Blackboard bb) => bb.Spec.Ranged && bb.Obs.Distance < bb.P("kite_distance", 0.0);
    }

    public sealed class BurstBlock : Block
    {
        public const string Name = "burst";
        public override string BlockName => Name;

        public override Node Build()
        {
            return new Selector(Name,
                new Act("use_burst", UseBest(SkillRole.Burst)),
                new Sequence("wait_gcd", new Condition("gcd_pending", GcdPendingInRange), new Act("idle", Wait)),
                new Act("approach", MoveToward));
        }
    }

    public sealed class DpsBlock : Block
    {
        public const string Name = "dps";
        public override string BlockName => Name;

        static bool FarForCharge(Blackboard bb) => bb.Obs.Distance > bb.P("charge_distance", 1e9);

        public override Node Build()
        {
            return new Selector(Name,
                new Sequence("kite", new Condition("too_close", TooClose), new Act("move_away", MoveAway)),
                new Sequence("charge", new Condition("far", FarForCharge), new Act("gap_close", UseBest(SkillRole.GapClose))),
                new Act("use_dps", UseBest(SkillRole.Dps, respectReserve: true)),
                new Act("use_basic", UseBest(SkillRole.Basic)),
                new Sequence("wait_gcd", new Condition("gcd_pending", GcdPendingInRange), new Act("idle", Wait)),
                new Act("approach", MoveToward));
        }
    }

    public sealed class SurvivalBlock : Block
    {
        public const string Name = "survival";
        public const double SafeMargin = 4.0;
        public override string BlockName => Name;

        static bool NeedsPotion(Blackboard bb) => bb.Obs.PotionReady && bb.Obs.HpRatio < bb.P("potion_hp");

        /// <summary>보스 사거리 + 안전 여유 안이면 후퇴 (회복이 시작되도록 거리 확보).</summary>
        static bool BossNear(Blackboard bb) => bb.Obs.Distance < bb.Obs.BossReach + SafeMargin;

        public override Node Build()
        {
            return new Selector(Name,
                new Sequence("potion", new Condition("needs_potion", NeedsPotion), new Act("drink", _ => BtAction.Potion)),
                new Act("defend", UseBest(SkillRole.Defense)),
                new Sequence("retreat", new Condition("boss_near", BossNear), new Act("move_away", MoveAway)),
                new Act("poke", UseBest(SkillRole.Basic)),
                new Act("idle", Wait));
        }
    }

    /// <summary>기믹 경고 시 강제 선택.</summary>
    public sealed class GimmickBlock : Block
    {
        public const string Name = "gimmick";
        public override string BlockName => Name;
        public override Node Build() => new Act("respond", _ => BtAction.RespondGimmick);
    }

    /// <summary>후보 블록이 하나도 없을 때의 기본 동작.</summary>
    public sealed class ApproachBlock : Block
    {
        public const string Name = "approach";
        public override string BlockName => Name;
        public override Node Build() => new Selector(Name, new Act("approach", MoveToward));
    }
}
