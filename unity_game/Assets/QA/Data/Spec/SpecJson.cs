// 정의서 JSON 읽기 도우미. UnityEngine 비의존.
using System;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Qa.Data
{
    /// <summary>정의서 형식 오류 (어느 파일·무엇이 문제인지 모아서 보고).</summary>
    public sealed class SpecException : Exception
    {
        public readonly string SourceFile;
        public readonly IReadOnlyList<string> Problems;

        public SpecException(string source, IReadOnlyList<string> problems)
            : base(source + ": " + string.Join("; ", problems))
        {
            SourceFile = source;
            Problems = problems;
        }

        public SpecException(string source, string problem) : this(source, new[] { problem }) { }
    }

    public static class SpecJson
    {
        static readonly JsonSerializerSettings Settings = new JsonSerializerSettings
        {
            DateParseHandling = DateParseHandling.None,
            FloatParseHandling = FloatParseHandling.Double,
        };

        public static JObject ParseObject(string text, string source)
        {
            try
            {
                var token = JsonConvert.DeserializeObject<JToken>(text, Settings);
                if (token is JObject obj) return obj;
            }
            catch (JsonException ex)
            {
                throw new SpecException(source, "JSON 파싱 실패: " + ex.Message);
            }
            throw new SpecException(source, "최상위가 JSON 객체가 아님");
        }

        public static double Num(JObject o, string key, string source)
        {
            var t = o[key];
            if (t == null) throw new SpecException(source, "필드 누락: " + key);
            if (t.Type != JTokenType.Float && t.Type != JTokenType.Integer)
                throw new SpecException(source, key + " 는 숫자여야 함");
            return t.Value<double>();
        }

        public static double Num(JObject o, string key, double fallback, string source)
        {
            return o[key] == null ? fallback : Num(o, key, source);
        }

        public static string Str(JObject o, string key, string fallback)
        {
            var t = o[key];
            return t == null || t.Type == JTokenType.Null ? fallback : t.Value<string>();
        }

        public static bool Bool(JObject o, string key, bool fallback)
        {
            var t = o[key];
            return t == null || t.Type == JTokenType.Null ? fallback : t.Value<bool>();
        }

        public static double[] NumArray(JObject o, string key, double[] fallback, string source)
        {
            var t = o[key];
            if (t == null) return fallback;
            if (!(t is JArray arr)) throw new SpecException(source, key + " 는 숫자 배열이어야 함");
            var outp = new double[arr.Count];
            for (int i = 0; i < arr.Count; i++) outp[i] = arr[i].Value<double>();
            return outp;
        }

        /// <summary>허용 목록에 없는 키 (밑줄 시작 주석 키는 무시) — 오타 잡기용.</summary>
        public static List<string> UnknownKeys(JObject o, ICollection<string> allowed)
        {
            var bad = new List<string>();
            foreach (var p in o.Properties())
                if (!p.Name.StartsWith("_") && !allowed.Contains(p.Name)) bad.Add(p.Name);
            return bad;
        }
    }
}
