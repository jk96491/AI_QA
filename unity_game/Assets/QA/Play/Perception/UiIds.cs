// UI 안정 id: QaTag 가 있으면 그 id, 없으면 가장 가까운 QaTag 조상 id + "/" + 이름 경로 (같은 이름 형제는 #index).
using System.Collections.Generic;
using System.Text;
using UnityEngine;

namespace Qa.Play.Perception
{
    public static class UiIds
    {
        public static string Of(Transform t)
        {
            var tag = t.GetComponent<QaTag>();
            if (tag != null && !string.IsNullOrEmpty(tag.id)) return tag.id;
            var parts = new List<string>();
            var cur = t;
            while (cur != null)
            {
                var ct = cur.GetComponent<QaTag>();
                if (ct != null && !string.IsNullOrEmpty(ct.id))
                {
                    parts.Reverse();
                    return ct.id + "/" + string.Join("/", parts);
                }
                parts.Add(Segment(cur));
                cur = cur.parent;
            }
            parts.Reverse();
            return "ui/" + string.Join("/", parts);
        }

        static string Segment(Transform t)
        {
            var p = t.parent;
            if (p == null) return t.name;
            int same = 0, index = 0;
            for (int i = 0; i < p.childCount; i++)
            {
                var c = p.GetChild(i);
                if (c.name != t.name) continue;
                if (c == t) index = same;
                same++;
            }
            return same > 1 ? t.name + "#" + index : t.name;
        }

        /// <summary>리치텍스트 태그 제거 + 앞뒤 공백 정리.</summary>
        public static string PlainText(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length);
            bool inTag = false;
            foreach (var ch in s)
            {
                if (ch == '<') { inTag = true; continue; }
                if (ch == '>' && inTag) { inTag = false; continue; }
                if (!inTag) sb.Append(ch);
            }
            return sb.ToString().Trim();
        }
    }
}
