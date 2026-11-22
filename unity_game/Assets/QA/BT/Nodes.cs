// BT 기본 노드 (game_sim/bt/node.py 대응).
using System;
using System.Collections.Generic;
using Qa.Sim;

namespace Qa.BT
{
    public enum Status { Success, Failure, Running }

    public abstract class Node
    {
        public readonly string Name;
        protected Node(string name) { Name = name; }
        public abstract Status Tick(Blackboard bb);
        public override string ToString() => GetType().Name + "(" + Name + ")";
    }

    /// <summary>자식이 모두 성공해야 성공.</summary>
    public sealed class Sequence : Node
    {
        readonly Node[] _children;
        public Sequence(string name, params Node[] children) : base(name) { _children = children; }

        public override Status Tick(Blackboard bb)
        {
            foreach (var c in _children)
            {
                var s = c.Tick(bb);
                if (s != Status.Success) return s;
            }
            return Status.Success;
        }
    }

    /// <summary>처음으로 실패하지 않은 자식의 결과 (고정 우선순위).</summary>
    public sealed class Selector : Node
    {
        readonly Node[] _children;
        public Selector(string name, params Node[] children) : base(name) { _children = children; }

        public override Status Tick(Blackboard bb)
        {
            foreach (var c in _children)
            {
                var s = c.Tick(bb);
                if (s != Status.Failure) return s;
            }
            return Status.Failure;
        }
    }

    public sealed class Condition : Node
    {
        readonly Func<Blackboard, bool> _pred;
        public Condition(string name, Func<Blackboard, bool> pred) : base(name) { _pred = pred; }
        public override Status Tick(Blackboard bb) => _pred(bb) ? Status.Success : Status.Failure;
    }

    /// <summary>행동을 고르는 리프. 함수가 null 이면 실패.</summary>
    public sealed class Act : Node
    {
        readonly Func<Blackboard, BtAction> _fn;
        public Act(string name, Func<Blackboard, BtAction> fn) : base(name) { _fn = fn; }

        public override Status Tick(Blackboard bb)
        {
            var a = _fn(bb);
            if (a == null) return Status.Failure;
            bb.Action = a;
            return Status.Success;
        }
    }
}
