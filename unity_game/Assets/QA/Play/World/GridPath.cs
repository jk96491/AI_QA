// 지역 격자 길찾기 (A*, 8방향, 모서리 끼어들기 금지 + 시야선 경로 단순화). 순수 C#, 결정적.
// NavMesh 대신 쓰는 이유: 고정 dt 수동 진행·헤드리스·결정성을 보장하기 쉽다. 관찰되는 의미(done/unreachable)는 같다.
using System;
using System.Collections.Generic;

namespace Qa.Play.World
{
    public sealed class GridPath
    {
        readonly double _minX, _minZ, _cell;
        readonly int _w, _h;
        readonly bool[] _blocked;

        public GridPath(ZoneDef zone, double cell, double inflate)
        {
            _minX = zone.MinX;
            _minZ = zone.MinZ;
            _cell = cell;
            _w = (int)Math.Ceiling((zone.MaxX - zone.MinX) / cell);
            _h = (int)Math.Ceiling((zone.MaxZ - zone.MinZ) / cell);
            _blocked = new bool[_w * _h];
            for (int j = 0; j < _h; j++)
                for (int i = 0; i < _w; i++)
                {
                    double x = CenterX(i), z = CenterZ(j);
                    // 지역 경계 가장자리도 막음
                    bool b = x < zone.MinX + inflate || x > zone.MaxX - inflate || z < zone.MinZ + inflate || z > zone.MaxZ - inflate;
                    foreach (var o in zone.Obstacles)
                    {
                        if (b) break;
                        b = Math.Abs(x - o.X) <= o.SizeX / 2 + inflate && Math.Abs(z - o.Z) <= o.SizeZ / 2 + inflate;
                    }
                    _blocked[j * _w + i] = b;
                }
        }

        double CenterX(int i) => _minX + (i + 0.5) * _cell;
        double CenterZ(int j) => _minZ + (j + 0.5) * _cell;
        int CellX(double x) => (int)Math.Floor((x - _minX) / _cell);
        int CellZ(double z) => (int)Math.Floor((z - _minZ) / _cell);
        bool InGrid(int i, int j) => i >= 0 && j >= 0 && i < _w && j < _h;
        bool Free(int i, int j) => InGrid(i, j) && !_blocked[j * _w + i];

        public bool IsFree(double x, double z) => Free(CellX(x), CellZ(z));

        /// <summary>
        /// (sx,sz) 에서 (tx,tz) 까지 arrive 반경 안의 칸으로 가는 경로점 목록 (시작점 제외, 마지막 = 도착 칸 중심).
        /// 이미 arrive 안이면 빈 목록. 길 없음 → null.
        /// </summary>
        public List<double[]> Find(double sx, double sz, double tx, double tz, double arrive)
        {
            if (Dist(sx, sz, tx, tz) <= arrive) return new List<double[]>();
            int si = CellX(sx), sj = CellZ(sz);
            if (!InGrid(si, sj)) return null;
            int n = _w * _h;
            var g = new double[n];
            var parent = new int[n];
            var closed = new bool[n];
            for (int k = 0; k < n; k++) { g[k] = double.PositiveInfinity; parent[k] = -1; }
            int start = sj * _w + si;
            g[start] = 0;
            var open = new MinHeap();
            open.Push(H(si, sj, tx, tz, arrive), start);
            int goal = -1;
            while (open.Count > 0)
            {
                int cur = open.Pop();
                if (closed[cur]) continue;
                closed[cur] = true;
                int ci = cur % _w, cj = cur / _w;
                if (!_blocked[cur] && Dist(CenterX(ci), CenterZ(cj), tx, tz) <= arrive) { goal = cur; break; }
                for (int dj = -1; dj <= 1; dj++)
                    for (int di = -1; di <= 1; di++)
                    {
                        if (di == 0 && dj == 0) continue;
                        int ni = ci + di, nj = cj + dj;
                        if (!Free(ni, nj)) continue;
                        if (di != 0 && dj != 0 && (!Free(ci + di, cj) || !Free(ci, cj + dj))) continue;   // 모서리 끼어들기 금지
                        int nk = nj * _w + ni;
                        if (closed[nk]) continue;
                        double ng = g[cur] + (di != 0 && dj != 0 ? 1.4142135623730951 : 1.0) * _cell;
                        if (ng < g[nk])
                        {
                            g[nk] = ng;
                            parent[nk] = cur;
                            open.Push(ng + H(ni, nj, tx, tz, arrive), nk);
                        }
                    }
            }
            if (goal < 0) return null;

            var cells = new List<int>();
            for (int k = goal; k != -1 && k != start; k = parent[k]) cells.Add(k);
            cells.Reverse();
            // 시야선 단순화: 현재 기준점에서 직선으로 갈 수 있는 가장 먼 경로점까지 건너뛴다
            var pts = new List<double[]>();
            double ax = sx, az = sz;
            int idx = 0;
            while (idx < cells.Count)
            {
                int far = idx;
                for (int k = cells.Count - 1; k > idx; k--)
                {
                    if (LineFree(ax, az, CenterX(cells[k] % _w), CenterZ(cells[k] / _w))) { far = k; break; }
                }
                double px = CenterX(cells[far] % _w), pz = CenterZ(cells[far] / _w);
                pts.Add(new[] { px, pz });
                ax = px; az = pz;
                idx = far + 1;
            }
            return pts;
        }

        bool LineFree(double ax, double az, double bx, double bz)
        {
            double d = Dist(ax, az, bx, bz);
            int steps = Math.Max(1, (int)Math.Ceiling(d / (_cell * 0.25)));
            for (int s = 1; s <= steps; s++)
            {
                double t = (double)s / steps;
                if (!IsFree(ax + (bx - ax) * t, az + (bz - az) * t)) return false;
            }
            return true;
        }

        double H(int i, int j, double tx, double tz, double arrive) => Math.Max(0, Dist(CenterX(i), CenterZ(j), tx, tz) - arrive);

        public static double Dist(double ax, double az, double bx, double bz)
        {
            double dx = ax - bx, dz = az - bz;
            return Math.Sqrt(dx * dx + dz * dz);
        }

        /// <summary>(우선순위, 삽입 순번) 순 이진 힙 — 동점 처리까지 결정적.</summary>
        sealed class MinHeap
        {
            readonly List<(double f, long seq, int v)> _a = new List<(double, long, int)>();
            long _seq;
            public int Count => _a.Count;

            static bool Less((double f, long seq, int v) x, (double f, long seq, int v) y) => x.f < y.f || (x.f == y.f && x.seq < y.seq);

            public void Push(double f, int v)
            {
                _a.Add((f, _seq++, v));
                int i = _a.Count - 1;
                while (i > 0)
                {
                    int p = (i - 1) / 2;
                    if (!Less(_a[i], _a[p])) break;
                    (_a[i], _a[p]) = (_a[p], _a[i]);
                    i = p;
                }
            }

            public int Pop()
            {
                var top = _a[0].v;
                var last = _a[_a.Count - 1];
                _a.RemoveAt(_a.Count - 1);
                if (_a.Count > 0)
                {
                    _a[0] = last;
                    int i = 0;
                    while (true)
                    {
                        int l = 2 * i + 1, r = l + 1, m = i;
                        if (l < _a.Count && Less(_a[l], _a[m])) m = l;
                        if (r < _a.Count && Less(_a[r], _a[m])) m = r;
                        if (m == i) break;
                        (_a[i], _a[m]) = (_a[m], _a[i]);
                        i = m;
                    }
                }
                return top;
            }
        }
    }
}
