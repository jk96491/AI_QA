// 세션 로그 (PLAY_PROTOCOL 4.8): [game_time, kind, payload]. get_log 로 반환. reset 마다 새로.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace Qa.Play.Log
{
    public sealed class PlayLog
    {
        readonly List<JArray> _entries = new List<JArray>();
        public int Count => _entries.Count;

        public void Add(double time, string kind, JToken payload)
        {
            _entries.Add(new JArray(Math.Round(time, 2), kind, payload ?? new JObject()));
        }

        public JArray Since(int seq)
        {
            var a = new JArray();
            for (int i = Math.Max(0, seq); i < _entries.Count; i++) a.Add(_entries[i].DeepClone());
            return a;
        }

        public void Clear() => _entries.Clear();
    }
}
