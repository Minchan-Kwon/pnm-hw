'''
Script for the design space exploration of the SiLU unit

We explore five axes of design choices.
NSEG:   Number of linear segments for [0, 8)
XFB:    Fraction bits of |x|, where |x| is represented as unsigned Q3.XFB
OW:     The offset bits of |x|'s position inside a segment (None = keep all)
HTANFB: The fraction bits of htan, which is the table's output
GB:     Guard bits: extra fraction bits on the slope and intercept, shifted out at the end

Datapath (bit-accurate model; RTL must match it exactly):
  scale s = m * 2^E,  m = 1.mantissa (m_int = 1024 + mantissa),  E = exp_field - 15
  bypass:  s >= 1 -> ReLU(q)  |  s < 2^-13 -> round(q/2)  |  invalid -> 0 (spec TBD)
  active (E = -13 .. -1):
    P      = |q| * m_int                          8 x 11-bit integer multiply
    x_abs  = round(P * 2^(E - 10 + XFB))          |x| in unsigned Q3.XFB; x_abs >= 8.0 -> htan = 0.5
    seg    = x_abs >> SEGLSB                      uniform segments over [0, 8): index = top bits of x_abs
    off    = low SEGLSB bits of x_abs, truncated to its top OW bits
    htan   = (SLOPE[seg] * off + ICPT[seg]) >> GB     htan ~= sigmoid(|x|) - 0.5, HTANFB fraction bits
    y      = clamp((|q| * htan + q * 2^(HTANFB-1) + 2^(HTANFB-1)) >> HTANFB)   = round(q/2 + |q| * htan)

Error at the output is |q| * (error of htan) <= 128 * (error of htan), independent of the scale.
'''
import os, time, csv
import numpy as np
from itertools import product

HERE = os.path.dirname(os.path.abspath(__file__))

def load_vectors(golden_dir = HERE):
    '''
    Load all active scale pairs (q, scale) with their golden outputs as flat arrays
    '''
    gp, bp = os.path.join(golden_dir, "golden.npy"), os.path.join(golden_dir, "scale_type.npy")
    gold, band = np.load(gp), np.load(bp)
    act = np.where(band == 2)[0].astype(np.int64)  # scale patterns in the active type
    Q = np.arange(-128, 128, dtype=np.int64)
    V = dict(q=np.tile(Q, len(act)),
             sb=np.repeat(act, 256),               # scale bit
             gold=gold[act].astype(np.int64).reshape(-1))
    V["E"] = ((V["sb"] >> 10) & 31) - 15           # exponent - bias
    V["m"] = 1024 + (V["sb"] & 1023)               # mantissa with hidden 1
    return V

def sbits(v):
    '''
    Smallest two's-complement width that holds every value in v
    '''
    lo, hi, w = int(np.min(v)), int(np.max(v)), 1
    while not (-(1 << (w - 1)) <= lo and hi < (1 << (w - 1))):
        w += 1
    return w

def htan_real(x):
    return 0.5 * np.tanh(x / 2.0)  # sigmoid(x) - 0.5

class SiLU_UNIT:
    def __init__(self, V, XFB=7, NSEG=16, OW=None, HTANFB=11, GB=4, fit="search", search_cap=40000, seed=0):
        assert (8 << XFB) % NSEG == 0
        self.V, self.XFB, self.NSEG, self.OW, self.HTANFB, self.GB = V, XFB, NSEG, OW, HTANFB, GB
        self.XMAX = 8 << XFB
        self.W = self.XMAX // NSEG                        # segment width (in steps of |x|)
        self.SEGLSB = int(np.log2(self.W))                # segment index starts at this bit
        self.DROP = 0 if OW is None else max(0, self.SEGLSB - OW)
        self._front_end()
        self.SLOPE, self.ICPT = self._fit_ls()
        if fit == "search":
            self._search(cap=search_cap, seed=seed)

    def _front_end(self):
        V = self.V
        self.abs_q = np.abs(V["q"])
        P = self.abs_q * V["m"]
        sh = V["E"] - 10 + self.XFB
        left = P << np.clip(sh, 0, 40)
        rs = np.clip(-sh, 0, 62)
        right = (P + np.where(rs > 0, np.int64(1) << np.clip(rs - 1, 0, 61), 0)) >> rs
        x_abs = np.minimum(np.where(sh >= 0, left, right), self.XMAX)
        self.in_range = x_abs < self.XMAX
        self.seg = np.where(self.in_range, x_abs >> self.SEGLSB, 0)
        self.off = (x_abs & (self.W - 1)) >> self.DROP

    def _fit_ls(self):
        sc = 2.0 ** (self.HTANFB + self.GB)
        SLOPE, ICPT = np.zeros(self.NSEG, np.int64), np.zeros(self.NSEG, np.int64)
        for s in range(self.NSEG):
            x_abs = s * self.W + np.arange(self.W)
            off = (x_abs - s * self.W) >> self.DROP
            t = htan_real(x_abs / 2.0 ** self.XFB) * sc
            if len(np.unique(off)) == 1:
                ICPT[s] = int(round((t.max() + t.min()) / 2)); continue
            k, b = np.polyfit(off, t, 1)
            e = t - (k * off + b); b += (e.max() + e.min()) / 2
            SLOPE[s], ICPT[s] = int(round(k)), int(round(b))
        return SLOPE, ICPT

    def _y(self, htan, abs_q, q):
        half = np.int64(1) << (self.HTANFB - 1)
        return np.clip((abs_q * htan + q * half + half) >> self.HTANFB, -128, 127)

    def outputs(self, SLOPE=None, ICPT=None):
        SLOPE = self.SLOPE if SLOPE is None else SLOPE
        ICPT = self.ICPT if ICPT is None else ICPT
        htan = np.where(self.in_range, (SLOPE[self.seg] * self.off + ICPT[self.seg]) >> self.GB,
                        np.int64(1) << (self.HTANFB - 1))
        return self._y(htan, self.abs_q, self.V["q"])

    def _search(self, kr=3, br=16, rounds=2, cap=40000, seed=0):
        V, rng = self.V, np.random.default_rng(seed)
        bstep = 1 << max(self.GB - 2, 0)
        for s in range(self.NSEG):
            ids = np.where(self.in_range & (self.seg == s))[0]
            if len(ids) == 0:
                continue
            if len(ids) > cap:
                ids = rng.choice(ids, cap, replace=False)
            off, abs_q, q, tg = self.off[ids], self.abs_q[ids], V["q"][ids], V["gold"][ids]
            bk, bb = self.SLOPE[s], self.ICPT[s]
            def evaluate(ks, bs):
                htan = (ks[:, None] * off[None, :] + bs[:, None]) >> self.GB
                d = np.abs(self._y(htan, abs_q[None, :], q[None, :]) - tg[None, :])
                return d.max(axis=1) * 1e7 + (d > 0).sum(axis=1)
            best = evaluate(np.array([bk]), np.array([bb]))[0]
            for _ in range(rounds):
                for k in range(bk - kr, bk + kr + 1):
                    bs = bb + bstep * np.arange(-br, br + 1)
                    sc = evaluate(np.full(len(bs), k), bs)
                    i = int(np.argmin(sc))
                    if sc[i] < best:
                        best, bk, bb = sc[i], k, int(bs[i])
            self.SLOPE[s], self.ICPT[s] = bk, bb

    def score(self):
        d = np.abs(self.outputs() - self.V["gold"])
        E = self.V["E"]
        per_E = {int(e): int((d[E == e] > 0).sum()) for e in np.unique(E)}
        return dict(max=int(d.max()), mism=int((d > 0).sum()), n=int(d.size), per_E=per_E)

    def cost(self):
        htan = (self.SLOPE[self.seg] * self.off + self.ICPT[self.seg]) >> self.GB
        SLOPEW, ICPTW = sbits(self.SLOPE), sbits(self.ICPT)
        HTANW = sbits(np.concatenate([htan[self.in_range], [1 << (self.HTANFB - 1)]]))
        OFFW = self.SEGLSB - self.DROP
        return dict(XW=self.XFB + 3, SLOPEW=SLOPEW, ICPTW=ICPTW, OFFW=OFFW, HTANW=HTANW,
                    table_bits=self.NSEG * (SLOPEW + ICPTW),
                    mult_qm="8x11", mult_slope=f"{SLOPEW}x{OFFW}", mult_qhtan=f"8x{HTANW}")

    def error(self, lo=-9.0, hi=9.0, in_bf=8, out_bf=None):
        k = np.arange(int(np.floor(lo * 2 ** in_bf)) + 1, int(np.ceil(hi * 2 ** in_bf)))
        x = k / 2.0 ** in_bf
        x_abs = np.floor(np.abs(x) * 2.0 ** self.XFB + 0.5).astype(np.int64)   # |x| -> Q3.XFB
        in_range = x_abs < self.XMAX
        x_in = np.where(in_range, x_abs, 0)
        seg = x_in >> self.SEGLSB
        off = (x_in & (self.W - 1)) >> self.DROP
        htan = np.where(in_range, (self.SLOPE[seg] * off + self.ICPT[seg]) >> self.GB,
                        1 << (self.HTANFB - 1)) / 2.0 ** self.HTANFB
        y = x / 2.0 + np.abs(x) * htan
        if out_bf is not None:
            y = np.floor(y * 2.0 ** out_bf + 0.5) / 2.0 ** out_bf
        e = y - x / (1.0 + np.exp(-x))
        return dict(MSE=float(np.mean(e ** 2)), MAE=float(np.mean(np.abs(e))), max_abs=float(np.max(np.abs(e))))

    # exports for RTL work
    def export_table(self, path):
        with open(path, "w") as f:
            for s, (k, b) in enumerate(zip(self.SLOPE, self.ICPT)):
                f.write(f"{s} {int(k)} {int(b)}\n")

def run(configs, out_csv=None, fit="search"):
    V = load_vectors()
    rows = []
    for c in configs:
        t = time.time()
        m = SiLU_UNIT(V, fit=fit, **c)
        sc, co, fe = m.score(), m.cost(), m.error()
        row = {**c, "max_lsb": sc["max"], "mism": sc["mism"],
               "mism_pct": round(100 * sc["mism"] / sc["n"], 4),
               "MSE": f"{fe['MSE']:.3e}", "MAE": f"{fe['MAE']:.3e}", **co, "sec": round(time.time() - t, 1)}
        rows.append(row)
        print(", ".join(f"{k}={v}" for k, v in row.items()), flush=True)
    if out_csv and rows:
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    return rows


if __name__ == "__main__":
    grid = [dict(XFB=f, NSEG=n, OW=None, HTANFB=h, GB=g)
        for f, n, h, g in product([8, 9, 10],     # |x| fraction bits
                                  [16, 32, 64],   # segments
                                  [11, 12, 13],   # htan fraction bits
                                  [3, 4])]        # guard bits

    run(grid, fit="ls")