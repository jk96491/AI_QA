// 범용 BT 노드 (컨텍스트 타입 T). 보스 BT 가 쓴다.
// 플레이어 BT(Nodes.cs)는 game_sim 과 1:1 대응을 유지하기 위해 별도로 둔다.
using System;

namespace Qa.BT
{
    public abstract class BtNode<T>
    {
        public readonly string Name;
        protected BtNode(string name) { Name = name; }
        public abstract Status Tick(T ctx);
        public override string ToString() => GetType().Name + "(" + Name + ")";
    }

    /// <summary>처음으로 실패하지 않은 자식의 결과 (고정 우선순위).</summary>
    public sealed class BtSelector<T> : BtNode<T>
    {
        readonly BtNode<T>[] _children;
        public BtSelector(string name, params BtNode<T>[] children) : base(name) { _children = children; }

        public override Status Tick(T ctx)
        {
            foreach (var c in _children)
            {
                var s = c.Tick(ctx);
                if (s != Status.Failure) return s;
            }
            return Status.Failure;
        }
    }

    /// <summary>자식이 모두 성공해야 성공.</summary>
    public sealed class BtSequence<T> : BtNode<T>
    {
        readonly BtNode<T>[] _children;
        public BtSequence(string name, params BtNode<T>[] children) : base(name) { _children = children; }

        public override Status Tick(T ctx)
        {
            foreach (var c in _children)
            {
                var s = c.Tick(ctx);
                if (s != Status.Success) return s;
            }
            return Status.Success;
        }
    }

    public sealed class BtCondition<T> : BtNode<T>
    {
        readonly Func<T, bool> _pred;
        public BtCondition(string name, Func<T, bool> pred) : base(name) { _pred = pred; }
        public override Status Tick(T ctx) => _pred(ctx) ? Status.Success : Status.Failure;
    }

    /// <summary>행동 리프. 함수가 false 면 실패.</summary>
    public sealed class BtDo<T> : BtNode<T>
    {
        readonly Func<T, bool> _fn;
        public BtDo(string name, Func<T, bool> fn) : base(name) { _fn = fn; }
        public override Status Tick(T ctx) => _fn(ctx) ? Status.Success : Status.Failure;
    }
}
