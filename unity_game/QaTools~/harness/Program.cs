// 테스트 하네스: Unity 없이 같은 로직 소스로 QA 서버를 띄운다 (scratchpad 전용).
using System;
using System.Collections.Generic;
using System.IO;
using Qa.Data;
using Qa.Protocol;
using Qa.Sim;

sealed class FileSource : ISpecSource
{
    readonly string _root;
    public FileSource(string root) { _root = root; }
    public string Read(string path) { var f = Path.Combine(_root, path + ".json"); return File.Exists(f) ? File.ReadAllText(f) : null; }
    public IEnumerable<string> List(string folder)
    {
        foreach (var f in Directory.GetFiles(Path.Combine(_root, folder), "*.json")) yield return Path.GetFileNameWithoutExtension(f);
    }
}

static class Program
{
    /// <summary>stats &lt;dataRoot&gt; &lt;class&gt; &lt;scenario&gt; &lt;n&gt; [params json] — 손 튜닝(default) 판 n 개 통계 + 아레나 패턴 피격 집계.</summary>
    static void Stats(string[] a)
    {
        var repo = new SpecRepository(new FileSource(a[1]));
        string cls = a[2], scen = a[3];
        int n = int.Parse(a[4]);
        var upd = a.Length > 5 ? Newtonsoft.Json.Linq.JObject.Parse(a[5]) : null;
        var cfg = new SimConfig().WithRecordEvents(Environment.GetEnvironmentVariable("QA_DMG") == "1");
        var dmg = new SortedDictionary<string, double>();
        int cleared = 0, deaths = 0, potions = 0;
        double elapsed = 0;
        var spawned = new SortedDictionary<string, int>();
        var hits = new SortedDictionary<string, int>();
        var blocks = new SortedDictionary<string, double>();
        var spec = repo.Class(cls);
        var uses = new double[spec.Skills.Count];
        var epsUsed = new int[spec.Skills.Count];
        int cancels = 0;
        var sw = System.Diagnostics.Stopwatch.StartNew();
        for (int i = 0; i < n; i++)
        {
            long seed = 1000 + i;
            var sim = new CombatSim(repo.Class(cls), repo.BossFor(scen), upd, seed, new Newtonsoft.Json.Linq.JValue(seed), cfg, null, null);
            var r = sim.Run();
            for (int k = 0; k < uses.Length; k++) { uses[k] += sim.SkillUses[k]; if (sim.SkillUses[k] > 0) epsUsed[k]++; }
            cancels += sim.CastCancels;
            if ((bool)r["cleared"]) cleared++;
            deaths += (int)r["deaths"];
            potions += (int)r["consumables_used"];
            elapsed += (double)r["elapsed"];
            foreach (var p in ((Newtonsoft.Json.Linq.JObject)r["block_time"]).Properties())
            { blocks.TryGetValue(p.Name, out var v); blocks[p.Name] = v + (double)p.Value; }
            if (cfg.RecordEvents)
            {
                double known = 0;
                foreach (Newtonsoft.Json.Linq.JArray e in (Newtonsoft.Json.Linq.JArray)r["events"])
                {
                    string k = (string)e[1]; var pl = (Newtonsoft.Json.Linq.JObject)e[2];
                    string key = k == "hit" ? (string)pl["kind"] : k == "player_hit" ? (string)pl["source"] : null;
                    if (key == null) continue;
                    double v = k == "hit" ? (double)pl["dmg"] : (double)pl["damage"];
                    dmg.TryGetValue(key, out var o); dmg[key] = o + v; known += v;
                }
                dmg.TryGetValue("pool(rest)", out var pr); dmg["pool(rest)"] = pr + (double)r["damage_taken"] - known;
            }
            var ar = sim.ArenaState;
            if (ar == null) continue;
            foreach (var kv in ar.Spawned) { spawned.TryGetValue(kv.Key, out var v); spawned[kv.Key] = v + kv.Value; }
            foreach (var kv in ar.Hits) { hits.TryGetValue(kv.Key, out var v); hits[kv.Key] = v + kv.Value; }
        }
        sw.Stop();
        Console.WriteLine(cls + " " + scen + " n=" + n + " clear=" + (100.0 * cleared / n).ToString("0.0") + "% elapsed=" + (elapsed / n).ToString("0.0") +
                          "s deaths=" + ((double)deaths / n).ToString("0.00") + " potions=" + ((double)potions / n).ToString("0.00") +
                          " ms/ep=" + (sw.Elapsed.TotalMilliseconds / n).ToString("0.00"));
        double tot = 0; foreach (var u in uses) tot += u;
        var ss = new List<string>();
        foreach (var sk in spec.Skills) ss.Add(sk.Name + " " + (100 * uses[sk.Index] / Math.Max(1, tot)).ToString("0") + "% (" + (uses[sk.Index] / n).ToString("0.0") + "/판, " + (100.0 * epsUsed[sk.Index] / n).ToString("0") + "% 판)");
        Console.WriteLine("  skills: " + string.Join(", ", ss) + "  cast_cancel " + ((double)cancels / n).ToString("0.0") + "/판");
        double bt = 0; foreach (var v in blocks.Values) bt += v;
        var bs = new List<string>(); foreach (var kv in blocks) bs.Add(kv.Key + " " + (100 * kv.Value / bt).ToString("0") + "%");
        Console.WriteLine("  blocks: " + string.Join(", ", bs));
        var hs = new List<string>();
        foreach (var kv in spawned) { hits.TryGetValue(kv.Key, out var h); hs.Add(kv.Key + " " + h + "/" + kv.Value); }
        if (hits.TryGetValue("pool_ticks", out var pt)) hs.Add("pool_ticks " + pt);
        if (hs.Count > 0) Console.WriteLine("  hits/spawned: " + string.Join(", ", hs));
        if (dmg.Count > 0) { var ds = new List<string>(); foreach (var kv in dmg) ds.Add(kv.Key + " " + (kv.Value / n).ToString("0")); Console.WriteLine("  dmg/ep: " + string.Join(", ", ds)); }
    }

    /// <summary>trace &lt;dataRoot&gt; &lt;class&gt; &lt;scenario&gt; &lt;seed&gt; &lt;from_t&gt; &lt;to_t&gt; [params] — 이벤트 + 매 틱 블록·거리.</summary>
    static void Trace(string[] a)
    {
        var repo = new SpecRepository(new FileSource(a[1]));
        long seed = long.Parse(a[4]);
        double t0 = double.Parse(a[5]), t1 = double.Parse(a[6]);
        var upd = a.Length > 7 ? Newtonsoft.Json.Linq.JObject.Parse(a[7]) : null;
        var sim = new CombatSim(repo.Class(a[2]), repo.BossFor(a[3]), upd, seed, new Newtonsoft.Json.Linq.JValue(seed), new SimConfig().WithRecordEvents(true), null, null);
        sim.Begin();
        int ev = 0;
        while (!sim.Done)
        {
            sim.Step();
            var es = sim.Events;
            for (; ev < es.Count; ev++)
            {
                var e = (Newtonsoft.Json.Linq.JArray)es[ev];
                double t = (double)e[0];
                if (t >= t0 && t <= t1) Console.WriteLine("  " + e.ToString(Newtonsoft.Json.Formatting.None));
            }
            if (sim.Time >= t0 && sim.Time <= t1)
                Console.WriteLine(sim.Time.ToString("0.0") + " " + sim.CurrentBlock + " d=" + sim.Distance.ToString("0.0") + " hp=" + sim.PlayerState.HpRatio.ToString("0.00") +
                                  " res=" + sim.PlayerState.Resource.ToString("0") + " boss=" + sim.BossState.HpRatio.ToString("0.000"));
        }
        Console.WriteLine(sim.Result().ToString(Newtonsoft.Json.Formatting.None).Substring(0, 300));
    }

    static void Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "trace") { Trace(args); return; }
        if (args.Length > 0 && args[0] == "stats") { Stats(args); return; }
        int port = int.Parse(args[1]);
        var repo = new SpecRepository(new FileSource(args[0]));
        var cfg = new SimConfig();
        var gameHost = new QaArenaHost(repo, cfg);
        var server = new Btqa.Game.QaServer("127.0.0.1", port, () => new Btqa.Game.QaSession(gameHost), Console.Error.WriteLine);
        server.Start();
        Console.WriteLine("LISTENING " + server.Port);
        server.Serve();
    }
}
