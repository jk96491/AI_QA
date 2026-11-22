// 직업별 전투 BT 에이전트 (game_sim/bt/agent.py 대응).
//
// Root (Selector)
// ├─ [강제] 기믹 경고 중? → 기믹 대응 블록
// └─ 전략 선택 노드 (S = N × w)
//    ├─ 버스트 콤보 (w_burst)
//    ├─ 딜 유지     (w_dps)
//    └─ 생존 모드   (w_survival)
//    (후보 없음 → 접근)
using Qa.Data;
using Qa.Sim;

namespace Qa.BT
{
    public sealed class BTAgent
    {
        public readonly ClassSpec Spec;
        readonly Blackboard _bb;
        readonly Node _root;

        public BTAgent(ClassSpec spec)
        {
            Spec = spec;
            _bb = new Blackboard(spec);
            _root = Build(spec);
        }

        /// <summary>강제 블록 진입을 블랙보드에 표시.</summary>
        sealed class MarkBlock : Node
        {
            readonly string _block;
            public MarkBlock(string block) : base("mark_" + block) { _block = block; }

            public override Status Tick(Blackboard bb)
            {
                if (bb.CurrentBlock != _block)
                {
                    bb.CurrentBlock = _block;
                    bb.BlockSince = bb.Obs.Time;
                }
                return Status.Success;
            }
        }

        static Node Build(ClassSpec spec)
        {
            var gimmick = new GimmickBlock();
            var utility = new UtilitySelector("strategy", new[]
            {
                new UtilityOption(BurstBlock.Name, new BurstBlock().Build(), new BurstNeed(), "w_burst"),
                new UtilityOption(DpsBlock.Name, new DpsBlock().Build(), new DpsNeed(), "w_dps"),
                // 생존 블록 최대 유지 시간 (정의서 bt_rules): 회복이 안 되는데 생존에 갇혀 멈추는 판 방지
                new UtilityOption(SurvivalBlock.Name, new SurvivalBlock().Build(), new SurvivalNeed(), "w_survival",
                                  spec.SurvivalMaxHold, spec.SurvivalLockout),
            }, ApproachBlock.Name, new ApproachBlock().Build());
            var forced = new Sequence("forced_gimmick",
                new Condition("gimmick_warning", bb => bb.Obs != null && bb.Obs.GimmickWarning),
                new MarkBlock(GimmickBlock.Name),
                gimmick.Build());
            return new Selector("root", forced, utility);
        }

        /// <summary>트리거 사이 구간에서 쓸 파라미터 교체 (다음 트리거까지 고정).</summary>
        public void SetParams(ParamValues p) => _bb.Params = p.Clone();

        public string CurrentBlock => _bb.CurrentBlock;

        public BtAction Decide(Observation obs)
        {
            _bb.Obs = obs;
            _bb.Action = null;
            _root.Tick(_bb);
            return _bb.Action ?? BtAction.Idle;
        }
    }
}
