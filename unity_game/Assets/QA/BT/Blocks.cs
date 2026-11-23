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

        /// <summary>같은 역할 중 점수 최대 스킬 (0.8.1 블록 안 스킬 고르기, 고정 규칙).</summary>
        protected static Func<Blackboard, BtAction> UseScored(SkillRole role, bool respectReserve = false)
        {
            return bb =>
            {
                var s = bb.BestUsable(role, respectReserve, 0.9);
                return s != null ? bb.UseAction(s) : null;
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

        /// <summary>버스트 직전: 콤보용 Setup(피해 버프·표식)이 준비됐고 아직 효과가 없으면 먼저 건다.</summary>
        static bool SetupFirst(Blackboard bb) => !bb.Obs.BuffActive && !bb.Obs.TargetMarked && UseComboSetup(bb) != null;

        static BtAction UseComboSetup(Blackboard bb)
        {
            foreach (var s in bb.Skills(SkillRole.Setup))
                if (s.IsComboSetup && bb.UsableNow(s) && bb.InRange(s)) return bb.UseAction(s);
            return null;
        }

        public override Node Build()
        {
            return new Selector(Name,
                new Sequence("combo_setup", new Condition("setup_first", SetupFirst), new Act("use_setup", UseComboSetup)),
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
                new Act("use_dps", UseScored(SkillRole.Dps, respectReserve: true)),
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
        static bool FarForCharge(Blackboard bb) => bb.Obs.Distance > bb.P("charge_distance", 1e9);

        /// <summary>0.8.1: 돌진(gap_close)은 원래 dps 블록 안에만 있었는데, dps 필요도는 사거리 밖이면 후보 제외라 한 번도 실행되지 않았다 → 여기서도.</summary>
        public override Node Build() => new Selector(Name,
            new Sequence("charge", new Condition("far", FarForCharge), new Act("gap_close", UseBest(SkillRole.GapClose))),
            new Act("approach", MoveToward));
    }

    /// <summary>위험 회피 (0.8.1, w_evade): 이동기 준비면 사용, 아니면 안전 지점으로 걷기.</summary>
    public sealed class EvadeBlock : Block
    {
        public const string Name = "evade";
        public override string BlockName => Name;
        public override Node Build() => new Selector(Name,
            new Act("mobility", UseBest(SkillRole.Mobility)),
            new Act("walk_to_safe", _ => BtAction.Evade));
    }

    /// <summary>준비 (0.8.1, w_setup): Setup 스킬(버프·자원), 없으면 평타로 자원 쌓기.</summary>
    public sealed class SetupBlock : Block
    {
        public const string Name = "setup";
        public override string BlockName => Name;
        public override Node Build() => new Selector(Name,
            new Act("use_setup", UseBest(SkillRole.Setup)),
            new Act("build_resource", UseBest(SkillRole.Basic)),
            new Act("approach", MoveToward));
    }
}
