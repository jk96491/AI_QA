// run_episode 실행기: 요청 → CombatSim → episode_result. 트리거 왕복도 여기서 처리한다.
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using Qa.Data;
using Qa.Sim;

namespace Qa.Protocol
{
    public sealed class CombatEpisodeRunner : IEpisodeRunner
    {
        readonly SimConfig _cfg;
        readonly EpisodeRecorder _recorder;   // null = 기록 안 함 (헤드리스)

        public CombatEpisodeRunner(SimConfig cfg, EpisodeRecorder recorder = null)
        {
            _cfg = cfg;
            _recorder = recorder;
        }

        public JObject Run(JObject msg, ClassSpec spec, BossSpec boss, IMessageChannel ch)
        {
            var episodeId = msg["episode_id"];
            var seedTok = msg["seed"];
            long seed;
            try { seed = seedTok.Value<long>(); }
            catch (System.Exception) { throw new ProtocolException(P.EBadRequest, "seed 는 64비트 정수여야 함"); }

            var triggers = ParseTriggers(msg["triggers"]);
            bool record = msg["record_events"]?.Type == JTokenType.Boolean && (bool)msg["record_events"];
            var cfg = record ? _cfg.WithRecordEvents(true) : _cfg;
            var rec = _recorder == null ? null : new EpisodeRecord { Request = (JObject)msg.DeepClone() };

            TriggerHandler onTrigger = (index, state, totals) =>
            {
                ch.Send(new JObject
                {
                    ["type"] = P.Trigger,
                    ["episode_id"] = episodeId.DeepClone(),
                    ["index"] = index,
                    ["state"] = state,
                    ["totals"] = totals,
                });
                var reply = ch.Recv();   // 응답이 올 때까지 판(게임 시간) 정지
                if (reply == null) throw new IOException("trigger 응답 대기 중 연결 종료");
                var po = CheckTriggerResponse(reply, "episode_id", episodeId, index);
                rec?.TriggerParams.Add(po == null ? null : (JObject)po.DeepClone());
                return po;
            };

            var sim = new CombatSim(spec, boss, msg["params"] as JObject, seed, seedTok, cfg, triggers, onTrigger);
            var result = sim.Run();
            if (rec != null)
            {
                rec.Result = (JObject)result.DeepClone();
                _recorder.Commit(rec);
            }
            return new JObject
            {
                ["type"] = P.EpisodeResult,
                ["episode_id"] = episodeId.DeepClone(),
                ["result"] = result,
            };
        }

        /// <summary>
        /// trigger_response 검증 → 덮어쓸 params (null 가능). 밸런스(episode_id)·플레이(encounter_id) 모드가 같이 쓴다.
        /// 형식이 틀리면 ProtocolException(bad_request).
        /// </summary>
        public static JObject CheckTriggerResponse(JObject reply, string idKey, JToken idValue, int index)
        {
            var type = reply["type"]?.Type == JTokenType.String ? (string)reply["type"] : null;
            if (type != P.TriggerResponse || !JToken.DeepEquals(reply[idKey], idValue))
                throw new ProtocolException(P.EBadRequest,
                    "trigger_response(" + idKey + "=" + idValue + ") 를 기대했으나 type=" + reply["type"] + " " + idKey + "=" + reply[idKey]);
            var idx = reply["index"];
            if (idx == null || (idx.Type != JTokenType.Integer && idx.Type != JTokenType.Float) || idx.Value<double>() != index)
                throw new ProtocolException(P.EBadRequest, "trigger_response index " + idx + " != " + index);
            var ps = reply["params"];
            if (ps == null || ps.Type == JTokenType.Null) return null;
            if (!(ps is JObject po)) throw new ProtocolException(P.EBadRequest, "trigger_response.params 는 객체여야 함");
            return po;
        }

        /// <summary>triggers.boss_hp_below 파싱 (밸런스 run_episode · 플레이 set_loadout 공용).</summary>
        public static List<double> ParseTriggers(JToken t)
        {
            var outp = new List<double>();
            if (t == null || t.Type == JTokenType.Null) return outp;
            if (!(t is JObject o)) throw new ProtocolException(P.EBadRequest, "triggers 는 객체여야 함");
            var b = o["boss_hp_below"];
            if (b == null || b.Type == JTokenType.Null) return outp;
            if (!(b is JArray arr)) throw new ProtocolException(P.EBadRequest, "triggers.boss_hp_below 는 숫자 배열이어야 함");
            foreach (var x in arr)
            {
                if (x.Type != JTokenType.Float && x.Type != JTokenType.Integer)
                    throw new ProtocolException(P.EBadRequest, "triggers.boss_hp_below 항목은 숫자");
                outp.Add(x.Value<double>());
            }
            return outp;
        }
    }
}
