// 플레이 모드(set_loadout·전투 트리거)가 쓰는 트리거 도우미. 밸런스 모드 판 실행은 QaArenaHost (BT-QA Game SDK).
using System.Collections.Generic;
using Btqa.Game;
using Newtonsoft.Json.Linq;

namespace Qa.Protocol
{
    public static class CombatEpisodeRunner
    {
        /// <summary>trigger_response 검증 → 덮어쓸 params (null 가능). = Btqa.Game.TriggerChannel.CheckResponse</summary>
        public static JObject CheckTriggerResponse(JObject reply, string idKey, JToken idValue, int index)
            => TriggerChannel.CheckResponse(reply, idKey, idValue, index);

        /// <summary>triggers.boss_hp_below 파싱 (플레이 set_loadout).</summary>
        public static List<double> ParseTriggers(JToken t) => TriggerChannel.ParseThresholds(t, P.TriggerType);
    }
}
