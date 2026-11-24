// QaArena 의 IEpisodeHost (BT-QA Game SDK 구현체, game_sim/server/session.py 의 GameSimHost 대응).
// SDK(Btqa.Game.QaSession) 가 메시지 처리·요청 검증·트리거 왕복 검사를 하고, 여기는 이 게임 고유의 두 가지만:
//   Declare()    : 정의서 — 직업 파라미터 + BT 전략 블록 가중치 (BTAgent.StrategyBlocks)
//   RunEpisode() : CombatSim 으로 판 1개
using Btqa.Game;
using Newtonsoft.Json.Linq;
using Qa.BT;
using Qa.Data;
using Qa.Sim;

namespace Qa.Protocol
{
    public sealed class QaArenaHost : IEpisodeHost
    {
        readonly SpecRepository _repo;
        readonly SimConfig _cfg;
        readonly EpisodeRecorder _recorder;   // null = 기록 안 함 (헤드리스)
        GameDecl _decl;

        public QaArenaHost(SpecRepository repo, SimConfig cfg, EpisodeRecorder recorder = null)
        {
            _repo = repo;
            _cfg = cfg;
            _recorder = recorder;
        }

        public GameDecl Declare()
        {
            if (_decl != null) return _decl;
            var d = new GameDecl
            {
                Game = _repo.GameName,
                GameVersion = _repo.GameVersion,
                TimeLimit = _cfg.TimeLimit,
                MaxDeaths = _cfg.MaxDeaths,
                DecisionInterval = _cfg.Dt,
            };
            foreach (var n in _repo.ClassNames) d.Classes.Add(ClassDeclOf(_repo.Class(n)));
            foreach (var s in _repo.Scenarios) d.Scenarios.Add(new ScenarioDecl(s.Name, s.Description));
            d.Triggers.Type = P.TriggerType;
            d.Triggers.Supported.AddRange(_repo.BossFor("base").PhaseThresholds);
            d.Triggers.StateFeatures.AddRange(P.TriggerStateFeatures);
            d.Triggers.Totals.AddRange(P.TriggerTotalsFields);
            d.ResultFields.AddRange(P.ResultFields);
            // 1.4: 판 시작 상태 (컨텍스트 밴딧). 이름은 triggers.state_features 안에서만. resource_ratio 는 직업마다 시작 자원이 달라 넣지 않는다.
            d.InitialState.Add(new InitialStateDecl("hp_ratio", 0.05, 1.0, 1.0, "판 시작 체력 / 최대 체력"));
            d.InitialState.Add(new InitialStateDecl("potions_ratio", 0.0, 1.0, 1.0, "판 시작 물약 = round(비율 × 직업 물약 수), 0.5 올림"));
            return _decl = d;
        }

        /// <summary>직업 정의서 → SDK 선언. 블록은 BT 코드(BTAgent.StrategyBlocks)에서 나온다 = 학습 대상 가중치.</summary>
        public static ClassDecl ClassDeclOf(ClassSpec spec)
        {
            var c = new ClassDecl { Name = spec.Name, DisplayName = spec.DisplayName, Ranged = spec.Ranged, SpecVersion = spec.SpecVersion };
            foreach (var p in spec.ParamList)
                c.Params.Add(new ParamDecl
                {
                    Name = p.Name, Low = p.Low, High = p.High, Default = p.Default,
                    Group = p.Group, Unit = p.Unit, Description = p.Description,
                    Optimize = p.ExplicitOptimize,
                });
            foreach (var b in BTAgent.StrategyBlocks) c.Blocks.Add(new BlockDecl(b.Name, b.Weight, b.Description));
            return c;
        }

        public JObject RunEpisode(EpisodeRequest req, TriggerChannel triggers)
        {
            var cfg = req.RecordEvents ? _cfg.WithRecordEvents(true) : _cfg;
            var rec = _recorder == null ? null : new EpisodeRecord { Request = (JObject)req.Raw.DeepClone() };

            TriggerHandler onTrigger = (index, state, totals) =>
            {
                var po = triggers.Fire(index, state, totals);
                rec?.TriggerParams.Add(po == null ? null : (JObject)po.DeepClone());
                return po;
            };

            JObject result;
            try
            {
                var sim = new CombatSim(_repo.Class(req.Class.Name), _repo.BossFor(req.Scenario), req.Params, req.Seed,
                                        req.SeedToken, cfg, req.Thresholds, onTrigger);
                if (req.InitialState != null)   // null = 요청 없음 -> 1.3 과 같은 판 (바이트 단위 동일)
                {
                    sim.SetStartHpRatio(req.InitialState["hp_ratio"]);
                    int cap = _repo.Class(req.Class.Name).Stats.Potions;
                    sim.SetStartPotions((int)System.Math.Floor(req.InitialState["potions_ratio"] * cap + 0.5));
                }
                result = sim.Run();
            }
            catch (ParamException ex)
            {
                throw new ProtocolException(ex.Code, ex.Message);
            }
            if (rec != null)
            {
                rec.Result = (JObject)result.DeepClone();
                _recorder.Commit(rec);
            }
            return result;
        }
    }
}
