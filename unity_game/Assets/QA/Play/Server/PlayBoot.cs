// 플레이 모드 진입점: QaArena.exe -qaPlay -qaPort 7800 [-qaPlaySeed 1] [-qaPlaySpeed 1] [-qaPlayOmniscient] [-qaNoPilotNotes]
// -qaPlay 가 없으면 아무것도 하지 않는다 (밸런스 QA 모드는 QaBoot 가 그대로 처리).
using Btqa.Game;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;
using Qa.Data;
using Qa.Play.World;
using UnityEngine;

namespace Qa.Play.Server
{
    public static class PlayArgs
    {
        public static bool Enabled => Has("-qaPlay");

        public static bool Has(string name)
        {
            foreach (var a in Environment.GetCommandLineArgs())
                if (string.Equals(a, name, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        public static string Value(string name)
        {
            IList<string> args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Count - 1; i++)
                if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase)) return args[i + 1];
            return null;
        }
    }

    /// <summary>메인 스레드 펌프 (매 프레임 PlaySession.Pump).</summary>
    public sealed class PlayDriver : MonoBehaviour
    {
        public PlaySession Session;
        void Update() => Session?.Pump(Time.unscaledDeltaTime);   // 실시간은 화면 진행 속도에만 쓴다 (로직은 dt·틱 수)
    }

    public static class PlayBoot
    {
        public static PlayServer Server { get; private set; }
        /// <summary>화면 생성 (Presentation 쪽 PlayView 가 등록). 로직은 화면 구현을 직접 참조하지 않는다.</summary>
        public static Func<Func<WorldState>, Perception.IPlayScene> SceneFactory;
        static Thread _thread;

        /// <summary>QaBoot 가 -qaPlay 일 때 부른다.</summary>
        public static void Start(string host, int port, SpecRepository repo, Action<string> outLine, Action<string> log, Action<string> fail)
        {
            var sceneFactory = SceneFactory;
            if (sceneFactory == null) { fail("플레이 화면 팩토리 없음 (PlayView 미등록)"); return; }
            var opt = new PlayOptions
            {
                Omniscient = PlayArgs.Has("-qaPlayOmniscient"),
                Instant = Application.isBatchMode,
            };
            var seedArg = PlayArgs.Value("-qaPlaySeed");
            if (seedArg != null && long.TryParse(seedArg, out var sd)) opt.DefaultSeed = sd;
            var spArg = PlayArgs.Value("-qaPlaySpeed");
            if (spArg != null && double.TryParse(spArg, NumberStyles.Float, CultureInfo.InvariantCulture, out var sp)) opt.Speed = sp;
            var csArg = PlayArgs.Value("-qaPlayCombatSpeed");
            if (csArg != null && double.TryParse(csArg, NumberStyles.Float, CultureInfo.InvariantCulture, out var cs)) opt.CombatSpeed = cs;

            PlayData data;
            try
            {
                var w = Resources.Load<TextAsset>("QaData/play/world");
                var d = Resources.Load<TextAsset>("QaData/play/dialogues");
                var it = Resources.Load<TextAsset>("QaData/play/items");
                var qs = Resources.Load<TextAsset>("QaData/play/quests");
                if (w == null || d == null || it == null || qs == null) throw new Exception("Resources/QaData/play/{world,dialogues,items,quests}.json 중 없는 파일");
                data = PlayData.Parse(w.text, d.text, it.text, qs.text);
                foreach (var sc in data.EnemyScenarios())
                    if (!repo.HasScenario(sc)) throw new Exception("적 엔티티의 scenario '" + sc + "' 가 scenarios.json 에 없음");
            }
            catch (Exception ex)
            {
                fail("플레이 데이터 검증 실패: " + ex.Message);
                return;
            }

            Application.runInBackground = true;
            Application.targetFrameRate = 60;
            QualitySettings.vSyncCount = 0;
            if (!Application.isBatchMode) Screen.SetResolution(1280, 720, FullScreenMode.Windowed);

            PlaySession session = null;
            var scene = sceneFactory(() => session?.World);
            var server = new PlayServer(host, port, log);
            try { server.Start(); }
            catch (Exception ex)
            {
                fail("포트 " + host + ":" + port + " 열기 실패: " + ex.Message);
                return;
            }
            Server = server;
            var logView = scene as IActionLogView;
            // pilot_note 표시: 창 모드만 (헤드리스는 로그만, -qaNoPilotNotes 는 녹화용으로 숨김)
            var noteView = Application.isBatchMode || PlayArgs.Has("-qaNoPilotNotes") ? null : scene as IPilotNoteView;
            Action<string, string> onNote = null;
            if (noteView != null) onNote = (k, t) => noteView.ShowPilotNote(k, t);
            session = new PlaySession(server, repo, data, scene, opt, s => logView?.AddLog(s), new Qa.Sim.SimConfig(), onNote);   // 밸런스 모드(QaBoot)와 같은 기본 설정
            var go = new GameObject("PlayDriver");
            UnityEngine.Object.DontDestroyOnLoad(go);
            go.AddComponent<PlayDriver>().Session = session;

            _thread = new Thread(server.Serve) { IsBackground = true, Name = "PlayServer:" + server.Port };
            _thread.Start();
            Application.quitting += () => server.Stop();
            outLine("LISTENING " + server.Port);
            log("플레이 서버 " + repo.GameName + " " + repo.GameVersion + " protocol play " + PP.ProtocolVersion +
                " speed=" + (opt.Instant ? "instant" : opt.Speed.ToString(CultureInfo.InvariantCulture)) + " omniscient=" + opt.Omniscient);
        }
    }

    /// <summary>관람용 행동 로그 표시 (선택).</summary>
    public interface IActionLogView
    {
        void AddLog(string line);
    }

    /// <summary>플레이어(LLM) 생각 메모 표시 (pilot_note, v0.3). 입력·관찰에 영향을 주면 안 된다.</summary>
    public interface IPilotNoteView
    {
        void ShowPilotNote(string kind, string text);
    }
}
