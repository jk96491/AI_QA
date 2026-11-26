// 고수준 행동 (PLAY_PROTOCOL 4.6). Start 로 시작 → ActionRunner 가 고정 dt 로 Step → done / failed / interrupted.
// move_to·interact·wait 는 순수 C# (WorldState 만 본다). 지각 판정은 Perceivable 위임으로 받는다.
using System;
using Newtonsoft.Json.Linq;
using Qa.Play.World;

namespace Qa.Play.Actions
{
    public enum ActionStatus { Running, Done, Failed, Interrupted }

    /// <summary>행동 인자 형식 오류 → error(bad_request) (action_result 가 아님).</summary>
    public sealed class ActionArgException : Exception
    {
        public ActionArgException(string m) : base(m) { }
    }

    public sealed class ActionContext
    {
        public WorldState World;
        /// <summary>엔티티 id 가 지금 플레이어에게 지각 가능한가 (omniscient 면 항상 true).</summary>
        public Func<string, bool> Perceivable;
        /// <summary>화면 (raw 입력: 엔티티 화면 위치·플레이어 위치). v0.4</summary>
        public Qa.Play.Perception.IPlayScene Scene;
    }

    public interface IPlayAction
    {
        /// <summary>시작. 즉시 끝나면 Done/Failed 를 돌려준다.</summary>
        ActionStatus Start(ActionContext ctx, JObject args);
        /// <summary>고정 dt 1틱 (세계 Step 전).</summary>
        ActionStatus Step(ActionContext ctx);
        string Reason { get; }
        string ReasonDetail { get; }
        string InterruptedBy { get; }
        /// <summary>이동하는 행동이면 매 틱 어그로 감지 (전투 진입은 게임이 판단 — LLM 을 기다리지 않음).</summary>
        bool DetectsEncounters { get; }
        /// <summary>적 어그로 반경에 들어갔을 때의 행동 상태 (move_to = interrupted(combat), engage = done).</summary>
        ActionStatus OnEncounter();
        /// <summary>Start 에서 바로 전투가 시작되는 경우의 적 (engage 가 이미 어그로 안일 때).</summary>
        EntityState ImmediateEncounter { get; }
    }

    public abstract class PlayActionBase : IPlayAction
    {
        public string Reason { get; protected set; }
        public string ReasonDetail { get; protected set; }
        public string InterruptedBy { get; protected set; }

        public abstract ActionStatus Start(ActionContext ctx, JObject args);
        public virtual ActionStatus Step(ActionContext ctx) => ActionStatus.Done;
        public virtual bool DetectsEncounters => false;
        public EntityState ImmediateEncounter { get; protected set; }

        public virtual ActionStatus OnEncounter()
        {
            InterruptedBy = "combat";
            return ActionStatus.Interrupted;
        }

        protected ActionStatus Fail(string reason, string detail = null)
        {
            Reason = reason;
            ReasonDetail = detail;
            return ActionStatus.Failed;
        }

        protected static string Str(JObject args, string key, bool required)
        {
            var t = args[key];
            if (t == null || t.Type == JTokenType.Null)
            {
                if (required) throw new ActionArgException("args." + key + " 필요");
                return null;
            }
            if (t.Type != JTokenType.String) throw new ActionArgException("args." + key + " 는 문자열");
            return (string)t;
        }

        /// <summary>엔티티 대상 공통 검사: 없음 → unknown_target, 지각 불가 → not_visible.</summary>
        protected EntityState Target(ActionContext ctx, string id, out ActionStatus fail)
        {
            fail = ActionStatus.Running;
            var e = ctx.World.Entity(id);
            if (e == null) { fail = Fail("unknown_target", id); return null; }
            if (!ctx.Perceivable(id)) { fail = Fail("not_visible", id); return null; }
            return e;
        }
    }

    // ------------------------------------------------------------------ move_to
    public class MoveTo : PlayActionBase
    {
        System.Collections.Generic.List<double[]> _path;
        int _next;
        double _tx, _tz, _done;
        double _elapsed;

        public override bool DetectsEncounters => true;

        /// <summary>engage 용: 정해진 점까지 arrive 반경으로 이동 시작.</summary>
        protected ActionStatus StartToward(WorldState w, double tx, double tz, double done)
        {
            _tx = tx;
            _tz = tz;
            _done = done;
            if (GridPath.Dist(w.PlayerX, w.PlayerZ, _tx, _tz) <= _done) return ActionStatus.Done;
            _path = w.Grid.Find(w.PlayerX, w.PlayerZ, _tx, _tz, Math.Max(done - 0.4, w.Data.Limits.CellSize));
            if (_path == null) return Fail("unreachable");
            _next = 0;
            w.PlayerState = "moving";
            return ActionStatus.Running;
        }

        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            var w = ctx.World;
            var lim = w.Data.Limits;
            var target = Str(args, "target", false);
            var posTok = args["pos"];
            if (target == null && (posTok == null || posTok.Type == JTokenType.Null))
                throw new ActionArgException("move_to 에는 args.target 또는 args.pos 필요");
            if (w.Modal != null) return Fail("blocked_by_modal", "ui." + w.TopModal);
            double arrivePath;
            if (target != null)
            {
                var e = Target(ctx, target, out var f);
                if (e == null) return f;
                _tx = e.X;
                _tz = e.Z;
                _done = lim.InteractRange - 0.2;
                arrivePath = lim.InteractRange - 0.6;
            }
            else
            {
                if (!(posTok is JArray a) || (a.Count != 3 && a.Count != 2)) throw new ActionArgException("args.pos 는 [x,y,z]");
                _tx = (double)a[0];
                _tz = (double)a[a.Count - 1];
                _done = 0.3;
                arrivePath = lim.CellSize;   // 목표점이 격자 모서리여도 도착 칸이 있도록 (마지막에 정확한 점을 붙인다)
                if (!w.Grid.IsFree(_tx, _tz)) return Fail("unreachable", "blocked position");
            }
            if (GridPath.Dist(w.PlayerX, w.PlayerZ, _tx, _tz) <= _done) return ActionStatus.Done;
            _path = w.Grid.Find(w.PlayerX, w.PlayerZ, _tx, _tz, arrivePath);
            if (_path == null) return Fail("unreachable", target);
            if (target == null) _path.Add(new[] { _tx, _tz });
            _next = 0;
            w.PlayerState = "moving";
            return ActionStatus.Running;
        }

        public override ActionStatus Step(ActionContext ctx)
        {
            var w = ctx.World;
            var lim = w.Data.Limits;
            double budget = lim.MoveSpeed * lim.Dt;
            while (budget > 1e-9 && _next < _path.Count)
            {
                var p = _path[_next];
                double d = GridPath.Dist(w.PlayerX, w.PlayerZ, p[0], p[1]);
                if (d <= budget)
                {
                    w.PlayerX = p[0];
                    w.PlayerZ = p[1];
                    budget -= d;
                    _next++;
                }
                else
                {
                    w.PlayerX += (p[0] - w.PlayerX) / d * budget;
                    w.PlayerZ += (p[1] - w.PlayerZ) / d * budget;
                    budget = 0;
                }
                if (GridPath.Dist(w.PlayerX, w.PlayerZ, _tx, _tz) <= _done) break;
            }
            _elapsed += lim.Dt;
            if (GridPath.Dist(w.PlayerX, w.PlayerZ, _tx, _tz) <= _done || _next >= _path.Count)
            {
                w.PlayerState = "idle";
                return ActionStatus.Done;
            }
            if (_elapsed >= lim.MaxActionSeconds)
            {
                w.PlayerState = "idle";
                return Fail("timeout");
            }
            return ActionStatus.Running;
        }
    }

    // ------------------------------------------------------------------ interact
    public sealed class Interact : PlayActionBase
    {
        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            var w = ctx.World;
            var id = Str(args, "target", true);
            var verb = Str(args, "verb", false);
            if (w.Modal != null) return Fail("blocked_by_modal", "ui." + w.TopModal);
            var e = Target(ctx, id, out var f);
            if (e == null) return f;
            if (verb == null)
            {
                if (e.Def.Actions.Length != 1) throw new ActionArgException("행동이 여러 개인 대상은 args.verb 필요: " + string.Join(",", e.Def.Actions));
                verb = e.Def.Actions[0];
            }
            if (Array.IndexOf(e.Def.Actions, verb) < 0) return Fail("not_interactable", "verb '" + verb + "' 미지원");
            // 자동 접근하지 않는다 (LLM 이 move_to 를 먼저)
            if (w.DistanceTo(e) > w.Data.Limits.InteractRange) return Fail("out_of_range", "distance " + Math.Round(w.DistanceTo(e), 1));
            switch (verb)
            {
                case "talk":
                    return w.OpenDialogue(e) ? ActionStatus.Done : Fail("invalid_state", "대화 없음");
                case "open":
                    w.Emit("opened", new JObject { ["target"] = e.Id });
                    return ActionStatus.Done;
                case "pickup":
                    return w.Pickup(e) ? ActionStatus.Done : Fail("invalid_state", "주울 수 없음");
                case "enter":
                    return w.EnterPortal(e) ? ActionStatus.Done : Fail("invalid_state", "갈 수 없음");
                default:
                    return Fail("invalid_state", "verb '" + verb + "' 아직 구현 전");
            }
        }
    }

    // ------------------------------------------------------------------ engage
    /// <summary>대상 적에게 다가가 전투 시작 (LLM 이 일부러 싸우기). 어그로 반경에 들어가면 done + 전투.</summary>
    public sealed class Engage : MoveTo
    {
        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            var w = ctx.World;
            var id = Str(args, "target", true);
            if (w.Modal != null) return Fail("blocked_by_modal", "ui." + w.TopModal);
            var e = Target(ctx, id, out var f);
            if (e == null) return f;
            if (e.Def.Role != "enemy") return Fail("not_interactable", "적이 아님");
            if (w.DistanceTo(e) <= e.Def.AggroRadius)
            {
                ImmediateEncounter = w.EnemyInAggro() ?? e;
                return ActionStatus.Done;
            }
            var st = StartToward(w, e.X, e.Z, e.Def.AggroRadius - 0.3);
            if (st == ActionStatus.Done) ImmediateEncounter = w.EnemyInAggro() ?? e;
            return st;
        }

        public override ActionStatus OnEncounter() => ActionStatus.Done;
    }

    // ------------------------------------------------------------------ use_item
    /// <summary>인벤토리 로직 직접 호출 (UI 를 거치지 않는 지름길 — 인벤토리 UI 테스트는 ui_click 으로).</summary>
    public sealed class UseItem : PlayActionBase
    {
        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            var id = Str(args, "item_id", true);
            if (ctx.World.Modal != null) return Fail("blocked_by_modal", "ui." + ctx.World.TopModal);
            var r = ctx.World.UseItem(id);
            if (r == null) return ActionStatus.Done;
            return Fail(r, r == "invalid_state" ? (ctx.World.Data.Item(id)?.Usable ?? false ? "체력이 가득 참" : "사용할 수 없는 아이템") : id);
        }
    }

    // ------------------------------------------------------------------ wait
    public sealed class Wait : PlayActionBase
    {
        double _seconds, _elapsed;
        string _until;
        bool _hit;
        WorldState _w;

        public override ActionStatus Start(ActionContext ctx, JObject args)
        {
            var lim = ctx.World.Data.Limits;
            var s = args["seconds"];
            _until = Str(args, "until", false);
            if ((s == null || s.Type == JTokenType.Null) && _until == null) throw new ActionArgException("wait 에는 args.seconds 또는 args.until 필요");
            if (s != null && s.Type != JTokenType.Null)
            {
                if (s.Type != JTokenType.Integer && s.Type != JTokenType.Float) throw new ActionArgException("args.seconds 는 숫자");
                _seconds = (double)s;
                if (_seconds < 0 || _seconds > lim.MaxActionSeconds) throw new ActionArgException("args.seconds 는 0~" + lim.MaxActionSeconds);
            }
            else _seconds = double.PositiveInfinity;
            _w = ctx.World;
            if (_until != null) _w.OnEvent += OnEv;
            return _seconds == 0 ? Finish(ActionStatus.Done) : ActionStatus.Running;
        }

        void OnEv(WorldEvent e) { if (e.Kind == _until) _hit = true; }

        ActionStatus Finish(ActionStatus s)
        {
            if (_until != null) _w.OnEvent -= OnEv;
            return s;
        }

        public override ActionStatus Step(ActionContext ctx)
        {
            _elapsed += ctx.World.Data.Limits.Dt;
            if (_hit || _elapsed >= _seconds - 1e-9) return Finish(ActionStatus.Done);
            if (_elapsed >= ctx.World.Data.Limits.MaxActionSeconds) { Finish(ActionStatus.Failed); return Fail("timeout"); }
            return ActionStatus.Running;
        }
    }

    // ------------------------------------------------------------------ 실행기
    /// <summary>행동 1개를 끝까지 고정 dt 로 진행. 세계 시간은 여기서만 흐른다.</summary>
    public sealed class ActionRunner
    {
        public IPlayAction Action { get; private set; }
        public ActionStatus Status { get; private set; }
        public double GameSeconds { get; private set; }
        /// <summary>이 행동 중 시작된 전투의 적 (없으면 null). 세션이 전투를 진행한 뒤 결과를 보낸다.</summary>
        public EntityState Encounter { get; private set; }
        readonly ActionContext _ctx;
        readonly long _step0;

        public ActionRunner(ActionContext ctx, IPlayAction action, JObject args)
        {
            _ctx = ctx;
            Action = action;
            _step0 = ctx.World.Steps;
            Status = action.Start(ctx, args);
            if (action.ImmediateEncounter != null) Encounter = action.ImmediateEncounter;
        }

        /// <summary>전투가 세계 시간을 진행한 뒤 경과 시간 갱신.</summary>
        public void Refresh() => GameSeconds = (_ctx.World.Steps - _step0) * _ctx.World.Data.Limits.Dt;

        public bool Finished => Status != ActionStatus.Running;

        /// <summary>1틱. 끝났으면 false.</summary>
        public bool Tick()
        {
            if (Finished) return false;
            Status = Action.Step(_ctx);
            _ctx.World.Step();
            GameSeconds = (_ctx.World.Steps - _step0) * _ctx.World.Data.Limits.Dt;
            if (Action.DetectsEncounters && Status != ActionStatus.Failed)
            {
                var enemy = _ctx.World.EnemyInAggro();
                if (enemy != null)
                {
                    _ctx.World.PlayerState = "idle";
                    Encounter = enemy;
                    Status = Action.OnEncounter();
                }
            }
            return !Finished;
        }
    }
}
