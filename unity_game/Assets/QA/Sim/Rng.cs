// 판 전용 난수 (xoshiro256**, SplitMix64 시드 확장).
// 런타임(Mono/.NET) 버전과 무관하게 같은 seed → 같은 수열. 판마다 새로 만들고 판의 모든 난수는 여기서만 뽑는다.
namespace Qa.Sim
{
    public sealed class Rng
    {
        ulong _s0, _s1, _s2, _s3;

        public Rng(long seed)
        {
            unchecked
            {
                ulong x = (ulong)seed;
                _s0 = SplitMix(ref x);
                _s1 = SplitMix(ref x);
                _s2 = SplitMix(ref x);
                _s3 = SplitMix(ref x);
            }
        }

        Rng() { }

        /// <summary>같은 상태의 복사본 (플레이 모드 snapshot 용). 이후 두 수열은 독립.</summary>
        public Rng Clone() => new Rng { _s0 = _s0, _s1 = _s1, _s2 = _s2, _s3 = _s3 };

        static ulong SplitMix(ref ulong x)
        {
            unchecked
            {
                x += 0x9E3779B97F4A7C15UL;
                ulong z = x;
                z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
                z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
                return z ^ (z >> 31);
            }
        }

        static ulong Rotl(ulong x, int k) => (x << k) | (x >> (64 - k));

        public ulong NextU64()
        {
            unchecked
            {
                ulong result = Rotl(_s1 * 5, 7) * 9;
                ulong t = _s1 << 17;
                _s2 ^= _s0;
                _s3 ^= _s1;
                _s1 ^= _s2;
                _s0 ^= _s3;
                _s2 ^= t;
                _s3 = Rotl(_s3, 45);
                return result;
            }
        }

        /// <summary>[0, 1)</summary>
        public double NextDouble() => (NextU64() >> 11) * (1.0 / 9007199254740992.0);

        /// <summary>[lo, hi)</summary>
        public double Uniform(double lo, double hi) => lo + (hi - lo) * NextDouble();
    }
}
