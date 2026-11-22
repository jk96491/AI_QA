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
    static void Main(string[] args)
    {
        int port = int.Parse(args[1]);
        var repo = new SpecRepository(new FileSource(args[0]));
        var cfg = new SimConfig();
        var runner = new CombatEpisodeRunner(cfg);
        var server = new QaServer("127.0.0.1", port, () => new QaSession(repo, cfg, runner), Console.Error.WriteLine);
        server.Start();
        Console.WriteLine("LISTENING " + server.Port);
        server.Serve();
    }
}
