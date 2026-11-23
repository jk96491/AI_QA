// 틱 기반 전투 시뮬레이터 (헤드리스, 시드 결정론) — game_sim/sim/engine.py 대응.
//
// 학습 쪽과의 접점 (PROTOCOL.md run_episode / trigger):
//   params     : 판 시작 시 BT 파라미터 (정의서 이름 → 값, 생략 = default)
//   onTrigger  : 결정 트리거마다 호출. (index, state, totals) → 갱신할 파라미터 (부분 덮어쓰기)
//
// 같은 (class, boss, params, triggers, seed, config, 트리거 응답) → 항상 같은 결과.
// 로직은 고정 dt 수동 루프로만 진행 (프레임·시계·코루틴과 무관).
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.BT;
using Qa.Data;

namespace Qa.Sim
{
    /// <summary>(트리거 번호, 정규화 상태, 누적값) → 갱신 파라미터 (null 가능).</summary>
    public delegate JObject TriggerHandler(int index, JObject state, JObject totals);

    public sealed class CombatSim
    {
        const double Eps = SimConst.Eps;

        readonly SimConfig _cfg;
        readonly ClassSpec _spec;
        readonly BossSpec _bossSpec;
        readonly TriggerHandler _onTrigger;
        readonly JToken _seedToken;
        readonly Rng _rng;
        readonly EventLog _log;

        readonly Player _p;
        readonly Boss _boss;
        readonly BTAgent _agent;
        readonly Arena _arena;          // 2D 아레나 패턴 (보스 arena_radius > 0 일 때만, 0.8.0)
        bool _evading;
        readonly int[] _skillUses;
        int _castCancels;
        string _lastSetup;
        double _lastSetupT;
        /// <summary>스킬별 사용 횟수 (SkillDef.Index) — 보고서·하네스용, 결과 JSON 에는 없음.</summary>
        public int[] SkillUses => _skillUses;
        public int CastCancels => _castCancels;
        readonly Observation _obs = new Observation();
        ParamValues _params;
        double _distance;
        double _t;

        // 집계
        int _deaths, _consumables, _gimmickSuccess, _gimmickFail, _invalidActions, _triggersFired;
        double _damageDealt, _damageTaken, _lastDamageT;
        readonly OrderedAccumulator _blockTime = new OrderedAccumulator();
        readonly List<double> _phaseTimes = new List<double>();
        readonly List<double> _pendingTriggers;   // 내림차순
        readonly bool _useTriggers;
        readonly SkillDef[] _bursts;

        // 루프 작업 버퍼
        readonly List<double> _crossed = new List<double>();
        readonly List<BossAttack> _attacks = new List<BossAttack>();

        public CombatSim(ClassSpec spec, BossSpec boss, JObject paramUpdates, long seed, JToken seedToken,
                         SimConfig cfg, IList<double> triggers, TriggerHandler onTrigger)
        {
            _cfg = cfg ?? new SimConfig();
            _spec = spec;
            _bossSpec = boss;
            // 정의서 default 위에 요청 파라미터를 덮어씀 (이름·범위 검사 → ParamException)
            _params = spec.ResolveParams(spec.DefaultParams(), paramUpdates);
            _onTrigger = onTrigger;
            _seedToken = seedToken ?? new JValue(seed);
            _rng = new Rng(seed);
            _log = new EventLog(_cfg.RecordEvents);

            _p = new Player(spec, _cfg.Gcd);
            _boss = new Boss(boss, _rng);
            _agent = new BTAgent(spec);
            _distance = _cfg.StartDistance;
            if (boss.HasArena)
            {
                _arena = new Arena(boss, _rng, _log, _cfg.StartDistance);
                _distance = _arena.Distance;
                _arena.OnHit = (kind, raw) =>
                {
                    double since = _p.SinceHit;
                    double taken = _p.ReceiveDamage(raw, false);
                    if (kind == "pool") _p.SinceHit = since;   // 독 장판 지속 피해는 비전투 회복 타이머를 끊지 않는다 (틱마다 끊으면 원거리 회복이 사라짐)
                    _damageTaken += taken;
                    return taken;
                };
            }
            _obs.SkillAvailable = new bool[spec.Skills.Count];
            _obs.CooldownLeft = new double[spec.Skills.Count];
            _obs.BossReach = boss.Reach;
            _skillUses = new int[spec.Skills.Count];
            _bursts = spec.SkillsByRole(SkillRole.Burst).ToArray();

            _pendingTriggers = new List<double>(triggers ?? new double[0]);
            _pendingTriggers.Sort((a, b) => b.CompareTo(a));
            _useTriggers = _pendingTriggers.Count > 0 && onTrigger != null;
        }

        /// <summary>시작 물약 수 덮어쓰기 (플레이 모드: 인벤토리에서 가져간 수, v0.3). Begin 전에만. 밸런스 run_episode 는 부르지 않는다 (= 직업 potions).</summary>
        public void SetStartPotions(int n)
        {
            if (_begun) throw new InvalidOperationException("SetStartPotions 는 판 시작 전에만");
            _p.Potions = Math.Max(0, n);
        }

        // ------------------------------------------------------------------ 관측
        Observation Observe()
        {
            var p = _p;
            var o = _obs;
            o.Time = _t;
            o.HpRatio = p.HpRatio;
            o.Resource = p.Resource;
            o.ResourceRatio = p.ResourceRatio;
            o.MaxResource = p.MaxResource;
            o.Distance = _distance;
            o.BossHpRatio = _boss.HpRatio;
            o.GcdReady = p.GcdReady;
            foreach (var s in _spec.Skills) { o.SkillAvailable[s.Index] = p.Available(s); o.CooldownLeft[s.Index] = p.Cooldowns[s.Index]; }
            o.BuffActive = p.DamageBuffTime > Eps && p.DamageBuff > 0;
            o.TargetMarked = _boss.VulnTime > Eps;
            o.PotionsLeft = p.Potions;
            o.PotionReady = p.PotionReady;
            o.GimmickWarning = _boss.GimmickWarning;
            o.Danger = _arena != null ? _arena.Danger : 0.0;
            return o;
        }

        /// <summary>결정 트리거 상태 (P.TriggerStateFeatures 순서, 0~1 정규화).</summary>
        public JObject TriggerState()
        {
            bool burstReady = false;
            foreach (var s in _bursts) if (_p.Available(s)) { burstReady = true; break; }
            return new JObject
            {
                ["hp_ratio"] = R6(_p.HpRatio),
                ["boss_hp_ratio"] = R6(_boss.HpRatio),
                ["potions_ratio"] = R6((double)_p.Potions / Math.Max(1, _spec.Stats.Potions)),
                ["resource_ratio"] = R6(_p.ResourceRatio),
                ["burst_ready"] = burstReady ? 1.0 : 0.0,
                ["time_ratio"] = R6(Math.Min(1.0, _t / _cfg.TimeLimit)),
                ["deaths_ratio"] = R6(Math.Min(1.0, (double)_deaths / Math.Max(1, _cfg.MaxDeaths))),
            };
        }

        /// <summary>판 시작부터의 누적값 (v1.1). episode_result 의 같은 이름 필드와 단위가 같다.</summary>
        public JObject TriggerTotals()
        {
            return new JObject
            {
                ["elapsed"] = Math.Round(_t, 3),
                ["deaths"] = _deaths,
                ["consumables_used"] = _consumables,
                ["boss_hp_remaining"] = R6(_boss.HpRatio),
            };
        }

        static double R6(double x) => Math.Round(Math.Min(1.0, Math.Max(0.0, x)), 6);

        void FireTrigger()
        {
            var updates = _onTrigger(_triggersFired, TriggerState(), TriggerTotals());
            _params = _spec.ResolveParams(_params, updates);
            _agent.SetParams(_params);
            if (_log.Enabled) _log.Record(_t, "trigger", new JObject { ["index"] = _triggersFired });
            _triggersFired++;
        }

        // ------------------------------------------------------------------ 행동 적용
        void Apply(BtAction action)
        {
            var p = _p;
            bool wasEvading = _evading;
            _evading = action.Kind == ActionKind.Evade;
            switch (action.Kind)
            {
                case ActionKind.Skill:
                {
                    var skill = action.Skill;
                    bool inRange = skill.IsSelfTarget || _distance <= skill.Range + Eps;
                    if (!p.CanUse(skill) || !inRange) { _invalidActions++; return; }
                    p.StartSkill(skill);
                    if (skill.GapClose) _distance = Math.Max(_cfg.MinDistance, _bossSpec.Reach - 1.5);
                    if (skill.Retreat > 0) _distance = Math.Min(_cfg.MaxDistance, _distance + skill.Retreat);
                    if (skill.Dash > 0)
                    {
                        if (_arena != null) _distance = _arena.Dash(skill.Dash);
                        else _distance = Math.Min(_cfg.MaxDistance, _distance + skill.Dash);
                    }
                    if (skill.BossStun > 0) _boss.StunLeft = Math.Max(_boss.StunLeft, skill.BossStun);
                    if (skill.TargetVuln > 0) { _boss.Vuln = skill.TargetVuln; _boss.VulnTime = skill.VulnDuration; }
                    _skillUses[skill.Index]++;
                    if (_log.Enabled)
                    {
                        _log.Record(_t, "skill", new JObject
                        {
                            ["name"] = skill.Name, ["block"] = _agent.CurrentBlock, ["role"] = skill.Role.ToString().ToLowerInvariant(),
                            ["cooldown_ready_at"] = Math.Round(_t + skill.Cooldown, 2),
                        });
                        if (skill.Role == SkillRole.Burst && _lastSetup != null && _t - _lastSetupT <= 10.0)
                            _log.Record(_t, "combo", new JObject { ["setup"] = _lastSetup, ["burst"] = skill.Name });
                        if (skill.Role == SkillRole.Mobility) _log.Record(_t, "dodge", new JObject { ["skill"] = skill.Name, ["danger"] = Math.Round(_obs.Danger, 3) });
                    }
                    if (skill.IsComboSetup) { _lastSetup = skill.Name; _lastSetupT = _t; }
                    if (skill.CastTime <= 0) Resolve(skill);
                    break;
                }
                case ActionKind.MoveToward:
                    _distance = Math.Max(_cfg.MinDistance, _distance - p.Spec.Stats.MoveSpeed * _cfg.Dt);
                    break;
                case ActionKind.MoveAway:
                    _distance = Math.Min(_cfg.MaxDistance, _distance + p.Spec.Stats.MoveSpeed * _cfg.Dt);
                    break;
                case ActionKind.Potion:
                {
                    if (!p.PotionReady) { _invalidActions++; return; }
                    double healed = p.DrinkPotion();
                    _consumables++;
                    if (_log.Enabled) _log.Record(_t, "potion", new JObject { ["healed"] = Math.Round(healed, 1) });
                    break;
                }
                case ActionKind.Evade:
                {
                    if (_arena == null) { _invalidActions++; return; }
                    double fx = _arena.Px, fz = _arena.Pz;
                    _distance = _arena.MoveToSafe(p.Spec.Stats.MoveSpeed, _cfg.Dt);
                    if (_log.Enabled && !wasEvading)
                        _log.Record(_t, "dodge", new JObject
                        {
                            ["from"] = new JArray(Math.Round(fx, 2), Math.Round(fz, 2)),
                            ["to"] = new JArray(Math.Round(_arena.SafeX, 2), Math.Round(_arena.SafeZ, 2)),
                            ["danger"] = Math.Round(_arena.Danger, 3),
                        });
                    break;
                }
                case ActionKind.RespondGimmick:
                    if (_boss.ResolveGimmick())
                    {
                        _gimmickSuccess++;
                        p.Gcd = Math.Max(p.Gcd, _cfg.Gcd);
                        if (_log.Enabled) _log.Record(_t, "gimmick_ok");
                    }
                    break;
            }
        }

        /// <summary>시전 완료 시 피해 적용.</summary>
        void Resolve(SkillDef skill)
        {
            if (skill.Damage > 0 && (skill.IsSelfTarget || _distance <= skill.Range + 0.5))
            {
                double dmg = skill.Damage * _p.DamageMult * _boss.DamageTakenMult;
                bool crit = _rng.NextDouble() < _spec.Stats.CritChance;
                if (crit) dmg *= _cfg.CritMult;
                if (_log.Enabled) _log.Record(_t, "dmg", new JObject { ["skill"] = skill.Name, ["dmg"] = Math.Round(dmg, 1), ["crit"] = crit });
                _damageDealt += dmg;
                _lastDamageT = _t;
                _boss.TakeDamage(dmg, _crossed);
                if (skill.ResourceGain != 0) _p.GainResource(skill.ResourceGain);
                if (_crossed.Count > 0) OnPhaseCross();
            }
        }

        void OnPhaseCross()
        {
            foreach (var thr in _crossed)
            {
                _phaseTimes.Add(_t + _cfg.Dt);
                if (_log.Enabled) _log.Record(_t, "phase", new JObject { ["threshold"] = thr });
            }
            // 결정 트리거: 같은 스텝에 경계 여러 개를 넘어도 마지막 상태로 한 번
            bool fired = false;
            while (_pendingTriggers.Count > 0 && _boss.HpRatio <= _pendingTriggers[0] + Eps)
            {
                _pendingTriggers.RemoveAt(0);
                fired = true;
            }
            if (fired && _boss.Alive && _useTriggers) FireTrigger();
        }

        // ------------------------------------------------------------------ 메인 루프
        // Run() = Begin() + Step() 반복 + Result(). 화면 표시(뷰어)는 Begin/Step 을 직접 호출해 한 틱씩 진행한다.
        bool _begun, _done, _cleared;
        double? _clearTime;
        string _stallReason;
        JObject _result;

        /// <summary>판 시작: 파라미터 적용 + (트리거 요청 시) index 0 트리거.</summary>
        public void Begin()
        {
            if (_begun) return;
            _begun = true;
            _agent.SetParams(_params);
            if (_useTriggers) FireTrigger();   // index 0: 판 시작 결정
            _done = !(_t < _cfg.TimeLimit - Eps);
        }

        /// <summary>고정 dt 1틱. 판이 끝나면 Done = true.</summary>
        public void Step()
        {
            if (!_begun) Begin();
            if (_done) return;
            var cfg = _cfg;
            var p = _p;

            p.Tick(cfg.Dt);

            // --- 플레이어 ---
            if (p.Dead)
            {
                _blockTime.Add("dead", cfg.Dt);
                p.ReviveTimer -= cfg.Dt;
                if (p.ReviveTimer <= Eps)
                {
                    p.Revive(cfg.ReviveHpRatio);
                    _distance = cfg.ReviveDistance;
                    if (_log.Enabled) _log.Record(_t, "revive");
                }
            }
            else
            {
                if (p.Casting != null && _arena != null && _arena.Danger > Eps && _params.Get("w_evade", 0.0) > 0 &&
                    _arena.Danger >= _params.Get("evade_cancel_danger", 2.0))
                {
                    // 시전 중 위험 → 시전을 끊고 이번 틱에 피한다 (0.8.1)
                    if (_log.Enabled) _log.Record(_t, "cast_cancel", new JObject { ["skill"] = p.Casting.Name, ["reason"] = "danger", ["danger"] = Math.Round(_arena.Danger, 3) });
                    _castCancels++;
                    p.Interrupt();
                }
                if (p.Casting != null)
                {
                    p.CastRemaining -= cfg.Dt;
                    if (p.CastRemaining <= Eps)
                    {
                        var skill = p.Casting;
                        p.Interrupt();
                        Resolve(skill);
                    }
                }
                else
                {
                    Apply(_agent.Decide(Observe()));
                }
                _blockTime.Add(_agent.CurrentBlock, cfg.Dt);
            }
            if (_arena != null) _distance = _arena.PlayerMoved(_distance);
            DistanceAfterPlayer = _distance;

            if (!_boss.Alive)
            {
                _cleared = true;
                _clearTime = _t + cfg.Dt;
                _t += cfg.Dt;
                _done = true;
                return;
            }

            // --- 보스 ---
            _distance = _boss.Update(cfg.Dt, _distance, !p.Dead, p.HpRatio, _t, _attacks);
            if (_arena != null) _distance = _arena.BossMoved(_distance);
            if (_log.Enabled && _boss.StartedMove != null) _log.Record(_t, "boss", new JObject { ["move"] = _boss.StartedMove });
            foreach (var atk in _attacks)
            {
                double raw = atk.RawDamage + atk.HpRatioDamage * p.MaxHp;
                double taken = p.ReceiveDamage(raw, atk.IgnoreMitigation);
                _damageTaken += taken;
                if (atk.Kind == BossAttackKind.Gimmick) _gimmickFail++;
                if (_log.Enabled) _log.Record(_t, "hit", new JObject { ["kind"] = atk.KindName, ["dmg"] = Math.Round(taken, 1) });
            }
            if (_arena != null) _distance = _arena.Tick(cfg.Dt, _t, _boss.Phase, _boss.DamageMultNow, !p.Dead, p.Hp);

            // --- 사망 ---
            if (!p.Dead && p.Hp <= Eps)
            {
                _deaths++;
                if (_log.Enabled) _log.Record(_t, "death", new JObject { ["count"] = _deaths });
                if (_deaths > cfg.MaxDeaths)
                {
                    _t += cfg.Dt;
                    _done = true;
                    return;
                }
                p.Die(cfg.ReviveDelay);
            }

            _t += cfg.Dt;

            // --- 무효 판 감지 ---
            if (!p.Dead && _t - _lastDamageT > cfg.StallSeconds)
            {
                // 멈춘 판 = BT 가 진전 없이 맴돈 실패 (v1.2 stalled). 환경 오류가 아니므로 invalid 아님.
                _stallReason = cfg.StallSeconds.ToString("0", System.Globalization.CultureInfo.InvariantCulture) + "s 동안 보스 피해 없음";
                _done = true;
                return;
            }
            if (!(_t < cfg.TimeLimit - Eps)) _done = true;
        }

        /// <summary>판 끝까지 실행하고 episode_result.result 를 돌려준다.</summary>
        public JObject Run()
        {
            Begin();
            while (!_done) Step();
            return Result();
        }

        /// <summary>끝난 판의 결과 (Done 이후). 한 번 만들면 캐시.</summary>
        public JObject Result()
        {
            if (_result == null) _result = Result(_cleared, _clearTime, _stallReason);
            return _result;
        }

        // ------------------------------------------------------------------ 읽기 전용 상태 (화면 표시용)
        public bool Done => _done;
        public bool Cleared => _cleared;
        public double Time => _t;
        public double Distance => _distance;
        /// <summary>이번 틱에 플레이어 행동만 반영된 거리 (보스 이동 전). 화면에서 누가 움직였는지 나눌 때 쓴다.</summary>
        public double DistanceAfterPlayer { get; private set; }
        public Player PlayerState => _p;
        public Boss BossState => _boss;
        /// <summary>2D 아레나 (없으면 null = 1차원 거리 전투).</summary>
        public Arena ArenaState => _arena;
        public ClassSpec ClassSpec => _spec;
        public SimConfig Config => _cfg;
        public string CurrentBlock => _agent.CurrentBlock;
        public int Deaths => _deaths;
        public int ConsumablesUsed => _consumables;
        public int TriggersFired => _triggersFired;
        public bool Stalled => _stallReason != null;
        public string StallReason => _stallReason;
        /// <summary>RecordEvents 일 때 [t, kind, payload] 이벤트 (계속 늘어남).</summary>
        public JArray Events => _log.Events;

        JObject Result(bool cleared, double? clearTime, string stallReason)
        {
            var marks = new List<double> { 0.0 };
            marks.AddRange(_phaseTimes);
            if (clearTime.HasValue) marks.Add(clearTime.Value);
            var segments = new JArray();
            for (int i = 1; i < marks.Count; i++) segments.Add(Math.Round(marks[i] - marks[i - 1], 3));

            var r = new JObject
            {
                ["seed"] = _seedToken.DeepClone(),
                ["cleared"] = cleared,
                ["elapsed"] = Math.Round(_t, 3),
                ["clear_time"] = clearTime.HasValue ? new JValue(Math.Round(clearTime.Value, 3)) : JValue.CreateNull(),
                ["boss_hp_remaining"] = _boss.HpRatio,
                ["deaths"] = _deaths,
                ["consumables_used"] = _consumables,
                ["damage_dealt"] = Math.Round(_damageDealt, 1),
                ["damage_taken"] = Math.Round(_damageTaken, 1),
                ["segment_times"] = segments,
                ["block_time"] = _blockTime.ToJson(3),
                ["gimmick_success"] = _gimmickSuccess,
                ["gimmick_fail"] = _gimmickFail,
                ["triggers_fired"] = _triggersFired,
                ["invalid_actions"] = _invalidActions,
                ["stalled"] = stallReason != null,
                ["stall_reason"] = stallReason == null ? JValue.CreateNull() : new JValue(stallReason),
                ["invalid"] = false,                 // 게임이 결과를 믿을 수 없는 경우에만 true (현재 없음 — 내부 예외는 error(internal))
                ["invalid_reason"] = JValue.CreateNull(),
            };
            if (_cfg.RecordEvents) r["events"] = _log.Events;
            return r;
        }
    }
}
