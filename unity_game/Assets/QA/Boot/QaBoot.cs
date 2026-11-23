// QA 서버 진입점.
//
// 1) 빌드 + 명령행:  QaArena.exe -batchmode -nographics -qaPort 7777 [-qaHost 127.0.0.1]
//    → batchmode 면 메인 스레드에서 블로킹 (CPU 사용 없음). Player.log 에 "LISTENING 7777".
// 2) 빌드 + 창 모드:  QaArena.exe -qaPort 7777   → 백그라운드 스레드 + 화면에 상태 표시.
// 3) 에디터 Play:     메뉴 QA > Play Mode Server 를 켜고 Play → 백그라운드 스레드, Play 종료 시 서버도 종료.
//
// 정의서는 메인 스레드에서 한 번 읽고(Resources), 서버 스레드는 Unity API 를 쓰지 않는다.
using Btqa.Game;
using System;
using System.Collections.Generic;
using System.Threading;
using Qa.Data;
using Qa.Protocol;
using Qa.Sim;
using UnityEngine;

namespace Qa.Boot
{
    public static class QaBoot
    {
        public const string EditorPrefEnabled = "Qa.PlayModeServer.Enabled";
        public const string EditorPrefPort = "Qa.PlayModeServer.Port";
        public const int DefaultEditorPort = 7777;

        /// <summary>실행 중인 서버 (표시용). 판 로직은 이 값을 쓰지 않는다.</summary>
        public static QaServer Server { get; private set; }
        public static SpecRepository Repo { get; private set; }
        /// <summary>시작 실패 사유 (표시용).</summary>
        public static string Error { get; private set; }
        /// <summary>최근 학습 판 기록 (화면 모드에서만, 헤드리스는 null).</summary>
        public static EpisodeRecorder Recorder { get; private set; }

        static Thread _thread;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            // 에디터에서 도메인 리로드를 끈 경우(Enter Play Mode Options)에도 이전 Play 의 상태가 남지 않게
            Server = null;
            Repo = null;
            Error = null;
            Recorder = null;
            _thread = null;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void OnLoad()
        {
            if (!ResolveEndpoint(out var host, out var port)) return;   // QA 서버 모드 아님
            if (Qa.Play.Server.PlayArgs.Enabled)
            {
                // 플레이 모드 (-qaPlay): 밸런스 서버를 열지 않고 플레이 서버만 (../docs/PLAY_PROTOCOL.md)
                try { Repo = new SpecRepository(new ResourcesSpecSource("QaData")); }
                catch (Exception ex) { Fail("게임 데이터 검증 실패: " + ex.Message); return; }
                Qa.Play.Server.PlayBoot.Start(host, port, Repo, Out, Log, Fail);
                return;
            }

            Application.runInBackground = true;   // 에디터·창 모드에서 포커스를 잃어도 학습이 멈추지 않게
            if (Application.isBatchMode)
            {
                Application.targetFrameRate = 1;
                QualitySettings.vSyncCount = 0;
                AudioListener.pause = true;
            }

            try
            {
                Repo = new SpecRepository(new ResourcesSpecSource("QaData"));
            }
            catch (Exception ex)
            {
                Fail("게임 데이터 검증 실패: " + ex.Message);
                return;
            }

            var cfg = new SimConfig();
            // 화면이 있는 모드에서만 최근 판을 기록 (뷰어 재생용). 헤드리스는 기록 비용 없음.
            Recorder = Application.isBatchMode ? null : new EpisodeRecorder();
            // BT-QA Game SDK: 서버·세션·요청 검증은 SDK, 판 실행·정의서는 QaArenaHost. 판 사이 상태 없음 → 연결 간 공유해도 안전
            var gameHost = new QaArenaHost(Repo, cfg, Recorder);
            gameHost.Declare().Validate();   // 기동 시 정의서 규칙 검사 (학습 대상 = 블록 가중치뿐)
            var server = new QaServer(host, port, () => new QaSession(gameHost), Log);
            try
            {
                server.Start();
            }
            catch (Exception ex)
            {
                Fail("포트 " + host + ":" + port + " 열기 실패: " + ex.Message);
                return;
            }
            Server = server;

            Out("LISTENING " + server.Port);
            Log("QA 서버 " + Repo.GameName + " " + Repo.GameVersion + " classes=[" + string.Join(",", Repo.ClassNames) + "]");

            if (Application.isBatchMode)
            {
                // 헤드리스: 메인 스레드에서 블로킹. 프레임 루프를 돌리지 않으므로 CPU 를 쓰지 않는다.
                server.Serve();
                return;
            }

            // 에디터 Play / 창 모드: 화면이 멈추지 않도록 백그라운드 스레드
            _thread = new Thread(server.Serve) { IsBackground = true, Name = "QaServer:" + server.Port };
            _thread.Start();
            Application.quitting += StopServer;
#if UNITY_EDITOR
            UnityEditor.EditorApplication.playModeStateChanged += OnPlayModeChanged;
#endif
        }

#if UNITY_EDITOR
        static void OnPlayModeChanged(UnityEditor.PlayModeStateChange s)
        {
            if (s == UnityEditor.PlayModeStateChange.ExitingPlayMode)
            {
                UnityEditor.EditorApplication.playModeStateChanged -= OnPlayModeChanged;
                StopServer();
            }
        }
#endif

        static void StopServer()
        {
            Application.quitting -= StopServer;
            var s = Server;
            if (s == null) return;
            s.Stop();
            _thread?.Join(2000);
            Log("QA 서버 종료 (포트 " + s.Port + ")");
            Server = null;
        }

        /// <summary>명령행 -qaPort 우선, 없으면 에디터 설정(QA > Play Mode Server).</summary>
        static bool ResolveEndpoint(out string host, out int port)
        {
            var args = Environment.GetCommandLineArgs();
            host = ArgValue(args, "-qaHost") ?? "127.0.0.1";
            port = 0;
            var portArg = ArgValue(args, "-qaPort");
            if (portArg != null)
            {
                if (int.TryParse(portArg, out port) && port >= 0 && port <= 65535) return true;
                Fail("잘못된 -qaPort: " + portArg);
                return false;
            }
#if UNITY_EDITOR
            if (UnityEditor.EditorPrefs.GetBool(EditorPrefEnabled, false))
            {
                port = UnityEditor.EditorPrefs.GetInt(EditorPrefPort, DefaultEditorPort);
                return true;
            }
#endif
            return false;
        }

        static string ArgValue(IList<string> args, string name)
        {
            for (int i = 0; i < args.Count - 1; i++)
                if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase)) return args[i + 1];
            return null;
        }

        static void Out(string line)
        {
            // stdout (사람 확인용) + Player.log / 에디터 Console
            try { Console.Out.WriteLine(line); Console.Out.Flush(); } catch { /* stdout 없음 */ }
            Debug.Log("[QA] " + line);
        }

        static void Log(string line) => Debug.Log("[QA] " + line);

        static void Fail(string message)
        {
            Error = message;
            try { Console.Error.WriteLine("ERROR " + message); Console.Error.Flush(); } catch { }
            Debug.LogError("[QA] " + message);
            if (Application.isBatchMode) Application.Quit(1);
        }
    }

    /// <summary>Resources/QaData/... 의 TextAsset(JSON). 메인 스레드에서만 호출.</summary>
    public sealed class ResourcesSpecSource : ISpecSource
    {
        readonly string _root;
        public ResourcesSpecSource(string root) { _root = root; }

        public string Read(string path)
        {
            var asset = Resources.Load<TextAsset>(_root + "/" + path);
            return asset == null ? null : asset.text;
        }

        public IEnumerable<string> List(string folder)
        {
            var names = new List<string>();
            foreach (var a in Resources.LoadAll<TextAsset>(_root + "/" + folder)) names.Add(a.name);
            return names;
        }
    }
}
