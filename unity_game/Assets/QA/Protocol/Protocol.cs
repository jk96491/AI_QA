// 이 게임(QaArena) 고유의 프로토콜 값. 메시지 이름·오류 코드·인코딩·서버·세션은 BT-QA Game SDK
// (embedded 패키지 사본 Packages/com.btqa.game, 네임스페이스 Btqa.Game — 원본은 별도 SDK 레포) 를 쓴다. 명세: ../docs/PROTOCOL.md v1.3
// P.* 상수는 기존 코드 호환용 별칭 (= Btqa.Game.Wire.*).
using Btqa.Game;
using Newtonsoft.Json.Linq;

namespace Qa.Protocol
{
    public static class P
    {
        public const string ProtocolVersion = Wire.ProtocolVersion;

        public const string Hello = Wire.Hello;
        public const string Describe = Wire.Describe;
        public const string RunEpisode = Wire.RunEpisode;
        public const string TriggerResponse = Wire.TriggerResponse;
        public const string Bye = Wire.Bye;

        public const string HelloOk = Wire.HelloOk;
        public const string Description = Wire.Description;
        public const string Trigger = Wire.Trigger;
        public const string EpisodeResult = Wire.EpisodeResult;
        public const string Error = Wire.Error;

        public const string EBadRequest = Wire.EBadRequest;
        public const string EUnknownType = Wire.EUnknownType;
        public const string EProtocolVersion = Wire.EProtocolVersion;
        public const string EUnknownClass = Wire.EUnknownClass;
        public const string EUnknownScenario = Wire.EUnknownScenario;
        public const string EUnknownParam = Wire.EUnknownParam;
        public const string EParamOutOfRange = Wire.EParamOutOfRange;
        public const string EInternal = Wire.EInternal;

        /// <summary>트리거 종류 = run_episode.triggers 의 키 (describe.triggers.type).</summary>
        public const string TriggerType = "boss_hp_below";

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

        public static JObject MakeError(string code, string message, JToken episodeId = null) => Wire.MakeError(code, message, episodeId);
    }
}
