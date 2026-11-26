// 플레이 모드 데이터 (Resources/QaData/play/*.json). 순수 C# — UnityEngine 비의존.
// 밸런스 모드(-qaPlay 없음)에서는 읽지 않는다.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace Qa.Play.World
{
    public sealed class EntityDef
    {
        public string Id, Role, Label, Dialogue;
        public double X, Z, Radius = 0.5, Height = 1.8;
        public string[] Actions = new string[0];
        public string[] Tags = new string[0];
        public bool AlwaysKnown;
        public string Item;     // pickup 으로 얻는 아이템
        public string ToZone;   // enter 로 가는 지역
        // 적 (role enemy): 조우 = 밸런스 시나리오 하나 (PLAY_PROTOCOL 4.2 scenarios, 로드아웃 키 (class, scenario))
        public string Scenario;
        public double AggroRadius;
        public double Jitter;       // (0.8.5) reset.seed 가 대기 위치를 ±Jitter m 흔든다 (0 = 고정)
        public string Checkpoint;   // 패배 시 부활 위치 엔티티 id
        public int Xp;
        public readonly List<KeyValuePair<string, int>> Loot = new List<KeyValuePair<string, int>>();
    }

    public sealed class ObstacleDef
    {
        public string Id;
        public double X, Z, SizeX, SizeZ, Height = 2.0;
    }

    public sealed class ZoneDef
    {
        public string Id, Label;
        public double MinX, MaxX, MinZ, MaxZ;
        public double SpawnX, SpawnZ;
        public readonly List<EntityDef> Entities = new List<EntityDef>();
        public readonly List<ObstacleDef> Obstacles = new List<ObstacleDef>();
    }

    /// <summary>대화 선택지 효과: accept_quest / complete_quest / open_shop / set_flag.</summary>
    public sealed class DialogueEffect
    {
        public string Kind, Arg;
    }

    public sealed class DialogueChoice
    {
        public string Text, Next;   // Next null = 대화 종료
        public readonly List<DialogueEffect> Effects = new List<DialogueEffect>();
    }

    public sealed class DialogueNode
    {
        public string Id, Speaker, Text;
        public readonly List<DialogueChoice> Choices = new List<DialogueChoice>();
    }

    public sealed class DialogueStart
    {
        public string If;     // null = 항상. "quest:<id>=<state>" | "flag:<name>"
        public string Node;
    }

    public sealed class DialogueDef
    {
        public string Id;
        public readonly List<DialogueStart> Start = new List<DialogueStart>();
        public readonly Dictionary<string, DialogueNode> Nodes = new Dictionary<string, DialogueNode>(StringComparer.Ordinal);
    }

    public sealed class ItemDef
    {
        public string Id, Label, Description;
        public int Price;
        public bool Usable;     // use_item·퀵슬롯 등록 가능
        public double HealRatio;
    }

    public sealed class ObjectiveDef
    {
        public string Id, Kind, Text, Item, Target;   // Kind: talk / collect / quickslot / buy / turn_in / kill
        public int Count = 1;
        public string[] HintTargets = new string[0];
    }

    public sealed class QuestDef
    {
        public string Id, Title, Giver, Next;
        public string ReadyNotice;   // 반납 대상만 남았을 때(ready) 띄울 안내 — 어디로 가야 하는지
        public string[] Requires = new string[0];
        public bool StartActive, AutoComplete, ConsumeItems;
        public readonly List<ObjectiveDef> Objectives = new List<ObjectiveDef>();
        public int RewardGold;
        public readonly List<KeyValuePair<string, int>> RewardItems = new List<KeyValuePair<string, int>>();
    }

    public sealed class PlayLimits
    {
        public double MaxActionSeconds = 60.0;
        public double InteractRange = 2.5;
        public double Dt = 0.05;            // 고정 게임 시간 간격
        public double MoveSpeed = 5.0;      // m/s
        public double PlayerRadius = 0.4;
        public double CellSize = 0.5;
    }

    public sealed class PlayData
    {
        public string StartZone;
        public int StartGold;
        public int StartPotions;              // (0.8.5) 시작 인벤토리 작은 물약 수 (reset_options.start_potions 기본값)
        public string StartPotionItem = "potion_small";
        public double StartJitter;            // (0.8.5) 시작 위치를 seed 로 ±m 흔든다
        public int QuickSlots = 2;
        /// <summary>(0.8.5) 배치 변형: 이름 → (엔티티 id → 기준 위치 [x,z]). "a" = 엔티티 pos 그대로. 순서 = 선언 순서 (a 가 처음).</summary>
        public readonly List<string> LayoutNames = new List<string> { "a" };
        public readonly Dictionary<string, Dictionary<string, double[]>> Layouts = new Dictionary<string, Dictionary<string, double[]>>(StringComparer.Ordinal);
        public readonly PlayLimits Limits = new PlayLimits();
        public readonly List<ZoneDef> Zones = new List<ZoneDef>();
        public readonly Dictionary<string, DialogueDef> Dialogues = new Dictionary<string, DialogueDef>(StringComparer.Ordinal);
        public readonly List<ItemDef> Items = new List<ItemDef>();
        public readonly Dictionary<string, List<string>> Shops = new Dictionary<string, List<string>>(StringComparer.Ordinal);
        public readonly List<QuestDef> Quests = new List<QuestDef>();

        public ZoneDef Zone(string id)
        {
            foreach (var z in Zones) if (z.Id == id) return z;
            return null;
        }

        /// <summary>적 엔티티가 쓰는 시나리오 이름들 (밸런스 정의서에 있는지 부트가 확인).</summary>
        public IEnumerable<string> EnemyScenarios()
        {
            foreach (var z in Zones)
                foreach (var e in z.Entities)
                    if (e.Scenario != null) yield return e.Scenario;
        }

        public ItemDef Item(string id)
        {
            foreach (var i in Items) if (i.Id == id) return i;
            return null;
        }

        public QuestDef Quest(string id)
        {
            foreach (var q in Quests) if (q.Id == id) return q;
            return null;
        }

        /// <summary>JSON 텍스트 → 검증된 데이터. 오류는 모두 모아 예외 하나로. items·quests 는 없어도 됨(빈 목록).</summary>
        public static PlayData Parse(string worldJson, string dialoguesJson, string itemsJson = null, string questsJson = null)
        {
            var errs = new List<string>();
            var d = new PlayData();
            var w = JObject.Parse(worldJson);
            d.StartZone = (string)w["start_zone"];
            d.StartGold = (int?)w["start_gold"] ?? 0;
            d.QuickSlots = (int?)w["quick_slots"] ?? 2;
            d.StartPotions = (int?)w["start_potions"] ?? 0;
            d.StartPotionItem = (string)w["start_potion_item"] ?? d.StartPotionItem;
            d.StartJitter = (double?)w["start_jitter"] ?? 0;
            if (w["limits"] is JObject lim)
            {
                d.Limits.MaxActionSeconds = (double?)lim["max_action_seconds"] ?? d.Limits.MaxActionSeconds;
                d.Limits.InteractRange = (double?)lim["interact_range"] ?? d.Limits.InteractRange;
                d.Limits.Dt = (double?)lim["dt"] ?? d.Limits.Dt;
                d.Limits.MoveSpeed = (double?)lim["move_speed"] ?? d.Limits.MoveSpeed;
                d.Limits.PlayerRadius = (double?)lim["player_radius"] ?? d.Limits.PlayerRadius;
                d.Limits.CellSize = (double?)lim["cell_size"] ?? d.Limits.CellSize;
            }
            var ids = new HashSet<string>(StringComparer.Ordinal);
            foreach (var zt in (JArray)w["zones"] ?? new JArray())
            {
                var z = new ZoneDef
                {
                    Id = (string)zt["id"], Label = (string)zt["label"],
                    MinX = (double)zt["bounds"][0], MinZ = (double)zt["bounds"][1],
                    MaxX = (double)zt["bounds"][2], MaxZ = (double)zt["bounds"][3],
                    SpawnX = (double)zt["spawn"][0], SpawnZ = (double)zt["spawn"][1],
                };
                foreach (var et in (JArray)zt["entities"] ?? new JArray())
                {
                    var e = new EntityDef
                    {
                        Id = (string)et["id"], Role = (string)et["role"], Label = (string)et["label"],
                        X = (double)et["pos"][0], Z = (double)et["pos"][1],
                        Radius = (double?)et["radius"] ?? 0.5, Height = (double?)et["height"] ?? 1.8,
                        Actions = Strings(et["actions"]), Tags = Strings(et["tags"]),
                        AlwaysKnown = (bool?)et["always_known"] ?? false,
                        Dialogue = (string)et["dialogue"], Item = (string)et["item"], ToZone = (string)et["to_zone"],
                        Scenario = (string)et["scenario"], AggroRadius = (double?)et["aggro_radius"] ?? 0,
                        Checkpoint = (string)et["checkpoint"], Xp = (int?)et["xp"] ?? 0,
                        Jitter = (double?)et["jitter"] ?? 0,
                    };
                    foreach (var lt in (JArray)et["loot"] ?? new JArray())
                        e.Loot.Add(new KeyValuePair<string, int>((string)lt["id"], (int?)lt["count"] ?? 1));
                    if (e.Role == "enemy" && (e.Scenario == null || e.AggroRadius <= 0)) errs.Add(e.Id + ": enemy 는 scenario·aggro_radius 필요");
                    if (string.IsNullOrEmpty(e.Id)) errs.Add("entity id 없음 (zone " + z.Id + ")");
                    else if (!ids.Add(e.Id)) errs.Add("중복 id " + e.Id);
                    z.Entities.Add(e);
                }
                foreach (var ot in (JArray)zt["obstacles"] ?? new JArray())
                {
                    z.Obstacles.Add(new ObstacleDef
                    {
                        Id = (string)ot["id"], X = (double)ot["center"][0], Z = (double)ot["center"][1],
                        SizeX = (double)ot["size"][0], SizeZ = (double)ot["size"][1],
                        Height = (double?)ot["height"] ?? 2.0,
                    });
                }
                d.Zones.Add(z);
            }
            if (d.Zone(d.StartZone) == null) errs.Add("start_zone '" + d.StartZone + "' 없음");
            d.Layouts["a"] = new Dictionary<string, double[]>(StringComparer.Ordinal);
            foreach (var lp in (JObject)w["layouts"] ?? new JObject())
            {
                if (lp.Key.StartsWith("_")) continue;
                if (d.Layouts.ContainsKey(lp.Key)) { errs.Add("layout '" + lp.Key + "' 중복 (a 는 기본 배치)"); continue; }
                var m = new Dictionary<string, double[]>(StringComparer.Ordinal);
                foreach (var ep in (JObject)lp.Value)
                {
                    if (!ids.Contains(ep.Key)) errs.Add("layout " + lp.Key + ": 엔티티 '" + ep.Key + "' 없음");
                    m[ep.Key] = new[] { (double)ep.Value[0], (double)ep.Value[1] };
                }
                d.Layouts[lp.Key] = m;
                d.LayoutNames.Add(lp.Key);
            }

            // ---- 아이템·상점
            if (itemsJson != null)
            {
                var ij = JObject.Parse(itemsJson);
                foreach (var it in (JArray)ij["items"] ?? new JArray())
                    d.Items.Add(new ItemDef
                    {
                        Id = (string)it["id"], Label = (string)it["label"], Description = (string)it["description"] ?? "",
                        Price = (int?)it["price"] ?? 0, Usable = (bool?)it["usable"] ?? false, HealRatio = (double?)it["heal_ratio"] ?? 0,
                    });
                foreach (var p in (JObject)ij["shops"] ?? new JObject())
                    d.Shops[p.Key] = new List<string>(Strings(p.Value));
            }

            // ---- 퀘스트
            if (questsJson != null)
            {
                var qj = JObject.Parse(questsJson);
                foreach (var qt in (JArray)qj["quests"] ?? new JArray())
                {
                    var q = new QuestDef
                    {
                        Id = (string)qt["id"], Title = (string)qt["title"], Giver = (string)qt["giver"], Next = (string)qt["next"],
                        Requires = Strings(qt["requires"]), StartActive = (bool?)qt["start_active"] ?? false,
                        AutoComplete = (bool?)qt["auto_complete"] ?? false, ConsumeItems = (bool?)qt["consume_items"] ?? false,
                        ReadyNotice = (string)qt["ready_notice"],
                    };
                    foreach (var ot in (JArray)qt["objectives"] ?? new JArray())
                        q.Objectives.Add(new ObjectiveDef
                        {
                            Id = (string)ot["id"], Kind = (string)ot["kind"], Text = (string)ot["text"], Item = (string)ot["item"],
                            Target = (string)ot["target"], Count = (int?)ot["count"] ?? 1, HintTargets = Strings(ot["hint_targets"]),
                        });
                    if (qt["rewards"] is JObject rw)
                    {
                        q.RewardGold = (int?)rw["gold"] ?? 0;
                        foreach (var ri in (JArray)rw["items"] ?? new JArray())
                            q.RewardItems.Add(new KeyValuePair<string, int>((string)ri["id"], (int?)ri["count"] ?? 1));
                    }
                    d.Quests.Add(q);
                }
            }

            // ---- 대화
            var dj = JObject.Parse(dialoguesJson);
            foreach (var p in (JObject)dj["dialogues"] ?? new JObject())
            {
                var def = new DialogueDef { Id = p.Key };
                var st = p.Value["start"];
                if (st is JArray sa)
                    foreach (var r in sa) def.Start.Add(new DialogueStart { If = (string)r["if"], Node = (string)r["node"] });
                else def.Start.Add(new DialogueStart { Node = (string)st });
                foreach (var np in (JObject)p.Value["nodes"] ?? new JObject())
                {
                    var n = new DialogueNode { Id = np.Key, Speaker = (string)np.Value["speaker"], Text = (string)np.Value["text"] };
                    foreach (var ct in (JArray)np.Value["choices"] ?? new JArray())
                    {
                        var c = new DialogueChoice { Text = (string)ct["text"], Next = (string)ct["next"] };
                        foreach (var ef in (JArray)ct["effects"] ?? new JArray())
                            foreach (var kv in (JObject)ef)
                                c.Effects.Add(new DialogueEffect { Kind = kv.Key, Arg = (string)kv.Value });
                        n.Choices.Add(c);
                    }
                    if (n.Choices.Count == 0 || n.Choices.Count > 4) errs.Add("대화 " + p.Key + "/" + np.Key + ": 선택지 1~4개");
                    def.Nodes[n.Id] = n;
                }
                d.Dialogues[def.Id] = def;
            }

            // ---- 교차 검증
            var effectKinds = new HashSet<string> { "accept_quest", "complete_quest", "open_shop", "set_flag" };
            foreach (var def in d.Dialogues.Values)
            {
                if (def.Start.Count == 0 || def.Start[def.Start.Count - 1].If != null) errs.Add("대화 " + def.Id + ": start 마지막 항목은 조건 없는 기본 노드");
                foreach (var s in def.Start)
                {
                    if (!def.Nodes.ContainsKey(s.Node ?? "")) errs.Add("대화 " + def.Id + ": start 노드 '" + s.Node + "' 없음");
                    if (s.If != null && !ValidCondition(d, s.If)) errs.Add("대화 " + def.Id + ": 조건 '" + s.If + "' 형식 오류");
                }
                foreach (var n in def.Nodes.Values)
                    foreach (var c in n.Choices)
                    {
                        if (c.Next != null && !def.Nodes.ContainsKey(c.Next)) errs.Add("대화 " + def.Id + "/" + n.Id + ": next '" + c.Next + "' 없음");
                        foreach (var ef in c.Effects)
                        {
                            if (!effectKinds.Contains(ef.Kind)) errs.Add("대화 " + def.Id + "/" + n.Id + ": 모르는 효과 " + ef.Kind);
                            if ((ef.Kind == "accept_quest" || ef.Kind == "complete_quest") && d.Quest(ef.Arg) == null) errs.Add("대화 " + def.Id + ": 퀘스트 '" + ef.Arg + "' 없음");
                            if (ef.Kind == "open_shop" && !d.Shops.ContainsKey(ef.Arg ?? "")) errs.Add("대화 " + def.Id + ": 상점 '" + ef.Arg + "' 없음");
                        }
                    }
            }
            foreach (var z in d.Zones)
                foreach (var e in z.Entities)
                {
                    if (e.Dialogue != null && !d.Dialogues.ContainsKey(e.Dialogue)) errs.Add(e.Id + ": dialogue '" + e.Dialogue + "' 없음");
                    if (e.Item != null && d.Item(e.Item) == null) errs.Add(e.Id + ": item '" + e.Item + "' 없음");
                    if (e.ToZone != null && d.Zone(e.ToZone) == null) errs.Add(e.Id + ": to_zone '" + e.ToZone + "' 없음");
                    foreach (var lt in e.Loot) if (d.Item(lt.Key) == null) errs.Add(e.Id + ": loot item '" + lt.Key + "' 없음");
                    if (e.Checkpoint != null && !z.Entities.Exists(x => x.Id == e.Checkpoint)) errs.Add(e.Id + ": checkpoint '" + e.Checkpoint + "' 가 같은 지역에 없음");
                }
            foreach (var s in d.Shops)
                foreach (var i in s.Value)
                    if (d.Item(i) == null) errs.Add("상점 " + s.Key + ": item '" + i + "' 없음");
            var kinds = new HashSet<string> { "talk", "collect", "quickslot", "buy", "turn_in", "kill" };
            foreach (var q in d.Quests)
            {
                foreach (var r in q.Requires) if (d.Quest(r) == null) errs.Add(q.Id + ": requires '" + r + "' 없음");
                if (q.Next != null && d.Quest(q.Next) == null) errs.Add(q.Id + ": next '" + q.Next + "' 없음");
                foreach (var o in q.Objectives)
                {
                    if (!kinds.Contains(o.Kind)) errs.Add(q.Id + "/" + o.Id + ": 모르는 kind " + o.Kind);
                    if (o.Item != null && d.Item(o.Item) == null) errs.Add(q.Id + "/" + o.Id + ": item '" + o.Item + "' 없음");
                }
                foreach (var ri in q.RewardItems) if (d.Item(ri.Key) == null) errs.Add(q.Id + ": 보상 item '" + ri.Key + "' 없음");
            }

            if (d.StartPotions > 0 && d.Item(d.StartPotionItem) == null) errs.Add("start_potion_item '" + d.StartPotionItem + "' 없음");
            if (errs.Count > 0) throw new FormatException("플레이 데이터 오류: " + string.Join("; ", errs));
            return d;
        }

        static bool ValidCondition(PlayData d, string c)
        {
            if (c.StartsWith("flag:")) return c.Length > 5;
            if (!c.StartsWith("quest:")) return false;
            var p = c.Substring(6).Split('=');
            return p.Length == 2 && d.Quest(p[0]) != null && Array.IndexOf(QuestStates.All, p[1]) >= 0;
        }

        static string[] Strings(JToken t)
        {
            if (!(t is JArray a)) return new string[0];
            var r = new string[a.Count];
            for (int i = 0; i < a.Count; i++) r[i] = (string)a[i];
            return r;
        }
    }

    public static class QuestStates
    {
        public const string Locked = "locked", Available = "available", Active = "active", Ready = "ready", Completed = "completed";
        /// <summary>locked = 선행 미완료, available = 받을 수 있음, ready = 반납만 남음.</summary>
        public static readonly string[] All = { Locked, Available, Active, Ready, Completed };
    }
}
