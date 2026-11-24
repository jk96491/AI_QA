// 플레이 모드 세계 상태 (순수 C#). 시간은 Step(dt) 을 부를 때만 흐른다 = 세계 정지.
// reset 마다 새로 만든다 (판 사이 static 상태 없음). 퀘스트·대화·인벤토리·상점·창 상태가 모두 여기 있다 (UI 는 그리기만).
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.Sim;

namespace Qa.Play.World
{
    public sealed class EntityState
    {
        public readonly EntityDef Def;
        public bool Active = true;   // 주운 아이템 등은 false
        public EntityState(EntityDef def) { Def = def; }
        public string Id => Def.Id;
    }

    public sealed class WorldEvent
    {
        public double Time;
        public string Kind;
        public JObject Payload;
        public JArray ToWire() => new JArray(Math.Round(Time, 2), Kind, Payload ?? new JObject());
    }

    public sealed class DialogueView
    {
        public string Npc, NodeId, Speaker, Text;
        public readonly List<string> Choices = new List<string>();
    }

    public sealed class QuestState
    {
        public readonly QuestDef Def;
        public bool Accepted, Completed;
        public readonly int[] Stored;     // talk·buy·turn_in 진행 (collect·quickslot 은 인벤토리에서 계산)
        public int[] LastProgress;
        public bool NoticeShown;          // ready_notice 를 띄웠는지 (한 번만)
        public QuestState(QuestDef def)
        {
            Def = def;
            Stored = new int[def.Objectives.Count];
        }
    }

    public sealed class ItemStack
    {
        public string Id;
        public int Count;
    }

    public sealed class WorldState
    {
        public readonly PlayData Data;
        public readonly long Seed;
        public readonly string Class;
        public readonly Rng Rng;

        public long Steps { get; private set; }
        public double Time => Steps * Data.Limits.Dt;

        public string Zone { get; private set; }
        public ZoneDef ZoneDef => Data.Zone(Zone);
        public GridPath Grid { get; private set; }
        readonly Dictionary<string, GridPath> _grids = new Dictionary<string, GridPath>(StringComparer.Ordinal);
        public double PlayerX, PlayerZ;
        public double HpRatio = 1.0;
        public int Level = 1;
        public int Xp { get; private set; }
        public int Encounters { get; private set; }   // 조우 순번 (조우 seed 의 근원)
        public int CombatDeaths { get; private set; } // 지금까지 전투에서 죽은 횟수 합 (field_state.deaths_so_far)
        public int Gold { get; private set; }
        public string PlayerState = "idle";   // idle / moving

        /// <summary>입력을 막는 창: null / "dialog" / "quests" / "inventory" / "shop".</summary>
        public string Modal { get; private set; }
        /// <summary>창 위에 뜬 안내 팝업 (null / "inventory"). 떠 있으면 아래 창 버튼을 가린다.</summary>
        public string Tip { get; private set; }
        /// <summary>관찰용 최상위 모달.</summary>
        public string TopModal => Tip != null ? "tip" : Modal;
        public DialogueView Dialogue { get; private set; }
        public string ShopNpc { get; private set; }
        public string ShopMessage { get; private set; }
        public string InventorySelected { get; private set; }
        /// <summary>게임 안내 (notice 사건). 화면 토스트용 — 관찰에는 사건으로 보인다.</summary>
        public string Notice { get; private set; }
        public int NoticeCount { get; private set; }

        readonly SortedSet<string> _flags = new SortedSet<string>(StringComparer.Ordinal);
        public IEnumerable<string> Flags => _flags;
        public bool HasFlag(string f) => _flags.Contains(f);

        readonly Dictionary<string, List<EntityState>> _zoneEntities = new Dictionary<string, List<EntityState>>(StringComparer.Ordinal);
        public IReadOnlyList<EntityState> Entities => _zoneEntities[Zone];

        readonly List<ItemStack> _inventory = new List<ItemStack>();
        public IReadOnlyList<ItemStack> Inventory => _inventory;
        public readonly string[] QuickSlots;

        readonly List<QuestState> _quests = new List<QuestState>();
        public IReadOnlyList<QuestState> Quests => _quests;

        readonly List<WorldEvent> _pending = new List<WorldEvent>();   // 직전 관찰 이후
        /// <summary>사건 발생 시 (로그용).</summary>
        public event Action<WorldEvent> OnEvent;

        public WorldState(PlayData data, long seed, string cls)
        {
            Data = data;
            Seed = seed;
            Class = cls;
            Rng = new Rng(seed);
            Gold = data.StartGold;
            QuickSlots = new string[Math.Max(1, data.QuickSlots)];
            foreach (var z in data.Zones)
            {
                var list = new List<EntityState>();
                foreach (var e in z.Entities) list.Add(new EntityState(e));
                _zoneEntities[z.Id] = list;
            }
            foreach (var q in data.Quests) _quests.Add(new QuestState(q));
            EnterZone(data.StartZone, false);
        }

        /// <summary>reset 직후 1회: 시작 퀘스트 수락 (new_game 사건 뒤에 오도록 세션이 부른다).</summary>
        public void Begin()
        {
            foreach (var q in _quests) if (q.Def.StartActive) Accept(q);
        }

        void EnterZone(string zone, bool emit)
        {
            Zone = zone;
            var z = ZoneDef;
            if (!_grids.TryGetValue(zone, out var g))
                _grids[zone] = g = new GridPath(z, Data.Limits.CellSize, Data.Limits.PlayerRadius);
            Grid = g;
            PlayerX = z.SpawnX;
            PlayerZ = z.SpawnZ;
            if (emit) Emit("zone_entered", new JObject { ["zone"] = zone });
        }

        public EntityState Entity(string id)
        {
            if (id == null) return null;
            foreach (var e in Entities) if (e.Id == id && e.Active) return e;
            return null;
        }

        public double DistanceTo(EntityState e) => GridPath.Dist(PlayerX, PlayerZ, e.Def.X, e.Def.Z);

        /// <summary>고정 dt 1틱. 이동은 행동(MoveTo)이 이 전에 위치를 바꾼다.</summary>
        public void Step() => Steps++;

        /// <summary>전투 경과 시간만큼 세계 시간을 진행 (dt 칸 단위로 올림).</summary>
        public long AddSeconds(double seconds)
        {
            long n = (long)Math.Ceiling(seconds / Data.Limits.Dt - 1e-9);
            if (n > 0) Steps += n;
            return n;
        }

        // ------------------------------------------------------------------ 적·전투
        /// <summary>어그로 반경 안의 살아 있는 적 (가장 가까운 것, 동률이면 id 순).</summary>
        public EntityState EnemyInAggro()
        {
            EntityState best = null;
            double bd = double.PositiveInfinity;
            foreach (var e in Entities)
            {
                if (!e.Active || e.Def.Role != "enemy") continue;
                double d = DistanceTo(e);
                if (d > e.Def.AggroRadius) continue;
                if (d < bd || (d == bd && string.CompareOrdinal(e.Id, best.Id) < 0)) { best = e; bd = d; }
            }
            return best;
        }

        /// <summary>조우 시작: 순번 증가 + 결정적 조우 seed = mix(reset seed, 순번).</summary>
        public long BeginEncounter(EntityState enemy, out string encounterId)
        {
            Encounters++;
            encounterId = "enc_" + Encounters;
            Emit("combat_started", new JObject { ["encounter_id"] = encounterId, ["enemy"] = enemy.Id, ["scenario"] = enemy.Def.Scenario });
            return EncounterSeed(Seed, Encounters);
        }

        public static long EncounterSeed(long seed, int k)
        {
            unchecked
            {
                ulong z = (ulong)seed + 0x9E3779B97F4A7C15UL * (ulong)k;
                z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
                z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
                z ^= z >> 31;
                return (long)(z & 0x7FFFFFFFUL);   // 0 ~ 2^31-1 (JSON·다른 언어에서 다루기 쉽게)
            }
        }

        /// <summary>퀵슬롯에 등록된 첫 물약(회복 아이템) — 전투에 가져가는 물약 (PLAY_PROTOCOL 4.7, v0.3). 없으면 null.</summary>
        public string QuickSlotPotion()
        {
            foreach (var it in QuickSlots)
            {
                if (it == null || CountOf(it) <= 0) continue;
                var d = Data.Item(it);
                if (d != null && d.Usable && d.HealRatio > 0) return it;
            }
            return null;
        }

        /// <summary>보스 결계: 회복 직전 필드 상태를 돌려주고 barrier_restore 사건. 체력·자원은 전투 준비 상태(full)로.</summary>
        public JObject Barrier(string encounterId, string potionItem, int carried)
        {
            var before = new JObject
            {
                ["hp_ratio"] = Math.Round(HpRatio, 4),
                ["resource_ratio"] = 1.0,   // 필드에는 자원 소모가 없다
                ["potions"] = potionItem != null ? CountOf(potionItem) : 0,
                ["deaths_so_far"] = CombatDeaths,
            };
            HpRatio = 1.0;
            Emit("barrier_restore", new JObject
            {
                ["encounter_id"] = encounterId, ["field_state"] = before.DeepClone(),
                ["potion_item"] = potionItem, ["potions_carried"] = carried,
            });
            return before;
        }

        /// <summary>전투 종료 처리. 승리: 적 제거·전리품·경험치·kill 목표. 패배: 체크포인트 부활 (적은 그대로 = 체력 회복).
        /// 전투에서 마신 물약(potionsUsed)은 인벤토리에서 뺀다 (v0.3).</summary>
        public JObject EndEncounter(EntityState enemy, string encounterId, bool cleared, int deaths, string potionItem, int potionsUsed)
        {
            var aftermath = new JObject();
            CombatDeaths += Math.Max(0, deaths);
            if (potionItem != null && potionsUsed > 0) RemoveItem(potionItem, Math.Min(potionsUsed, CountOf(potionItem)));
            var loot = new JArray();
            if (cleared)
            {
                enemy.Active = false;
                foreach (var l in enemy.Def.Loot)
                {
                    AddItem(l.Key, l.Value);
                    loot.Add(new JObject { ["id"] = l.Key, ["count"] = l.Value });
                }
                Xp += enemy.Def.Xp;
                foreach (var q in _quests)
                {
                    if (!q.Accepted || q.Completed) continue;
                    for (int i = 0; i < q.Def.Objectives.Count; i++)
                    {
                        var o = q.Def.Objectives[i];
                        if (o.Kind == "kill" && o.Target == enemy.Id) q.Stored[i]++;
                    }
                }
                aftermath["xp"] = enemy.Def.Xp;
                aftermath["respawned_at"] = null;
            }
            else
            {
                aftermath["xp"] = 0;
                var cp = enemy.Def.Checkpoint != null ? Entity(enemy.Def.Checkpoint) : null;
                if (cp != null)
                {
                    // 체크포인트 바로 옆(같은 칸이 막혀 있으면 지역 시작점)
                    PlayerX = cp.Def.X;
                    PlayerZ = cp.Def.Z;
                    if (!Grid.IsFree(PlayerX, PlayerZ)) { PlayerX = ZoneDef.SpawnX; PlayerZ = ZoneDef.SpawnZ; }
                    aftermath["respawned_at"] = cp.Id;
                }
                else
                {
                    PlayerX = ZoneDef.SpawnX;
                    PlayerZ = ZoneDef.SpawnZ;
                    aftermath["respawned_at"] = Zone + ":spawn";
                }
            }
            aftermath["loot"] = loot;
            aftermath["potions_used"] = potionItem != null ? Math.Max(0, potionsUsed) : 0;
            HpRatio = 1.0;   // 시작 상태 full (v0.1) — 필드 상태를 전투로 가져가지도, 전투 결과를 필드로 가져오지도 않는다
            PlayerState = "idle";
            Emit("combat_ended", new JObject { ["encounter_id"] = encounterId, ["enemy"] = enemy.Id, ["cleared"] = cleared });
            if (!cleared) Emit("respawned", new JObject { ["at"] = (string)aftermath["respawned_at"] });
            UpdateQuests();
            return aftermath;
        }

        // ------------------------------------------------------------------ 사건
        public void Emit(string kind, JObject payload = null)
        {
            var ev = new WorldEvent { Time = Time, Kind = kind, Payload = payload ?? new JObject() };
            _pending.Add(ev);
            OnEvent?.Invoke(ev);
        }

        public List<WorldEvent> DrainEvents()
        {
            var r = new List<WorldEvent>(_pending);
            _pending.Clear();
            return r;
        }

        // ------------------------------------------------------------------ 월드 상호작용 (interact)
        public bool Pickup(EntityState e)
        {
            if (e.Def.Item == null || !e.Active) return false;
            e.Active = false;
            Emit("picked_up", new JObject { ["target"] = e.Id, ["item"] = e.Def.Item });
            AddItem(e.Def.Item, 1);
            UpdateQuests();
            return true;
        }

        public bool EnterPortal(EntityState e)
        {
            if (e.Def.ToZone == null) return false;
            EnterZone(e.Def.ToZone, true);
            return true;
        }

        // ------------------------------------------------------------------ 인벤토리
        public int CountOf(string item)
        {
            foreach (var s in _inventory) if (s.Id == item) return s.Count;
            return 0;
        }

        void AddItem(string item, int n)
        {
            if (n <= 0) return;
            ItemStack st = null;
            foreach (var s in _inventory) if (s.Id == item) st = s;
            if (st == null) _inventory.Add(st = new ItemStack { Id = item });
            st.Count += n;
            Emit("item_added", new JObject { ["item"] = item, ["count"] = n, ["total"] = st.Count });
        }

        bool RemoveItem(string item, int n)
        {
            for (int i = 0; i < _inventory.Count; i++)
            {
                var s = _inventory[i];
                if (s.Id != item) continue;
                if (s.Count < n) return false;
                s.Count -= n;
                if (s.Count == 0)
                {
                    _inventory.RemoveAt(i);
                    for (int k = 0; k < QuickSlots.Length; k++) if (QuickSlots[k] == item) QuickSlots[k] = null;
                    if (InventorySelected == item) InventorySelected = null;
                }
                Emit("item_removed", new JObject { ["item"] = item, ["count"] = n, ["total"] = s.Count });
                return true;
            }
            return false;
        }

        void AddGold(int delta)
        {
            if (delta == 0) return;
            Gold += delta;
            Emit("gold_changed", new JObject { ["delta"] = delta, ["gold"] = Gold });
        }

        /// <summary>use_item. 실패 사유(없음 null).</summary>
        public string UseItem(string item)
        {
            if (CountOf(item) <= 0) return "unknown_target";
            var def = Data.Item(item);
            if (def == null || !def.Usable) return "invalid_state";
            if (def.HealRatio > 0 && HpRatio >= 1.0) return "invalid_state";
            RemoveItem(item, 1);
            HpRatio = Math.Min(1.0, HpRatio + def.HealRatio);
            Emit("item_used", new JObject { ["item"] = item });
            UpdateQuests();
            return null;
        }

        // ------------------------------------------------------------------ 창 (UI 버튼 → 여기)
        public bool OpenWindow(string name)
        {
            if (Modal != null) return false;
            Modal = name;
            Emit("window_opened", new JObject { ["window"] = name });
            if (name == "inventory" && !HasFlag("tip_inventory_seen"))
            {
                Tip = "inventory";
                SetFlag("tip_inventory_seen");
                Emit("tip_shown", new JObject { ["tip"] = Tip });
            }
            return true;
        }

        public bool CloseWindow(string name)
        {
            if (Modal != name || name == "dialog" || Tip != null) return false;
            Modal = null;
            if (name == "shop") { ShopNpc = null; ShopMessage = null; }
            if (name == "inventory") InventorySelected = null;
            Emit("window_closed", new JObject { ["window"] = name });
            return true;
        }

        public bool CloseTip()
        {
            if (Tip == null) return false;
            Emit("tip_closed", new JObject { ["tip"] = Tip });
            Tip = null;
            return true;
        }

        public bool SelectSlot(string item)
        {
            if (Modal != "inventory" || Tip != null || CountOf(item) <= 0) return false;
            InventorySelected = item;
            Emit("slot_selected", new JObject { ["item"] = item });
            return true;
        }

        public bool CanAssignSelected => InventorySelected != null && (Data.Item(InventorySelected)?.Usable ?? false);

        public bool AssignQuickSlot(int slot)
        {
            if (Modal != "inventory" || Tip != null || !CanAssignSelected || slot < 0 || slot >= QuickSlots.Length) return false;
            QuickSlots[slot] = InventorySelected;
            Emit("quickslot_set", new JObject { ["slot"] = slot, ["item"] = InventorySelected });
            UpdateQuests();
            return true;
        }

        // ------------------------------------------------------------------ 상점
        public IReadOnlyList<string> ShopItems => ShopNpc != null && Data.Shops.TryGetValue(ShopNpc, out var l) ? l : (IReadOnlyList<string>)new string[0];

        /// <summary>구매 버튼 활성 규칙: potion_small 은 항상 눌림 (부족하면 실패 메시지), 나머지는 골드 부족 시 비활성 — 의도적 함정 두 종류.</summary>
        public bool BuyEnabled(string item)
        {
            var def = Data.Item(item);
            if (def == null) return false;
            return item == "potion_small" || Gold >= def.Price;
        }

        public bool Buy(string item)
        {
            if (Modal != "shop" || ShopNpc == null) return false;
            var def = Data.Item(item);
            if (def == null) return false;
            if (Gold < def.Price)
            {
                ShopMessage = "골드가 부족합니다 (필요 " + def.Price + "G, 보유 " + Gold + "G)";
                Emit("purchase_failed", new JObject { ["item"] = item, ["reason"] = "insufficient_gold", ["price"] = def.Price, ["gold"] = Gold });
                return true;
            }
            AddGold(-def.Price);
            AddItem(item, 1);
            ShopMessage = def.Label + "을(를) 샀습니다.";
            Emit("purchase", new JObject { ["item"] = item, ["price"] = def.Price });
            foreach (var q in _quests)
            {
                if (!q.Accepted || q.Completed) continue;
                for (int i = 0; i < q.Def.Objectives.Count; i++)
                {
                    var o = q.Def.Objectives[i];
                    if (o.Kind == "buy" && o.Item == item) q.Stored[i]++;
                }
            }
            UpdateQuests();
            return true;
        }

        // ------------------------------------------------------------------ 대화
        public bool OpenDialogue(EntityState npc)
        {
            var def = npc.Def.Dialogue == null ? null : Data.Dialogues[npc.Def.Dialogue];
            if (def == null) return false;
            string node = null;
            foreach (var s in def.Start)
                if (s.If == null || Condition(s.If)) { node = s.Node; break; }
            Modal = "dialog";
            ShowNode(npc.Id, def, node);
            Emit("dialog_opened", new JObject { ["npc"] = npc.Id, ["node"] = node });
            // talk 목표
            foreach (var q in _quests)
            {
                if (!q.Accepted || q.Completed) continue;
                for (int i = 0; i < q.Def.Objectives.Count; i++)
                {
                    var o = q.Def.Objectives[i];
                    if (o.Kind == "talk" && o.Target == npc.Id) q.Stored[i] = 1;
                }
            }
            UpdateQuests();
            return true;
        }

        void ShowNode(string npc, DialogueDef def, string nodeId)
        {
            var n = def.Nodes[nodeId];
            var v = new DialogueView { Npc = npc, NodeId = nodeId, Speaker = n.Speaker, Text = n.Text };
            foreach (var c in n.Choices) v.Choices.Add(c.Text);
            Dialogue = v;
        }

        public bool ChooseDialogue(int index)
        {
            if (Modal != "dialog" || Dialogue == null || index < 0 || index >= Dialogue.Choices.Count) return false;
            var npcId = Dialogue.Npc;
            var npc = Entity(npcId);
            var def = Data.Dialogues[npc.Def.Dialogue];
            var choice = def.Nodes[Dialogue.NodeId].Choices[index];
            Emit("dialog_choice", new JObject { ["npc"] = npcId, ["node"] = Dialogue.NodeId, ["index"] = index, ["text"] = choice.Text });
            string openShop = null;
            foreach (var ef in choice.Effects)
            {
                switch (ef.Kind)
                {
                    case "set_flag": SetFlag(ef.Arg); break;
                    case "accept_quest":
                    {
                        var q = Q(ef.Arg);
                        if (QuestStateOf(q) == QuestStates.Available) Accept(q);
                        break;
                    }
                    case "complete_quest":
                    {
                        var q = Q(ef.Arg);
                        if (QuestStateOf(q) == QuestStates.Ready)
                        {
                            for (int i = 0; i < q.Def.Objectives.Count; i++)
                                if (q.Def.Objectives[i].Kind == "turn_in") q.Stored[i] = 1;
                            Complete(q);
                        }
                        break;
                    }
                    case "open_shop": openShop = ef.Arg; break;
                }
            }
            if (choice.Next != null && openShop == null)
            {
                ShowNode(npcId, def, choice.Next);
                return true;
            }
            Dialogue = null;
            Modal = null;
            Emit("dialog_closed", new JObject { ["npc"] = npcId });
            if (openShop != null)
            {
                Modal = "shop";
                ShopNpc = openShop;
                ShopMessage = null;
                Emit("window_opened", new JObject { ["window"] = "shop", ["shop"] = openShop });
            }
            return true;
        }

        void ShowNotice(string text, string quest)
        {
            Notice = text;
            NoticeCount++;
            Emit("notice", new JObject { ["text"] = text, ["quest"] = quest });
        }

        void SetFlag(string f)
        {
            if (_flags.Add(f)) Emit("flag_set", new JObject { ["flag"] = f });
        }

        bool Condition(string c)
        {
            if (c.StartsWith("flag:")) return HasFlag(c.Substring(5));
            var p = c.Substring(6).Split('=');
            return QuestStateOf(Q(p[0])) == p[1];
        }

        // ------------------------------------------------------------------ 퀘스트
        public QuestState Q(string id)
        {
            foreach (var q in _quests) if (q.Def.Id == id) return q;
            return null;
        }

        public int Progress(QuestState q, int i)
        {
            var o = q.Def.Objectives[i];
            switch (o.Kind)
            {
                case "collect": return Math.Min(o.Count, q.Completed ? o.Count : CountOf(o.Item));
                case "quickslot": return q.Completed || Array.IndexOf(QuickSlots, o.Item) >= 0 ? 1 : 0;
                default: return Math.Min(o.Count, q.Completed ? o.Count : q.Stored[i]);
            }
        }

        public int Target(QuestState q, int i) => q.Def.Objectives[i].Kind == "collect" || q.Def.Objectives[i].Kind == "buy" ? q.Def.Objectives[i].Count : 1;

        bool AllDone(QuestState q, bool exceptTurnIn)
        {
            for (int i = 0; i < q.Def.Objectives.Count; i++)
            {
                if (exceptTurnIn && q.Def.Objectives[i].Kind == "turn_in") continue;
                if (Progress(q, i) < Target(q, i)) return false;
            }
            return true;
        }

        public string QuestStateOf(QuestState q)
        {
            if (q == null) return QuestStates.Locked;
            if (q.Completed) return QuestStates.Completed;
            if (q.Accepted)
            {
                bool hasTurnIn = false;
                foreach (var o in q.Def.Objectives) if (o.Kind == "turn_in") hasTurnIn = true;
                return hasTurnIn && AllDone(q, true) ? QuestStates.Ready : QuestStates.Active;
            }
            foreach (var r in q.Def.Requires) if (!(Q(r)?.Completed ?? false)) return QuestStates.Locked;
            return QuestStates.Available;
        }

        void Accept(QuestState q)
        {
            if (q.Accepted) return;
            q.Accepted = true;
            Emit("quest_accepted", new JObject { ["quest"] = q.Def.Id, ["title"] = q.Def.Title });
            UpdateQuests();
        }

        void Complete(QuestState q)
        {
            if (q.Completed) return;
            if (q.Def.ConsumeItems)
                foreach (var o in q.Def.Objectives)
                    if (o.Kind == "collect") RemoveItem(o.Item, o.Count);
            q.Completed = true;
            Emit("quest_completed", new JObject { ["quest"] = q.Def.Id, ["title"] = q.Def.Title });
            AddGold(q.Def.RewardGold);
            foreach (var ri in q.Def.RewardItems) AddItem(ri.Key, ri.Value);
            if (q.Def.Next != null) Accept(Q(q.Def.Next));
            UpdateQuests();
        }

        bool _updating;

        /// <summary>진행도 변화 사건 + 자동 완료. 상태가 바뀌는 모든 곳에서 부른다.</summary>
        public void UpdateQuests()
        {
            if (_updating) return;
            _updating = true;
            try
            {
                bool changed = true;
                while (changed)
                {
                    changed = false;
                    foreach (var q in _quests)
                    {
                        if (!q.Accepted || q.Completed) continue;
                        var cur = new int[q.Def.Objectives.Count];
                        for (int i = 0; i < cur.Length; i++) cur[i] = Progress(q, i);
                        if (q.LastProgress == null) q.LastProgress = new int[cur.Length];
                        for (int i = 0; i < cur.Length; i++)
                            if (cur[i] != q.LastProgress[i])
                                Emit("quest_progress", new JObject
                                {
                                    ["quest"] = q.Def.Id, ["objective"] = q.Def.Objectives[i].Id,
                                    ["progress"] = new JArray(cur[i], Target(q, i)),
                                });
                        q.LastProgress = cur;
                        if (!q.NoticeShown && q.Def.ReadyNotice != null && QuestStateOf(q) == QuestStates.Ready)
                        {
                            q.NoticeShown = true;
                            ShowNotice(q.Def.ReadyNotice, q.Def.Id);
                        }
                        if (q.Def.AutoComplete && AllDone(q, false))
                        {
                            _updating = false;
                            Complete(q);
                            _updating = true;
                            changed = true;
                            break;
                        }
                    }
                }
            }
            finally { _updating = false; }
        }

        /// <summary>퀘스트 마커로 위치를 아는 대상 (0.8.4): 진행 중(active) 퀘스트의 완료 안 된 목표(반납 제외)의 target·hint_targets,
        /// 반납 가능(ready) 퀘스트의 반납 목표 target·hint_targets. 같은 지역 판정은 호출 쪽 (지금 지역의 엔티티만 본다).</summary>
        public bool IsQuestMarkerTarget(string entityId)
        {
            foreach (var q in _quests)
            {
                var st = QuestStateOf(q);
                if (st != QuestStates.Active && st != QuestStates.Ready) continue;
                for (int i = 0; i < q.Def.Objectives.Count; i++)
                {
                    var o = q.Def.Objectives[i];
                    if (Progress(q, i) >= Target(q, i)) continue;
                    if ((o.Kind == "turn_in") != (st == QuestStates.Ready)) continue;
                    if (o.Target == entityId || Array.IndexOf(o.HintTargets, entityId) >= 0) return true;
                }
            }
            return false;
        }

        /// <summary>화면의 퀘스트 마커와 같은 정보: quest_available / quest_turn_in / objective / null.</summary>
        public string MarkerFor(string entityId)
        {
            foreach (var q in _quests)
            {
                var st = QuestStateOf(q);
                if (st == QuestStates.Ready)
                    foreach (var o in q.Def.Objectives) if (o.Kind == "turn_in" && o.Target == entityId) return "quest_turn_in";
            }
            foreach (var q in _quests)
                if (QuestStateOf(q) == QuestStates.Available && q.Def.Giver == entityId) return "quest_available";
            foreach (var q in _quests)
            {
                var st = QuestStateOf(q);
                if (st != QuestStates.Active) continue;
                for (int i = 0; i < q.Def.Objectives.Count; i++)
                {
                    var o = q.Def.Objectives[i];
                    if (Progress(q, i) >= Target(q, i) || o.Kind == "turn_in") continue;
                    if (o.Target == entityId || Array.IndexOf(o.HintTargets, entityId) >= 0) return "objective";
                }
            }
            return null;
        }
    }
}
