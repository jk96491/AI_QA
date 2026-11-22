// BT 파라미터 정의 (game_sim/spec/param.py 대응). describe 응답으로 학습 쪽에 공개된다.
using Newtonsoft.Json.Linq;

namespace Qa.Data
{
    public sealed class ParamDef
    {
        public const string GroupBt = "bt";            // 학습 대상 BT 값
        public const string GroupPersona = "persona";  // 페르소나가 정하는 N 설정값 (θ, φ)

        public readonly string Name;
        public readonly double Low;
        public readonly double High;
        public readonly double Default;   // 개발자 손 튜닝 값 (기준선)
        public readonly bool Optimize;
        public readonly string Group;
        public readonly string Unit;
        public readonly string Description;

        public ParamDef(string name, double low, double high, double @default, bool optimize,
                        string group, string unit, string description)
        {
            Name = name; Low = low; High = high; Default = @default; Optimize = optimize;
            Group = group; Unit = unit; Description = description;
        }

        public static ParamDef FromJson(string name, JObject d, string source)
        {
            var src = source + " params." + name;
            if (!(d["range"] is JArray range) || range.Count != 2)
                throw new SpecException(src, "range 는 [low, high]");
            var group = SpecJson.Str(d, "group", GroupBt);
            return new ParamDef(
                name,
                range[0].Value<double>(),
                range[1].Value<double>(),
                SpecJson.Num(d, "default", src),
                SpecJson.Bool(d, "optimize", group == GroupBt),
                group,
                SpecJson.Str(d, "unit", ""),
                SpecJson.Str(d, "description", ""));
        }

        public bool Contains(double v, double tol = 1e-9) => Low - tol <= v && v <= High + tol;

        public JObject ToWire()
        {
            return new JObject
            {
                ["name"] = Name,
                ["range"] = new JArray(Low, High),
                ["default"] = Default,
                ["optimize"] = Optimize,
                ["group"] = Group,
                ["unit"] = Unit,
                ["description"] = Description,
            };
        }
    }
}
