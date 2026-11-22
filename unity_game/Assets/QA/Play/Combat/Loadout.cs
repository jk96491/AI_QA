// set_loadout (PLAY_PROTOCOL 4.3): 전투에서 BT 가 쓸 학습 결과 파라미터. 키 = (class, scenario).
// 검증은 밸런스 run_episode.params 와 같다 (ClassSpec.ResolveParams → unknown_param / param_out_of_range).
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.Data;
using Qa.Play.Server;
using Qa.Protocol;

namespace Qa.Play.Combat
{
    public sealed class LoadoutEntry
    {
        public string Class, Scenario, Boss, Source;
        public JObject Params;               // 요청 그대로 (CombatSim 이 default 위에 덮어쓴다 — run_episode 와 같은 경로)
        public List<double> Triggers;        // boss_hp_below (비어 있으면 트리거 없음)
        public JToken TriggersRaw;
    }

    public sealed class Loadout
    {
        public string Persona;
        public string Fallback = "default";
        public readonly List<LoadoutEntry> Entries = new List<LoadoutEntry>();

        public LoadoutEntry Find(string cls, string scenario)
        {
            foreach (var e in Entries) if (e.Class == cls && e.Scenario == scenario) return e;
            return null;
        }

        public static Loadout Parse(JObject msg, SpecRepository repo)
        {
            var lo = new Loadout { Persona = msg["persona"]?.Type == JTokenType.String ? (string)msg["persona"] : null };
            var fb = msg["fallback"];
            if (fb != null && fb.Type != JTokenType.Null)
            {
                lo.Fallback = fb.Type == JTokenType.String ? (string)fb : null;
                if (lo.Fallback != "default" && lo.Fallback != "error")
                    throw new ProtocolException(P.EBadRequest, "fallback 은 \"default\" 또는 \"error\"");
            }
            if (!(msg["entries"] is JArray arr)) throw new ProtocolException(P.EBadRequest, "set_loadout.entries 는 배열이어야 함");
            var seen = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < arr.Count; i++)
            {
                if (!(arr[i] is JObject e)) throw new ProtocolException(P.EBadRequest, "entries[" + i + "] 는 객체여야 함");
                string Str(string k) => e[k]?.Type == JTokenType.String ? (string)e[k] : null;
                var cls = Str("class");
                if (!repo.HasClass(cls)) throw new ProtocolException(P.EUnknownClass, "entries[" + i + "]: 알 수 없는 class " + e["class"]);
                var scen = Str("scenario") ?? "base";
                if (!repo.HasScenario(scen)) throw new ProtocolException(P.EUnknownScenario, "entries[" + i + "]: 알 수 없는 scenario " + e["scenario"]);
                var bossName = repo.BossFor(scen).Name;
                var boss = Str("boss");
                if (e["boss"] != null && e["boss"].Type != JTokenType.Null && boss != bossName)
                    throw new ProtocolException(PP.EUnknownBoss, "entries[" + i + "]: boss " + e["boss"] + " 는 시나리오 " + scen + " 의 보스(" + bossName + ")가 아님");
                var ps = e["params"];
                if (ps != null && ps.Type != JTokenType.Null && ps.Type != JTokenType.Object)
                    throw new ProtocolException(P.EBadRequest, "entries[" + i + "].params 는 객체여야 함");
                var spec = repo.Class(cls);
                try { spec.ResolveParams(spec.DefaultParams(), ps as JObject); }
                catch (ParamException ex) { throw new ProtocolException(ex.Code, "entries[" + i + "]: " + ex.Message); }
                var triggers = CombatEpisodeRunner.ParseTriggers(e["triggers"]);
                if (!seen.Add(cls + "\n" + scen)) throw new ProtocolException(P.EBadRequest, "entries[" + i + "]: (" + cls + ", " + scen + ") 중복");
                lo.Entries.Add(new LoadoutEntry
                {
                    Class = cls, Scenario = scen, Boss = bossName, Source = Str("source"),
                    Params = ps is JObject po ? (JObject)po.DeepClone() : null,
                    Triggers = triggers, TriggersRaw = e["triggers"]?.DeepClone(),
                });
            }
            return lo;
        }
    }
}
