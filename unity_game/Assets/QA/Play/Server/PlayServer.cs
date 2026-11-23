// 플레이 모드 TCP 서버 (PLAY_PROTOCOL 2장). 전송 규칙은 밸런스 서버와 같다 (JSON Lines, 연결 1개, 오류 후 연결 유지).
// 소켓 읽기는 이 스레드, 메시지 처리·송신은 메인 스레드(PlaySession.Pump) — Unity API(uGUI·EventSystem)가 메인 스레드 전용이라서.
// 이 스레드는 받은 줄을 계속 Inbox 에 넣는다 (전투 중 trigger_response 를 받아야 하므로 요청 완료를 기다리지 않음).
// 송신은 메인 스레드만 한다 (JSON 파싱 오류도 Inbox 로 넘겨 메인 스레드가 보냄 → 쓰기 경합 없음).
using Btqa.Game;
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using Newtonsoft.Json.Linq;
using Qa.Protocol;

namespace Qa.Play.Server
{
    public interface IPlayChannel
    {
        /// <summary>연결이 끊겼으면 IOException.</summary>
        void Send(JObject msg);
    }

    public sealed class PlayRequest
    {
        public JObject Msg;              // null = 아래 둘 중 하나
        public JObject PreError;         // JSON 파싱 오류 → 그대로 보낼 error
        public bool Disconnected;        // 연결 종료 알림
        public IPlayChannel Channel;
        public long Connection;
        readonly ManualResetEventSlim _done = new ManualResetEventSlim(false);
        public bool CloseAfter;   // bye 등
        public void Complete() => _done.Set();
        public void WaitDone() => _done.Wait();

        public string Type => Msg?["type"]?.Type == JTokenType.String ? (string)Msg["type"] : null;
    }

    public sealed class PlayServer
    {
        readonly TcpListener _listener;
        readonly Action<string> _log;
        volatile bool _stopping;
        TcpClient _current;
        long _connections;

        public readonly BlockingCollection<PlayRequest> Inbox = new BlockingCollection<PlayRequest>(new ConcurrentQueue<PlayRequest>());
        public int Port => ((IPEndPoint)_listener.LocalEndpoint).Port;

        public PlayServer(string host, int port, Action<string> log)
        {
            _log = log ?? (_ => { });
            var addr = host == "localhost" ? IPAddress.Loopback : IPAddress.Parse(host);
            _listener = new TcpListener(addr, port);
        }

        public void Start() => _listener.Start(5);

        public void Stop()
        {
            _stopping = true;
            try { _listener.Stop(); } catch { }
            try { _current?.Close(); } catch { }
        }

        public void Serve()
        {
            while (!_stopping)
            {
                TcpClient client;
                try { client = _listener.AcceptTcpClient(); }
                catch (Exception ex) when (ex is SocketException || ex is ObjectDisposedException || ex is InvalidOperationException)
                {
                    if (_stopping) return;
                    _log("accept 실패: " + ex.Message);
                    continue;
                }
                _current = client;
                long conn = Interlocked.Increment(ref _connections);
                try { HandleClient(client, conn); }
                catch (Exception ex) { if (!_stopping) _log("플레이 연결 처리 중 오류: " + ex); }
                finally
                {
                    _current = null;
                    try { client.Close(); } catch { }
                }
            }
        }

        void HandleClient(TcpClient client, long conn)
        {
            client.NoDelay = true;
            using (var stream = client.GetStream())
            {
                var utf8 = new UTF8Encoding(false);
                var reader = new StreamReader(stream, utf8, false, 1 << 16, true);
                var ch = new Channel(new StreamWriter(stream, utf8, 1 << 16, true) { AutoFlush = false, NewLine = "\n" });
                try
                {
                    while (!_stopping)
                    {
                        string line;
                        try { line = reader.ReadLine(); }
                        catch (Exception ex) when (ex is IOException || ex is ObjectDisposedException) { return; }
                        if (line == null) return;
                        if (line.Trim().Length == 0) continue;
                        var req = new PlayRequest { Channel = ch, Connection = conn };
                        try { req.Msg = JsonLine.Decode(line); }
                        catch (ProtocolException ex) { req.PreError = P.MakeError(ex.Code, ex.Message); }
                        Inbox.Add(req);
                        if (req.Type == PP.Bye)
                        {
                            req.WaitDone();   // 메인 스레드가 정리한 뒤 닫는다
                            return;
                        }
                    }
                }
                finally
                {
                    // 메인 스레드가 이 연결의 진행 중 전투·행동을 정리하고, 끝날 때까지 소켓을 닫지 않는다
                    var bye = new PlayRequest { Disconnected = true, Channel = ch, Connection = conn };
                    Inbox.Add(bye);
                    bye.WaitDone();
                }
            }
        }

        sealed class Channel : IPlayChannel
        {
            readonly StreamWriter _w;
            public Channel(StreamWriter w) { _w = w; }

            public void Send(JObject msg)
            {
                try
                {
                    _w.Write(JsonLine.Encode(msg));
                    _w.Write('\n');
                    _w.Flush();
                }
                catch (ObjectDisposedException ex) { throw new IOException("연결 닫힘", ex); }
            }
        }
    }
}
