// 게임 내부 타입 (game_sim/core/types.py, event_log.py 대응). 학습 쪽과 공유하지 않는다 — 경계는 PROTOCOL.md.
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Qa.Data;

namespace Qa.Sim
{
    public static class SimConst
    {
        public const double Eps = 1e-9;
    }

    public enum ActionKind { Idle, Skill, MoveToward, MoveAway, Potion, RespondGimmick, Evade }

    /// <summary>BT 가 결정(300ms)마다 내놓는 행동. 불변·캐시 (판 루프에서 할당 없음).</summary>
    public sealed class BtAction
    {
        public readonly ActionKind Kind;
        public readonly SkillDef Skill;

        BtAction(ActionKind kind, SkillDef skill) { Kind = kind; Skill = skill; }

        public static readonly BtAction Idle = new BtAction(ActionKind.Idle, null);
        public static readonly BtAction MoveToward = new BtAction(ActionKind.MoveToward, null);
        public static readonly BtAction MoveAway = new BtAction(ActionKind.MoveAway, null);
        public static readonly BtAction Potion = new BtAction(ActionKind.Potion, null);
        public static readonly BtAction RespondGimmick = new BtAction(ActionKind.RespondGimmick, null);
        /// <summary>아레나 위험 지역에서 안전 지점으로 이동 (0.8.0).</summary>
        public static readonly BtAction Evade = new BtAction(ActionKind.Evade, null);

        public static BtAction Use(SkillDef skill) => new BtAction(ActionKind.Skill, skill);
    }

    /// <summary>BT 가 보는 현재 상태. 판마다 1개를 재사용한다.</summary>
    public sealed class Observation
    {
        public double Time;
        public double HpRatio;
        public double Resource;
        public double ResourceRatio;
        public double MaxResource;
        public double Distance;
        public double BossReach;
        public double BossHpRatio;
        public bool GcdReady;
        /// <summary>쿨·자원 기준 사용 가능 (GCD 무시), SkillDef.Index 로 조회.</summary>
        public bool[] SkillAvailable;
        public int PotionsLeft;
        public bool PotionReady;
        public bool GimmickWarning;
        /// <summary>지금 위치의 위험도 0~1 (아레나 패턴: 경고 원·장판·돌진 띠·탄 경로). 아레나 없는 보스는 항상 0.</summary>
        public double Danger;
        /// <summary>스킬별 남은 쿨타임(초), SkillDef.Index (0.8.1).</summary>
        public double[] CooldownLeft;
        /// <summary>플레이어 피해 버프 중 / 보스 표식 중 (0.8.1 Setup → Burst 콤보).</summary>
        public bool BuffActive, TargetMarked;

        public bool InBossReach => Distance <= BossReach + SimConst.Eps;
    }

    /// <summary>(시간, 종류, 내용) 이벤트. 꺼져 있으면 호출부가 페이로드를 만들지 않는다 (Enabled 확인).</summary>
    public sealed class EventLog
    {
        public readonly bool Enabled;
        public readonly JArray Events = new JArray();

        public EventLog(bool enabled) { Enabled = enabled; }

        public void Record(double t, string kind, JObject payload = null)
        {
            if (!Enabled) return;
            Events.Add(new JArray(System.Math.Round(t, 2), kind, payload ?? new JObject()));
        }
    }

    /// <summary>삽입 순서를 유지하는 이름 → 누적값 (block_time 용, 키가 적어 선형 탐색).</summary>
    public sealed class OrderedAccumulator
    {
        readonly List<string> _keys = new List<string>();
        readonly List<double> _vals = new List<double>();

        public void Add(string key, double v)
        {
            for (int i = 0; i < _keys.Count; i++)
                if (ReferenceEquals(_keys[i], key) || _keys[i] == key) { _vals[i] += v; return; }
            _keys.Add(key);
            _vals.Add(v);
        }

        public JObject ToJson(int digits)
        {
            var o = new JObject();
            for (int i = 0; i < _keys.Count; i++) o[_keys[i]] = System.Math.Round(_vals[i], digits);
            return o;
        }
    }
}
