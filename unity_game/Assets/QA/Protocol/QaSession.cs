// 연결 1개에 대한 게임 세션 (game_sim/server/session.py 대응).
//   hello → hello_ok, describe → description,
//   run_episode → (trigger ↔ trigger_response)* → episode_result
using System;
using System.IO;
using Newtonsoft.Json.Linq;
using Qa.Data;
using Qa.Sim;

namespace Qa.Protocol
{
    /// <summary>세션이 쓰는 송수신 통로. Recv 는 연결이 끊기면 null.</summary>
    public interface IMessageChannel
    {
        void Send(JObject msg);
        JObject Recv();
    }

    /// <summary>run_episode 실행기. 2단계에서 전투 시뮬레이터로 구현.</summary>
    public interface IEpisodeRunner
    {
        JObject Run(JObject msg, ClassSpec spec, BossSpec boss, IMessageChannel channel);
    }

    public sealed class QaSession
    {
        readonly SpecRepository _repo;
        readonly SimConfig _cfg;
        readonly IEpisodeRunner _runner;

        public QaSession(SpecRepository repo, SimConfig cfg, IEpisodeRunner runner)
        {
            _repo = repo;
            _cfg = cfg;
            _runner = runner;
        }

        // ------------------------------------------------------------------ describe
        public JObject Description()
        {
            var classes = new JArray();
            foreach (var n in _repo.ClassNames) classes.Add(_repo.Class(n).ToWire());
            var scenarios = new JArray();
            foreach (var s in _repo.Scenarios)
                scenarios.Add(new JObject { ["name"] = s.Name, ["description"] = s.Description });
            var baseBoss = _repo.BossFor("base");
            return new JObject
            {
                ["type"] = P.Description,
                ["protocol_version"] = P.ProtocolVersion,
                ["game"] = _repo.GameName,
                ["game_version"] = _repo.GameVersion,
                ["time_limit"] = _cfg.TimeLimit,
                ["max_deaths"] = _cfg.MaxDeaths,
                ["decision_interval"] = _cfg.Dt,
                ["classes"] = classes,
                ["scenarios"] = scenarios,
                ["triggers"] = new JObject
                {
                    ["type"] = "boss_hp_below",
                    ["supported"] = new JArray(baseBoss.PhaseThresholds),
                    ["state_features"] = new JArray(P.TriggerStateFeatures),
                    ["totals"] = new JArray(P.TriggerTotalsFields),
                },
                ["result_fields"] = new JArray(P.ResultFields),
            };
        }

        // ------------------------------------------------------------------ run_episode
        JObject RunEpisode(JObject msg, IMessageChannel ch)
        {
            foreach (var key in new[] { "episode_id", "class", "seed" })
                if (msg[key] == null) throw new ProtocolException(P.EBadRequest, "run_episode 에 '" + key + "' 필요");
            var cls = msg["class"].Type == JTokenType.String ? (string)msg["class"] : null;
            if (!_repo.HasClass(cls)) throw new ProtocolException(P.EUnknownClass, "알 수 없는 class " + msg["class"]);
            var scTok = msg["scenario"];
            var scenario = scTok == null || scTok.Type == JTokenType.Null ? "base" : scTok.Type == JTokenType.String ? (string)scTok : null;
            if (scenario == "") scenario = "base";
            if (!_repo.HasScenario(scenario)) throw new ProtocolException(P.EUnknownScenario, "알 수 없는 scenario " + scTok);
            var ps = msg["params"];
            if (ps != null && ps.Type != JTokenType.Null && ps.Type != JTokenType.Object)
                throw new ProtocolException(P.EBadRequest, "params 는 객체여야 함");
            var seed = msg["seed"];
            if (seed.Type != JTokenType.Integer) throw new ProtocolException(P.EBadRequest, "seed 는 정수여야 함");
            if (_runner == null) throw new ProtocolException(P.EInternal, "run_episode 아직 구현 전");
            try
            {
                return _runner.Run(msg, _repo.Class(cls), _repo.BossFor(scenario), ch);
            }
            catch (ParamException ex)
            {
                throw new ProtocolException(ex.Code, ex.Message);
            }
        }

        // ------------------------------------------------------------------ 디스패치
        /// <summary>메시지 1개 처리. 연결을 닫아야 하면 false.</summary>
        public bool Handle(JObject msg, IMessageChannel ch)
        {
            var kind = msg["type"]?.Type == JTokenType.String ? (string)msg["type"] : null;
            try
            {
                switch (kind)
                {
                    case P.Hello:
                    {
                        var v = msg["protocol_version"]?.ToString() ?? "";
                        if (v.Split('.')[0] != P.ProtocolVersion.Split('.')[0])
                            throw new ProtocolException(P.EProtocolVersion, "지원 버전 " + P.ProtocolVersion + ", 요청 '" + v + "'");
                        ch.Send(new JObject
                        {
                            ["type"] = P.HelloOk,
                            ["protocol_version"] = P.ProtocolVersion,
                            ["game"] = _repo.GameName,
                            ["game_version"] = _repo.GameVersion,
                        });
                        break;
                    }
                    case P.Describe:
                        ch.Send(Description());
                        break;
                    case P.RunEpisode:
                        ch.Send(RunEpisode(msg, ch));
                        break;
                    case P.Bye:
                        return false;
                    default:
                        throw new ProtocolException(P.EUnknownType, "알 수 없는 type '" + msg["type"] + "'");
                }
            }
            catch (ProtocolException ex)
            {
                ch.Send(P.MakeError(ex.Code, ex.Message, msg["episode_id"]));
            }
            catch (IOException)
            {
                return false;   // 연결 끊김 (트리거 응답 대기 중 등)
            }
            catch (Exception ex)  // 게임 내부 오류도 연결은 유지
            {
                ch.Send(P.MakeError(P.EInternal, ex.GetType().Name + ": " + ex.Message, msg["episode_id"]));
            }
            return true;
        }
    }
}
