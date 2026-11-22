// 게임 데이터 저장소·검증기 (game_sim/spec/loader.py 대응).
// 기동 시 모든 정의서를 한 번에 읽고 검증해 캐시한다 → 이후 Unity API 호출 없음 (서버 스레드 안전).
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace Qa.Data
{
    /// <summary>정의서 텍스트 공급자. Unity 빌드는 Resources, 테스트는 파일 등.</summary>
    public interface ISpecSource
    {
        /// <summary>"classes/warrior" 처럼 확장자 없는 경로의 JSON 텍스트. 없으면 null.</summary>
        string Read(string path);
        /// <summary>폴더 안 JSON 파일 이름 (확장자 없음).</summary>
        IEnumerable<string> List(string folder);
    }

    public sealed class SpecRepository
    {
        /// <summary>모든 직업 BT 가 공통으로 요구하는 파라미터 (학습 쪽 페르소나·정책이 이 이름을 씀).</summary>
        public static readonly string[] RequiredClassParams =
        {
            "survival_hp_threshold", "dps_hp_floor", "w_burst", "w_dps", "w_survival",
            "potion_hp", "resource_reserve", "min_commit",
        };
        public static readonly string[] RangedRequiredParams = { "kite_distance" };

        public string GameName { get; private set; }
        public string GameVersion { get; private set; }
        public IReadOnlyList<string> ClassNames => _classNames;
        public IReadOnlyList<Scenario> Scenarios => _scenarios;

        readonly List<string> _classNames = new List<string>();
        readonly Dictionary<string, ClassSpec> _classes = new Dictionary<string, ClassSpec>(StringComparer.Ordinal);
        readonly List<Scenario> _scenarios = new List<Scenario>();
        readonly Dictionary<string, BossSpec> _bossByScenario = new Dictionary<string, BossSpec>(StringComparer.Ordinal);

        public SpecRepository(ISpecSource src)
        {
            var problems = new List<string>();

            var game = SpecJson.ParseObject(Require(src, "game"), "game.json");
            GameName = SpecJson.Str(game, "game", "qa_arena");
            GameVersion = SpecJson.Str(game, "game_version", null) ?? throw new SpecException("game.json", "game_version 누락");

            var names = new List<string>(src.List("classes"));
            names.Sort(StringComparer.Ordinal);
            foreach (var n in names)
            {
                var source = "classes/" + n + ".json";
                var spec = ClassSpec.FromJson(SpecJson.ParseObject(Require(src, "classes/" + n), source), source);
                if (spec.Name != n) problems.Add(source + ": class 이름 " + spec.Name + " 이 파일 이름과 다름");
                foreach (var p in ValidateClass(spec)) problems.Add(source + ": " + p);
                _classNames.Add(spec.Name);
                _classes[spec.Name] = spec;
            }
            if (_classNames.Count == 0) problems.Add("classes/ 에 직업 정의서가 없음");

            var sc = SpecJson.ParseObject(Require(src, "scenarios"), "scenarios.json");
            if (!(sc["scenarios"] is JObject scs)) throw new SpecException("scenarios.json", "scenarios 객체 누락");
            var bossJson = new Dictionary<string, JObject>(StringComparer.Ordinal);
            foreach (var prop in scs.Properties())
            {
                var s = Scenario.FromJson(prop.Name, (JObject)prop.Value);
                _scenarios.Add(s);
                if (!bossJson.TryGetValue(s.Boss, out var bj))
                {
                    bj = SpecJson.ParseObject(Require(src, "bosses/" + s.Boss), "bosses/" + s.Boss + ".json");
                    bossJson[s.Boss] = bj;
                }
                var source = "scenarios.json:" + s.Name;
                var boss = BossSpec.FromJson(s.Name == "base" ? bj : s.Apply(bj, source), source);
                foreach (var p in ValidateBoss(boss)) problems.Add(source + ": " + p);
                _bossByScenario[s.Name] = boss;
            }
            if (!_bossByScenario.ContainsKey("base")) problems.Add("scenarios.json: 'base' 시나리오 필수");

            if (problems.Count > 0) throw new SpecException("QaData", problems);
        }

        static string Require(ISpecSource src, string path)
        {
            return src.Read(path) ?? throw new SpecException(path + ".json", "파일 없음");
        }

        public bool HasClass(string name) => name != null && _classes.ContainsKey(name);
        public ClassSpec Class(string name) => _classes[name];
        public bool HasScenario(string name) => name != null && _bossByScenario.ContainsKey(name);
        public BossSpec BossFor(string scenario) => _bossByScenario[string.IsNullOrEmpty(scenario) ? "base" : scenario];

        // ------------------------------------------------------------------ 검증
        public static List<string> ValidateClass(ClassSpec spec)
        {
            var problems = new List<string>();
            foreach (var k in RequiredClassParams)
                if (!spec.HasParam(k)) problems.Add("필수 파라미터 누락: " + k);
            if (spec.Ranged)
                foreach (var k in RangedRequiredParams)
                    if (!spec.HasParam(k)) problems.Add("원거리 필수 파라미터 누락: " + k);
            int nOpt = 0;
            foreach (var p in spec.ParamList)
            {
                if (p.Low >= p.High) problems.Add(p.Name + ": range 하한 >= 상한");
                else if (!(p.Low <= p.Default && p.Default <= p.High)) problems.Add(p.Name + ": default 가 범위 밖");
                if (p.Group != ParamDef.GroupBt && p.Group != ParamDef.GroupPersona)
                    problems.Add(p.Name + ": group 은 bt|persona");
                if (p.Optimize) nOpt++;
            }
            if (nOpt < 1 || nOpt > 20) problems.Add("최적화 파라미터 수 " + nOpt + " (권장 5~20)");
            if (spec.SkillsByRole(SkillRole.Basic).Count == 0) problems.Add("basic 역할 스킬이 최소 1개 필요");
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var s in spec.Skills)
            {
                if (!seen.Add(s.Name)) problems.Add("스킬 이름 중복: " + s.Name);
                if (s.Damage < 0 || s.Cooldown < 0 || s.Cost < 0 || s.CastTime < 0) problems.Add(s.Name + ": 음수 수치");
                if (s.Cost > spec.Stats.MaxResource) problems.Add(s.Name + ": 비용이 최대 자원보다 큼");
            }
            if (!(spec.Stats.Armor >= 0 && spec.Stats.Armor < 1)) problems.Add("armor 는 [0, 1)");
            return problems;
        }

        public static List<string> ValidateBoss(BossSpec b)
        {
            var problems = new List<string>();
            int n = b.PhaseThresholds.Length;
            for (int i = 1; i < n; i++)
                if (b.PhaseThresholds[i] > b.PhaseThresholds[i - 1]) { problems.Add("phase_thresholds 는 내림차순"); break; }
            if (b.PhaseDamageMult.Length != n + 1 || b.PhaseSpeedMult.Length != n + 1)
                problems.Add("phase_*_mult 길이는 phase_thresholds + 1");
            if (b.GimmickWindow <= 0) problems.Add("gimmick_window > 0 필요");
            if (b.MaxHp <= 0) problems.Add("max_hp > 0 필요");
            return problems;
        }
    }
}
