// 시뮬레이션 공통 설정 (game_sim/sim/config.py 대응).
namespace Qa.Sim
{
    public sealed class SimConfig
    {
        public double Dt = 0.3;              // 1스텝 = BT 결정 주기 300ms
        public double TimeLimit = 600.0;     // 시간 초과(중도절단)
        public int MaxDeaths = 3;            // 이 횟수를 넘겨 사망하면 실패 (부활 3회 허용)
        public double ReviveDelay = 25.0;    // 0.4.0: 15 → 25 (부활을 회복 수단으로 쓰지 못하게)
        public double ReviveHpRatio = 0.5;   // 0.4.0: 부활 시 최대 체력의 50%
        public double StartDistance = 8.0;
        public double ReviveDistance = 10.0;
        public double MinDistance = 1.0;
        public double MaxDistance = 30.0;
        public double StallSeconds = 90.0;   // 이 시간 동안 보스에게 피해가 없으면 무효 판
        public double CritMult = 1.5;
        public double Gcd = 0.9;
        public bool RecordEvents = false;

        public SimConfig WithRecordEvents(bool on)
        {
            var c = (SimConfig)MemberwiseClone();
            c.RecordEvents = on;
            return c;
        }
    }
}
