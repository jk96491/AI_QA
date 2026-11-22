// 보스 엔티티 + 고정 BT (학습 대상 아님 — 상수는 bosses/*.json, describe 로 공개하지 않는다).
//
// 보스 BT (0.3초마다, 준비 동작 중에는 쉬지 않고 동작 완료까지 대기)
// Root (Selector)
// ├─ 기믹 시작     : 기믹 타이머 준비 + 대상 생존 → 경고 (제한 시간 내 미대응 시 최대 체력 비례 피해)
// ├─ 광역기        : 타이머 준비 + 대상 생존 → 거리 무관 피해
// ├─ 처형          : 페이즈 ≥ execute_phase_min, 대상 체력 < execute_hp_below, 사거리 안 → 준비 후 큰 피해
// ├─ 도약          : 페이즈 ≥ leap_phase_min, 거리 > leap_min_distance → 준비 후 대상 앞에 착지하며 피해
// ├─ 투척          : 거리 > reach + throw_min_gap → 준비 후 원거리 피해 (회피기로 피함)
// ├─ 내려찍기      : 사거리 안 → 준비 후, 그때도 사거리(+보정) 안이면 피해 (뒤로 빠지면 회피)
// ├─ 평타          : 사거리 안 + 평타 준비
// ├─ 추격          : 사거리 밖 → 접근
// └─ 대기
// 모든 피해 × 페이즈 배율 × (격노 시 enrage_damage_mult) × 난수(±damage_variance)
using System;
using System.Collections.Generic;
using Qa.BT;
using Qa.Data;

namespace Qa.Sim
{
    public enum BossAttackKind { Auto, Aoe, Gimmick, Cleave, Leap, Execute, Throw }

    public struct BossAttack
    {
        public BossAttackKind Kind;
        public double RawDamage;
        public bool IgnoreMitigation;
        public double HpRatioDamage;   // 플레이어 최대 체력 비례 피해 (기믹)

        public string KindName
        {
            get
            {
                switch (Kind)
                {
                    case BossAttackKind.Auto: return "auto";
                    case BossAttackKind.Aoe: return "aoe";
                    case BossAttackKind.Gimmick: return "gimmick";
                    case BossAttackKind.Cleave: return "cleave";
                    case BossAttackKind.Leap: return "leap";
                    case BossAttackKind.Throw: return "throw";
                    default: return "execute";
                }
            }
        }
    }

    public sealed class Boss
    {
        const double Eps = SimConst.Eps;

        public readonly BossSpec Spec;
        readonly Rng _rng;
        public double Hp;
        public int Phase;

        // 쿨다운 (≤0 이면 준비)
        double _autoCd, _aoeCd, _gimmickCd, _cleaveCd, _leapCd, _executeCd, _throwCd;
        double _gimmickRemaining;   // >0 이면 경고 중

        // 준비 동작 (windup)
        BossAttackKind _pending;
        double _windup;
        bool _winding;

        // BT 컨텍스트 (Update 동안만 유효)
        double _distance, _playerHp, _time, _dt;
        bool _targetAlive;
        List<BossAttack> _out;

        // ----- 읽기 전용 (화면 표시용) -----
        public bool Winding => _winding;
        public BossAttackKind PendingKind => _pending;
        public double WindupLeft => _windup;
        public double GimmickLeft => _gimmickRemaining;

        /// <summary>이번 틱에 시작한 기술 이름 (이벤트 기록용, 없으면 null).</summary>
        public string StartedMove { get; private set; }

        static readonly BtNode<Boss> Brain = BuildBrain();

        public Boss(BossSpec spec, Rng rng)
        {
            Spec = spec;
            _rng = rng;
            Hp = spec.MaxHp;
            _autoCd = spec.AutoInterval;
            _aoeCd = Jittered(spec.AoeInterval, spec.AoeJitter);
            _gimmickCd = Jittered(spec.GimmickFirstAt, spec.GimmickJitter);
            _cleaveCd = spec.CleaveCooldown * 0.5;
            _leapCd = 0.0;
            _executeCd = 0.0;
            _throwCd = spec.ThrowCooldown * 0.5;
        }

        double Jittered(double b, double jitter) => Math.Max(1.0, b + _rng.Uniform(-jitter, jitter));

        // ----- 상태 -----
        public double HpRatio => Math.Max(0.0, Hp / Spec.MaxHp);
        public bool Alive => Hp > Eps;
        public bool GimmickWarning => _gimmickRemaining > Eps;
        public bool Enraged => Spec.EnrageTime > 0 && _time >= Spec.EnrageTime;
        double DamageMult => Spec.PhaseDamageMult[Phase] * (Enraged ? Spec.EnrageDamageMult : 1.0);
        double SpeedMult => Spec.PhaseSpeedMult[Phase];
        bool InReach => _distance <= Spec.Reach + Eps;

        // ----- 피격 -----
        /// <summary>피해 적용. 새로 넘어간 페이즈 경계를 crossed 에 채운다 (비우고 시작).</summary>
        public void TakeDamage(double amount, List<double> crossed)
        {
            crossed.Clear();
            double before = HpRatio;
            Hp = Math.Max(0.0, Hp - amount);
            double after = HpRatio;
            foreach (var t in Spec.PhaseThresholds)
                if (before > t && t >= after) crossed.Add(t);
            Phase += crossed.Count;
        }

        public bool ResolveGimmick()
        {
            if (!GimmickWarning) return false;
            _gimmickRemaining = 0.0;
            return true;
        }

        double Roll(double b)
        {
            double v = Spec.DamageVariance;
            return b * DamageMult * _rng.Uniform(1.0 - v, 1.0 + v);
        }

        void Hit(BossAttackKind kind, double baseDamage) =>
            _out.Add(new BossAttack { Kind = kind, RawDamage = Roll(baseDamage) });

        // ----- 시간 경과 -----
        /// <summary>쿨다운·기믹 처리 + 보스 BT 1회. 새 거리를 반환하고 공격은 attacks 에 채운다 (비우고 시작).</summary>
        public double Update(double dt, double distance, bool targetAlive, double playerHpRatio, double time, List<BossAttack> attacks)
        {
            attacks.Clear();
            _out = attacks;
            _distance = distance;
            _targetAlive = targetAlive;
            _playerHp = playerHpRatio;
            _time = time;
            _dt = dt;
            StartedMove = null;

            _autoCd -= dt * SpeedMult;
            _aoeCd -= dt;
            _cleaveCd -= dt;
            _leapCd -= dt;
            _executeCd -= dt;
            _throwCd -= dt;

            // 기믹 경고 진행 (보스 행동과 별개로 흐른다)
            if (GimmickWarning)
            {
                _gimmickRemaining -= dt;
                if (_gimmickRemaining <= Eps)
                {
                    _gimmickRemaining = 0.0;
                    if (targetAlive)
                        attacks.Add(new BossAttack
                        {
                            Kind = BossAttackKind.Gimmick, RawDamage = 0.0, IgnoreMitigation = true,
                            HpRatioDamage = Spec.GimmickDamageRatio,
                        });
                }
            }
            else _gimmickCd -= dt;

            // 대상이 죽어 있는 동안 준비된 광역기·기믹은 건너뛴다 (부활 직후 몰아치기 방지)
            if (!targetAlive)
            {
                if (_aoeCd <= Eps) _aoeCd = Jittered(Spec.AoeInterval, Spec.AoeJitter);
                if (_gimmickCd <= Eps && !GimmickWarning) _gimmickCd = Jittered(Spec.GimmickInterval, Spec.GimmickJitter);
            }

            if (_winding)
            {
                _windup -= dt;
                if (_windup <= Eps)
                {
                    _winding = false;
                    ResolvePending();
                }
            }
            else
            {
                Brain.Tick(this);
            }

            _out = null;
            return _distance;
        }

        void StartWindup(BossAttackKind kind, double windup, string name)
        {
            StartedMove = name;
            if (windup <= Eps)
            {
                _pending = kind;
                ResolvePending();
                return;
            }
            _pending = kind;
            _windup = windup;
            _winding = true;
        }

        void ResolvePending()
        {
            if (!_targetAlive) return;
            var s = Spec;
            switch (_pending)
            {
                case BossAttackKind.Cleave:
                    if (_distance <= s.Reach + s.CleaveRangeBonus + Eps) Hit(BossAttackKind.Cleave, s.CleaveDamage);
                    break;
                case BossAttackKind.Leap:
                    _distance = Math.Max(1.0, s.Reach - 0.5);
                    Hit(BossAttackKind.Leap, s.LeapDamage);
                    break;
                case BossAttackKind.Throw:
                    Hit(BossAttackKind.Throw, s.ThrowDamage);
                    break;
                case BossAttackKind.Execute:
                    if (_distance <= s.Reach + 0.5 + Eps) Hit(BossAttackKind.Execute, s.ExecuteDamage);
                    break;
            }
        }

        // ------------------------------------------------------------------ 보스 BT (고정)
        static BtNode<Boss> BuildBrain()
        {
            return new BtSelector<Boss>("boss_root",
                new BtSequence<Boss>("gimmick",
                    new BtCondition<Boss>("gimmick_ready", b => b._targetAlive && !b.GimmickWarning && b._gimmickCd <= Eps),
                    new BtDo<Boss>("start_gimmick", b =>
                    {
                        b._gimmickRemaining = b.Spec.GimmickWindow;
                        b._gimmickCd = b.Jittered(b.Spec.GimmickInterval, b.Spec.GimmickJitter);
                        b.StartedMove = "gimmick";
                        return true;
                    })),
                new BtSequence<Boss>("aoe",
                    new BtCondition<Boss>("aoe_ready", b => b._targetAlive && b._aoeCd <= Eps),
                    new BtDo<Boss>("cast_aoe", b =>
                    {
                        b.Hit(BossAttackKind.Aoe, b.Spec.AoeDamage);
                        b._aoeCd = b.Jittered(b.Spec.AoeInterval, b.Spec.AoeJitter);
                        b.StartedMove = "aoe";
                        return true;
                    })),
                new BtSequence<Boss>("execute",
                    new BtCondition<Boss>("execute_ready", b =>
                        b.Spec.ExecuteDamage > 0 && b._targetAlive && b.Phase >= b.Spec.ExecutePhaseMin &&
                        b._playerHp < b.Spec.ExecuteHpBelow && b.InReach && b._executeCd <= Eps),
                    new BtDo<Boss>("start_execute", b =>
                    {
                        b._executeCd = b.Spec.ExecuteCooldown;
                        b.StartWindup(BossAttackKind.Execute, b.Spec.ExecuteWindup, "execute");
                        return true;
                    })),
                new BtSequence<Boss>("leap",
                    new BtCondition<Boss>("leap_ready", b =>
                        b.Spec.LeapDamage > 0 && b._targetAlive && b.Phase >= b.Spec.LeapPhaseMin &&
                        b._distance > b.Spec.LeapMinDistance + Eps && b._leapCd <= Eps),
                    new BtDo<Boss>("start_leap", b =>
                    {
                        b._leapCd = b.Spec.LeapCooldown;
                        b.StartWindup(BossAttackKind.Leap, b.Spec.LeapWindup, "leap");
                        return true;
                    })),
                new BtSequence<Boss>("throw",
                    new BtCondition<Boss>("throw_ready", b =>
                        b.Spec.ThrowDamage > 0 && b._targetAlive && b.Phase >= b.Spec.ThrowPhaseMin && b._distance > b.Spec.Reach + b.Spec.ThrowMinGap + Eps && b._throwCd <= Eps),
                    new BtDo<Boss>("start_throw", b =>
                    {
                        b._throwCd = b.Spec.ThrowCooldown;
                        b.StartWindup(BossAttackKind.Throw, b.Spec.ThrowWindup, "throw");
                        return true;
                    })),
                new BtSequence<Boss>("cleave",
                    new BtCondition<Boss>("cleave_ready", b =>
                        b.Spec.CleaveDamage > 0 && b._targetAlive && b.InReach && b._cleaveCd <= Eps),
                    new BtDo<Boss>("start_cleave", b =>
                    {
                        b._cleaveCd = b.Spec.CleaveCooldown;
                        b.StartWindup(BossAttackKind.Cleave, b.Spec.CleaveWindup, "cleave");
                        return true;
                    })),
                new BtSequence<Boss>("auto",
                    new BtCondition<Boss>("auto_ready", b => b._targetAlive && b.InReach && b._autoCd <= Eps),
                    new BtDo<Boss>("auto_attack", b =>
                    {
                        b.Hit(BossAttackKind.Auto, b.Spec.AutoDamage);
                        b._autoCd = b.Spec.AutoInterval;
                        return true;
                    })),
                new BtSequence<Boss>("chase",
                    new BtCondition<Boss>("out_of_reach", b => !b.InReach),
                    new BtDo<Boss>("move", b =>
                    {
                        b._distance = Math.Max(b.Spec.Reach, b._distance - b.Spec.MoveSpeed * b.SpeedMult * b._dt);
                        return true;
                    })),
                new BtDo<Boss>("idle", _ => true));
        }
    }
}
