// 판 시작 조건 (0.8.5, 증류 평가 요청 DISTILL_EVAL_REQUEST.md).
//   ResetOptions: reset.options (PLAY_PROTOCOL 4.4.1) — start_gold / start_potions / layout. 선언·검사·로그 표현.
//   Placement:    reset.seed + layout → 엔티티 대기 위치·시작 위치. 순수 C#, 결정적 (seed 전용 난수, 조우 seed 와 별개).
// seed 가 바꾸는 것 = jitter 를 준 엔티티(약초·NPC·늑대왕)의 위치와 마을 시작 위치뿐. id·퀘스트·목표 글·hint_targets 는 그대로.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.Sim;

namespace Qa.Play.World
{
    public sealed class ResetOptions
    {
        public int StartGold;
        public int StartPotions;
        public string Layout = "a";

        public const int MaxGold = 200, MaxPotions = 5;

        public static ResetOptions Defaults(PlayData d) => new ResetOptions
        {
            StartGold = d.StartGold, StartPotions = d.StartPotions, Layout = d.LayoutNames[0],
        };

        /// <summary>play_description.reset_options (4.4.1).</summary>
        public static JArray Declaration(PlayData d) => new JArray
        {
            new JObject
            {
                ["name"] = "start_gold", ["type"] = "int", ["min"] = 0, ["max"] = MaxGold, ["default"] = d.StartGold,
                ["description"] = "시작 골드",
            },
            new JObject
            {
                ["name"] = "start_potions", ["type"] = "int", ["min"] = 0, ["max"] = MaxPotions, ["default"] = d.StartPotions,
                ["description"] = "시작 인벤토리 작은 물약 수 (퀵슬롯에는 등록되지 않음)",
            },
            new JObject
            {
                ["name"] = "layout", ["type"] = "enum", ["values"] = new JArray(d.LayoutNames.ToArray()), ["default"] = d.LayoutNames[0],
                ["description"] = "채집물·NPC·늑대왕 대기 위치 변형 (a = 기본 배치). seed 는 같은 변형 안의 흔들림",
            },
        };

        /// <summary>reset.options 검사. 오류 → FormatException(메시지) — 세션이 bad_request 로.</summary>
        public static ResetOptions Parse(JToken tok, PlayData d)
        {
            var o = Defaults(d);
            if (tok == null || tok.Type == JTokenType.Null) return o;
            if (!(tok is JObject obj)) throw new FormatException("options 는 객체여야 함");
            foreach (var p in obj.Properties())
            {
                switch (p.Name)
                {
                    case "start_gold": o.StartGold = Int(p, 0, MaxGold); break;
                    case "start_potions": o.StartPotions = Int(p, 0, MaxPotions); break;
                    case "layout":
                        var v = p.Value.Type == JTokenType.String ? (string)p.Value : null;
                        if (v == null || !d.Layouts.ContainsKey(v))
                            throw new FormatException("options.layout 은 " + string.Join("|", d.LayoutNames) + " 중 하나: " + p.Value.ToString(Newtonsoft.Json.Formatting.None));
                        o.Layout = v;
                        break;
                    default:
                        throw new FormatException("모르는 reset 옵션 '" + p.Name + "' (선언: start_gold, start_potions, layout)");
                }
            }
            return o;
        }

        static int Int(JProperty p, int lo, int hi)
        {
            if (p.Value.Type != JTokenType.Integer) throw new FormatException("options." + p.Name + " 는 정수여야 함");
            long v = p.Value.Value<long>();
            if (v < lo || v > hi) throw new FormatException("options." + p.Name + " 범위 밖 (" + lo + "~" + hi + "): " + v);
            return (int)v;
        }

        public JObject ToWire() => new JObject { ["start_gold"] = StartGold, ["start_potions"] = StartPotions, ["layout"] = Layout };
    }

    /// <summary>엔티티 대기 위치 결정. 기준 위치(layout 덮어쓰기 또는 pos) + seed 흔들림 (±jitter, 0.1 m 단위).
    /// 후보가 조건(지역 안·장애물 밖·지역 시작점에서 도달 가능·다른 엔티티와 1.5 m 이상·적 어그로 밖)을 못 맞추면 다시 뽑고, 끝내 못 맞추면 기준 위치.</summary>
    public static class Placement
    {
        const int Tries = 24;
        const double MinGap = 1.5, AggroMargin = 2.0, EdgeMargin = 1.5;
        const long Salt = 0x4C41594F5554L;   // "LAYOUT" — 조우 seed(EncounterSeed)와 겹치지 않게

        public static Rng LayoutRng(long seed) => new Rng(unchecked(seed ^ Salt));

        public static void Apply(PlayData data, ResetOptions opt, Rng rng, Func<string, GridPath> grid,
                                 Func<string, List<EntityState>> entities)
        {
            var over = data.Layouts[opt.Layout];
            foreach (var z in data.Zones)
            {
                var list = entities(z.Id);
                // 1) 기준 위치
                foreach (var e in list)
                {
                    if (over.TryGetValue(e.Id, out var p)) { e.X = p[0]; e.Z = p[1]; }
                    else { e.X = e.Def.X; e.Z = e.Def.Z; }
                }
                // 2) 흔들림 (정의 순서대로 — 앞의 것은 정해진 위치, 뒤의 것은 기준 위치와 비교)
                var g = grid(z.Id);
                foreach (var e in list)
                {
                    if (e.Def.Jitter <= 0) continue;
                    double ax = e.X, az = e.Z, j = e.Def.Jitter;
                    for (int t = 0; t < Tries; t++)
                    {
                        double x = Math.Round(ax + rng.Uniform(-j, j), 1), zz = Math.Round(az + rng.Uniform(-j, j), 1);
                        if (Ok(data, z, g, list, e, x, zz)) { e.X = x; e.Z = zz; break; }
                    }
                }
            }
        }

        /// <summary>시작 위치 흔들림 (마을 시작점 ±start_jitter). 조건 못 맞추면 시작점 그대로.</summary>
        public static void StartPos(PlayData data, ZoneDef z, GridPath g, List<EntityState> list, Rng rng, ref double px, ref double pz)
        {
            double j = data.StartJitter;
            if (j <= 0) return;
            double ax = px, az = pz;
            for (int t = 0; t < Tries; t++)
            {
                double x = Math.Round(ax + rng.Uniform(-j, j), 1), zz = Math.Round(az + rng.Uniform(-j, j), 1);
                if (!g.IsFree(x, zz) || !Inside(z, x, zz)) continue;
                bool clear = true;
                foreach (var o in list)
                {
                    double need = o.Def.Role == "enemy" ? o.Def.AggroRadius + AggroMargin : MinGap;
                    if (GridPath.Dist(x, zz, o.X, o.Z) < need) { clear = false; break; }
                }
                if (!clear) continue;
                px = x; pz = zz;
                return;
            }
        }

        static bool Inside(ZoneDef z, double x, double zz) =>
            x >= z.MinX + EdgeMargin && x <= z.MaxX - EdgeMargin && zz >= z.MinZ + EdgeMargin && zz <= z.MaxZ - EdgeMargin;

        static bool Ok(PlayData data, ZoneDef z, GridPath g, List<EntityState> list, EntityState e, double x, double zz)
        {
            if (!Inside(z, x, zz) || !g.IsFree(x, zz)) return false;
            bool enemy = e.Def.Role == "enemy";
            // 지역 시작점·다른 엔티티와 거리 (적이면 어그로 반경 + 여유 — 입구·체크포인트·채집물이 어그로 안에 들지 않게)
            if (enemy && GridPath.Dist(x, zz, z.SpawnX, z.SpawnZ) < e.Def.AggroRadius + AggroMargin) return false;
            foreach (var o in list)
            {
                if (ReferenceEquals(o, e)) continue;
                double need = MinGap;
                if (enemy) need = Math.Max(need, e.Def.AggroRadius + AggroMargin);
                if (o.Def.Role == "enemy") need = Math.Max(need, o.Def.AggroRadius + AggroMargin);
                if (GridPath.Dist(x, zz, o.X, o.Z) < need) return false;
            }
            // 지역 시작점에서 상호작용 거리까지 걸어갈 수 있어야 한다
            var path = g.Find(z.SpawnX, z.SpawnZ, x, zz, Math.Max(data.Limits.InteractRange - 0.6, data.Limits.CellSize));
            return path != null;
        }
    }
}
