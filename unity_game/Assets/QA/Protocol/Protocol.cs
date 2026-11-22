// 프로토콜 상수·오류·JSON Lines 인코딩 (game_sim/server/protocol.py 대응). 명세: ../docs/PROTOCOL.md v1.1
using System;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Qa.Protocol
{
    public static class P
    {
        public const string ProtocolVersion = "1.2";  // 1.1: trigger.totals, 1.2: result.stalled

        // 학습 → 게임
        public const string Hello = "hello";
        public const string Describe = "describe";
        public const string RunEpisode = "run_episode";
        public const string TriggerResponse = "trigger_response";
        public const string Bye = "bye";

        // 게임 → 학습
        public const string HelloOk = "hello_ok";
        public const string Description = "description";
        public const string Trigger = "trigger";
        public const string EpisodeResult = "episode_result";
        public const string Error = "error";

        // 오류 코드
        public const string EBadRequest = "bad_request";
        public const string EUnknownType = "unknown_type";
        public const string EProtocolVersion = "protocol_version";
        public const string EUnknownClass = "unknown_class";
        public const string EUnknownScenario = "unknown_scenario";
        public const string EUnknownParam = "unknown_param";
        public const string EParamOutOfRange = "param_out_of_range";
        public const string EInternal = "internal";

        /// <summary>트리거 상태 키 (모두 0~1). describe 에 그대로 노출 = 학습 쪽 정책 입력 순서.</summary>
        public static readonly string[] TriggerStateFeatures =
        {
            "hp_ratio", "boss_hp_ratio", "potions_ratio", "resource_ratio", "burst_ready", "time_ratio", "deaths_ratio",
        };

        /// <summary>trigger.totals 키 (v1.1). 이름·단위는 episode_result 와 같다.</summary>
        public static readonly string[] TriggerTotalsFields = { "elapsed", "deaths", "consumables_used", "boss_hp_remaining" };

        public static readonly string[] ResultFields =
        {
            "seed", "cleared", "elapsed", "clear_time", "boss_hp_remaining", "deaths",
            "consumables_used", "damage_dealt", "damage_taken", "segment_times", "block_time",
            "gimmick_success", "gimmick_fail", "triggers_fired", "invalid_actions", "stalled", "stall_reason", "invalid", "invalid_reason",
        };

        public static JObject MakeError(string code, string message, JToken episodeId = null)
        {
            var m = new JObject { ["type"] = Error, ["code"] = code, ["message"] = message };
            if (episodeId != null && episodeId.Type != JTokenType.Null) m["episode_id"] = episodeId.DeepClone();
            return m;
        }
    }

    /// <summary>error 응답으로 바뀌는 예외. 연결은 유지된다.</summary>
    public sealed class ProtocolException : Exception
    {
        public readonly string Code;
        public ProtocolException(string code, string message) : base(message) { Code = code; }
    }

    /// <summary>JSON Lines 한 줄 ↔ JObject.</summary>
    public static class JsonLine
    {
        static readonly JsonSerializerSettings Settings = new JsonSerializerSettings
        {
            DateParseHandling = DateParseHandling.None,   // "2026-..." 문자열을 DateTime 으로 바꾸지 않음
            FloatParseHandling = FloatParseHandling.Double,
        };

        public static JObject Decode(string line)
        {
            JToken token;
            try
            {
                token = JsonConvert.DeserializeObject<JToken>(line, Settings);
            }
            catch (JsonException ex)
            {
                throw new ProtocolException(P.EBadRequest, "JSON 파싱 실패: " + ex.Message);
            }
            if (!(token is JObject obj) || obj["type"] == null)
                throw new ProtocolException(P.EBadRequest, "메시지는 'type' 을 가진 JSON 객체여야 함");
            return obj;
        }

        /// <summary>한 줄 JSON (개행 없음). 비 ASCII 는 그대로 UTF-8.</summary>
        public static string Encode(JObject msg) => msg.ToString(Formatting.None);
    }
}
