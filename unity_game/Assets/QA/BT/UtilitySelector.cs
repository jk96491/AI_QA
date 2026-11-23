// 위층 전략 선택 노드: 점수 기반 선택 (원문 6·7장, game_sim/bt/selector.py 대응).
using System.Collections.Generic;

namespace Qa.BT
{
    public sealed class UtilityOption
    {
        public readonly string Name;
        public readonly Node Node;
        public readonly NeedFunction Need;
        public readonly string WeightKey;
        /// <summary>이 블록을 연속으로 유지할 수 있는 최대 시간(초). 0 = 제한 없음.</summary>
        public readonly double MaxHold;
        /// <summary>MaxHold 를 넘기면 이 시간(초) 동안 후보에서 제외.</summary>
        public readonly double Lockout;

        public UtilityOption(string name, Node node, NeedFunction need, string weightKey, double maxHold = 0, double lockout = 0)
        {
            Name = name; Node = node; Need = need; WeightKey = weightKey; MaxHold = maxHold; Lockout = lockout;
        }
    }

    /// <summary>
    /// 실행 가능한 블록 중 S = N × w 가 가장 큰 블록을 실행.
    /// - N 이 null(후보 제외) 이거나 S 가 0 인 블록은 후보가 아님
    /// - min_commit 초 동안은 현재 블록이 후보에 남아 있으면 유지 (떨림 방지)
    /// - 선택된 블록이 실패하면 fallback 블록 실행
    /// </summary>
    public sealed class UtilitySelector : Node
    {
        readonly UtilityOption[] _options;
        readonly string _fallbackName;
        readonly Node _fallback;

        // 판 루프 할당 방지용 작업 버퍼
        readonly List<UtilityOption> _scored = new List<UtilityOption>();
        readonly List<double> _scores = new List<double>();

        // 최대 유지 시간 규칙: 옵션별 '후보 제외 끝나는 시각' (판마다 새 에이전트 → 판 사이 상태 없음)
        readonly double[] _lockedUntil;
        // 연속 유지 시작 시각 (NaN = 지금 유지 중 아님). 0.8.1: 회피·기믹으로 잠깐 끊겨도 이어서 센다
        readonly double[] _holdSince;
        /// <summary>다른 블록의 연속 유지 시간을 끊지 않는 블록 (짧은 끼어들기).</summary>
        static readonly string[] Transparent = { "evade", "gimmick" };

        public UtilitySelector(string name, UtilityOption[] options, string fallbackName, Node fallback) : base(name)
        {
            _options = options;
            _fallbackName = fallbackName;
            _fallback = fallback;
            _lockedUntil = new double[options.Length];
            for (int i = 0; i < _lockedUntil.Length; i++) _lockedUntil[i] = double.NegativeInfinity;
            _holdSince = new double[options.Length];
            for (int i = 0; i < _holdSince.Length; i++) _holdSince[i] = double.NaN;
        }

        /// <summary>현재 블록이 최대 유지 시간을 넘겼으면 잠그고, 잠긴 동안이면 true.</summary>
        bool Locked(Blackboard bb, int i)
        {
            var opt = _options[i];
            double now = bb.Obs.Time;
            UpdateHold(bb, i);
            if (opt.MaxHold > 0 && !double.IsNaN(_holdSince[i]) && now - _holdSince[i] >= opt.MaxHold - 1e-9)
            {
                _lockedUntil[i] = now + opt.Lockout;
                _holdSince[i] = double.NaN;
            }
            return now < _lockedUntil[i] - 1e-9;
        }

        /// <summary>현재 블록 기준으로 옵션 i 의 연속 유지 시작 시각 갱신.</summary>
        void UpdateHold(Blackboard bb, int i)
        {
            var name = _options[i].Name;
            if (bb.CurrentBlock == name) { if (double.IsNaN(_holdSince[i])) _holdSince[i] = bb.BlockSince; }
            else if (System.Array.IndexOf(Transparent, bb.CurrentBlock) < 0) _holdSince[i] = double.NaN;
        }

        /// <summary>후보를 점수 내림차순으로 채운다. 동점이면 정의 순서 유지 (안정 삽입 정렬 → 결정론).</summary>
        void Score(Blackboard bb)
        {
            _scored.Clear();
            _scores.Clear();
            for (int oi = 0; oi < _options.Length; oi++)
            {
                var opt = _options[oi];
                if (Locked(bb, oi)) continue;   // 최대 유지 시간 초과 → 잠시 후보 제외
                var n = opt.Need.Value(bb);
                if (n == null) continue;
                double s = n.Value * bb.P(opt.WeightKey);
                if (s <= 1e-9) continue;   // 필요도(또는 가중치) 0 → '필요 없음' → 후보 제외
                int i = _scored.Count;
                _scored.Add(opt);
                _scores.Add(s);
                while (i > 0 && _scores[i - 1] < s)
                {
                    _scored[i] = _scored[i - 1];
                    _scores[i] = _scores[i - 1];
                    i--;
                }
                _scored[i] = opt;
                _scores[i] = s;
            }
        }

        UtilityOption Choose(Blackboard bb)
        {
            if (_scored.Count == 0) return null;
            var best = _scored[0];
            double minCommit = bb.P("min_commit", 0.0);
            if (bb.CurrentBlock != best.Name && bb.Obs.Time - bb.BlockSince < minCommit)
                foreach (var opt in _scored)
                    if (opt.Name == bb.CurrentBlock) return opt;
            return best;
        }

        static void Switch(Blackboard bb, string name)
        {
            if (bb.CurrentBlock != name)
            {
                bb.CurrentBlock = name;
                bb.BlockSince = bb.Obs.Time;
            }
        }

        public override Status Tick(Blackboard bb)
        {
            Score(bb);
            var chosen = Choose(bb);
            if (chosen != null)
            {
                Switch(bb, chosen.Name);
                var st = chosen.Node.Tick(bb);
                if (st != Status.Failure) return st;
            }
            Switch(bb, _fallbackName);
            return _fallback.Tick(bb);
        }
    }
}
