// 스킬 바 (0.8.1, PLAYER_SKILL_BT_REQUEST 4장) — 표시 전용. 전투는 학습된 BT 가 하므로 누를 수 없다 (IMGUI, 관찰 대상 아님).
//   슬롯 = 평타 제외 스킬 + 물약. 쿨타임 = 위에서 아래로 쓸기 + 남은 초, 끝나면 반짝.
//   자원 부족 = 회색 + 비용 빨강, 사거리 밖 = 빨간 테두리, 시전 중 = 진행 테두리, BT 가 방금 쓴 스킬 = 눌림 + 고른 블록 태그.
using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.Data;
using UnityEngine;

namespace Qa.Presentation
{
    public sealed partial class BattleViewer
    {
        readonly Dictionary<string, float> _skillPressedAt = new Dictionary<string, float>();
        readonly Dictionary<string, string> _skillBlock = new Dictionary<string, string>();
        readonly Dictionary<int, float> _readyFlashAt = new Dictionary<int, float>();
        readonly Dictionary<int, bool> _wasCooling = new Dictionary<int, bool>();
        float _potionPressedAt = -10f;

        /// <summary>OnEvent 앞에서: 스킬·물약 사용 기록 (화면 표시용).</summary>
        void NoteSkillEvent(string kind, JObject pl)
        {
            if (kind == "skill")
            {
                var n = (string)pl["name"];
                _skillPressedAt[n] = Time.unscaledTime;
                _skillBlock[n] = (string)pl["block"];
            }
            else if (kind == "potion") _potionPressedAt = Time.unscaledTime;
        }

        static Color RoleColor(SkillRole r)
        {
            switch (r)
            {
                case SkillRole.Dps: return new Color(0.95f, 0.6f, 0.25f);
                case SkillRole.Burst: return new Color(1f, 0.3f, 0.3f);
                case SkillRole.Defense: return new Color(0.35f, 0.65f, 1f);
                case SkillRole.GapClose: return new Color(0.85f, 0.45f, 0.95f);
                case SkillRole.Mobility: return new Color(0.4f, 0.95f, 0.55f);
                case SkillRole.Setup: return new Color(1f, 0.85f, 0.3f);
                default: return new Color(0.7f, 0.7f, 0.7f);
            }
        }

        void Border(Rect r, Color c, float t)
        {
            Fill(new Rect(r.x, r.y, r.width, t), c);
            Fill(new Rect(r.x, r.yMax - t, r.width, t), c);
            Fill(new Rect(r.x, r.y, t, r.height), c);
            Fill(new Rect(r.xMax - t, r.y, t, r.height), c);
        }

        void DrawSkillBar()
        {
            if (_sim == null || _spec == null) return;
            var p = _sim.PlayerState;
            var skills = new List<SkillDef>();
            foreach (var s in _spec.Skills) if (s.Role != SkillRole.Basic) skills.Add(s);
            int n = skills.Count + 1;   // + 물약
            const float sz = 54f, gap = 6f;
            float w = n * sz + (n - 1) * gap;
            float x0 = (Screen.width - w) / 2 - (_panel ? 150 : 0) + (_playMode ? 60 : 0);   // 플레이 모드: 왼쪽 아래 "QA 플레이어" 패널을 피해 오른쪽으로
            float y = Screen.height - 112 - 14 - sz - 26;
            float now = Time.unscaledTime;
            double dist = _sim.Distance;

            for (int i = 0; i < n; i++)
            {
                var r = new Rect(x0 + i * (sz + gap), y, sz, sz);
                if (i == skills.Count) { DrawPotionSlot(r, p, i + 1, now); continue; }
                var s = skills[i];
                double cd = p.Cooldowns[s.Index];
                bool cooling = cd > 1e-6;
                bool noRes = p.Resource + 1e-9 < s.Cost;
                bool outRange = !s.IsSelfTarget && dist > s.Range + 1e-6;
                bool casting = p.Casting == s;
                var rc = RoleColor(s.Role);
                if (_wasCooling.TryGetValue(s.Index, out var was) && was && !cooling) _readyFlashAt[s.Index] = now;
                _wasCooling[s.Index] = cooling;

                bool pressed = _skillPressedAt.TryGetValue(s.Name, out var pt) && now - pt < 0.35f;
                var rr = pressed ? new Rect(r.x + 3, r.y + 3, r.width - 6, r.height - 6) : r;
                Fill(rr, new Color(0.06f, 0.07f, 0.09f, 0.88f));
                var face = noRes || p.Dead ? new Color(0.35f, 0.35f, 0.38f, 0.9f) : new Color(rc.r * 0.55f, rc.g * 0.55f, rc.b * 0.55f, 0.95f);
                Fill(new Rect(rr.x + 3, rr.y + 3, rr.width - 6, rr.height - 6), face);
                GUI.Label(new Rect(rr.x + 4, rr.y + 2, 20, 16), (i + 1).ToString(), _small);
                GUI.Label(new Rect(rr.x, rr.y + 16, rr.width, 22), "<b>" + Short(Names.Skill(s.Name)) + "</b>", _center);
                if (cooling)
                {
                    float frac = (float)(cd / Math.Max(0.01, s.Cooldown));
                    Fill(new Rect(rr.x + 3, rr.y + 3, rr.width - 6, (rr.height - 6) * frac), new Color(0f, 0f, 0f, 0.62f));
                    GUI.Label(new Rect(rr.x, rr.y + 30, rr.width, 22), "<b>" + (cd >= 1 ? Math.Ceiling(cd).ToString("0") : cd.ToString("0.0")) + "</b>", _center);
                }
                if (s.Cost > 0)
                    GUI.Label(new Rect(rr.x, rr.yMax - 17, rr.width - 4, 16), "<color=" + (noRes ? "#FF5050" : "#C8C8C8") + ">" + s.Cost.ToString("0") + "</color>", _small);
                if (_readyFlashAt.TryGetValue(s.Index, out var ft) && now - ft < 0.4f)
                    Fill(rr, new Color(1f, 1f, 1f, 0.35f * (1f - (now - ft) / 0.4f)));
                if (outRange) Border(rr, new Color(1f, 0.25f, 0.2f, 0.9f), 2f);
                if (casting)
                {
                    float prog = 1f - (float)(p.CastRemaining / Math.Max(0.01, s.CastTime));
                    Fill(new Rect(rr.x, rr.yMax - 4, rr.width * prog, 4), new Color(1f, 0.9f, 0.5f, 1f));
                    Border(rr, new Color(1f, 0.9f, 0.5f, 0.9f), 2f);
                }
                if (pressed)
                {
                    Border(rr, Color.white, 2f);
                    if (_skillBlock.TryGetValue(s.Name, out var blk))
                        GUI.Label(new Rect(r.x - 10, r.y - 20, r.width + 20, 18), "<color=#FFFFFF>" + BlockTag(blk) + "</color>", _center);
                }
            }
        }

        void DrawPotionSlot(Rect r, Qa.Sim.Player p, int key, float now)
        {
            bool pressed = now - _potionPressedAt < 0.35f;
            var rr = pressed ? new Rect(r.x + 3, r.y + 3, r.width - 6, r.height - 6) : r;
            Fill(rr, new Color(0.06f, 0.07f, 0.09f, 0.88f));
            Fill(new Rect(rr.x + 3, rr.y + 3, rr.width - 6, rr.height - 6), p.Potions > 0 ? new Color(0.15f, 0.45f, 0.2f, 0.95f) : new Color(0.3f, 0.3f, 0.32f, 0.9f));
            GUI.Label(new Rect(rr.x + 4, rr.y + 2, 20, 16), key.ToString(), _small);
            GUI.Label(new Rect(rr.x, rr.y + 16, rr.width, 22), "<b>물약</b>", _center);
            GUI.Label(new Rect(rr.x, rr.yMax - 18, rr.width - 4, 16), "x" + p.Potions, _small);
            if (p.PotionCd > 1e-6)
            {
                float frac = (float)(p.PotionCd / Math.Max(0.01, _spec.Stats.PotionCooldown));
                Fill(new Rect(rr.x + 3, rr.y + 3, rr.width - 6, (rr.height - 6) * frac), new Color(0f, 0f, 0f, 0.62f));
                GUI.Label(new Rect(rr.x, rr.y + 30, rr.width, 22), "<b>" + Math.Ceiling(p.PotionCd).ToString("0") + "</b>", _center);
            }
            if (pressed) Border(rr, Color.white, 2f);
        }

        static string Short(string s) => s.Length > 4 ? s.Substring(0, 4) : s;
    }
}
