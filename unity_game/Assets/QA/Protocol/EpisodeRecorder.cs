// 최근에 학습 쪽이 돌린 판의 재생 정보 (요청 + 트리거 응답 + 결과).
// 화면 뷰어가 같은 seed·params·트리거 응답으로 다시 돌려 그 판을 그대로 재현한다 (결정성).
// 헤드리스(batchmode)에서는 기록하지 않는다 (QaBoot 이 recorder 를 넘기지 않음).
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace Qa.Protocol
{
    public sealed class EpisodeRecord
    {
        public JObject Request;                       // run_episode 메시지
        public readonly List<JObject> TriggerParams = new List<JObject>();   // index 순서, null 가능
        public JObject Result;                        // episode_result.result
        public long Serial;                           // 몇 번째 기록인지
    }

    public sealed class EpisodeRecorder
    {
        readonly object _lock = new object();
        EpisodeRecord _last;
        long _serial;

        /// <summary>마지막으로 끝까지 돈 판 (없으면 null). 스레드 안전.</summary>
        public EpisodeRecord Last
        {
            get { lock (_lock) return _last; }
        }

        internal void Commit(EpisodeRecord r)
        {
            lock (_lock)
            {
                r.Serial = ++_serial;
                _last = r;
            }
        }
    }
}
