'''
Script for the design space exploration of the SiLU unit

We explore five axes of design choices.
NSEG: Number of linear segments for [0, 8)
FXA: Fraction bits of |x|, where x is represented as Q3.FXA
OW: The offset bits of |x|'s position inside a segment
HF: The fraction bits of h, which is the table's output
KS: Additional fraction bits of the slope

Datapath (bit-accurate model; RTL must match it exactly):
  scale s = m * 2^E,  m = 1.mantissa (m_int = 1024 + mantissa),  E = exp_field - 15
  bypass:  s >= 1 -> ReLU(q)  |  s < 2^-13 -> round(q/2)  |  invalid -> 0 (spec TBD)
  active (E = -13 .. -1):
    P   = |q| * m_int                         8 x 11-bit integer multiply
    a   = round(P * 2^(E - 10 + FXA))         |x| in unsigned Q3.FXA; a >= 8.0 -> h = 0.5
    seg = a >> (FXA + 3 - log2(NSEG))         uniform segments over [0, 8): index = top bits of a
    off = low bits of a, truncated to its top OW bits
    h   = (K[seg] * off + B[seg]) >> KS       h ~= sigmoid(|x|) - 0.5, HF fraction bits
    y   = clamp((|q| * h + q * 2^(HF-1) + 2^(HF-1)) >> HF)        = round(q/2 + |q| * h)

Error at the output is |q| * (error of h) <= 128 * (error of h), independent of the scale.
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

def h_real(a):
    return 0.5 * np.tanh(a / 2.0)  # sigmoid(a) - 0.5

class AFP16:
    def __init__(self, V, FXA=7, NSEG=16, OW=None, HF=11, KS=4, fit="search", search_cap=40000, seed=0):
        assert (8 << FXA) % NSEG == 0
        self.V, self.FXA, self.NSEG, self.OW, self.HF, self.KS = V, FXA, NSEG, OW, HF, KS
        self.AMAX = 8 << FXA
        self.W = self.AMAX // NSEG                        # segment width
        self.WB = int(np.log2(self.W))                    # offset bits before truncation
        self.DROP = 0 if OW is None else max(0, self.WB - OW)
        self._front_end()
        self.K, self.B = self._fit_ls()
        if fit == "search":
            self._search(cap=search_cap, seed=seed)

    def _front_end(self):
        V = self.V
        self.mq = np.abs(V["q"])
        P = self.mq * V["m"]
        sh = V["E"] - 10 + self.FXA
        left = P << np.clip(sh, 0, 40)
        rs = np.clip(-sh, 0, 62)
        right = (P + np.where(rs > 0, np.int64(1) << np.clip(rs - 1, 0, 61), 0)) >> rs
        a = np.minimum(np.where(sh >= 0, left, right), self.AMAX)
        self.inr = a < self.AMAX
        self.seg = np.where(self.inr, a >> self.WB, 0)
        self.off = (a & (self.W - 1)) >> self.DROP

    def _fit_ls(self):
        sc = 2.0 ** (self.HF + self.KS)
        K, Bc = np.zeros(self.NSEG, np.int64), np.zeros(self.NSEG, np.int64)
        for s in range(self.NSEG):
            a = s * self.W + np.arange(self.W)
            off = (a - s * self.W) >> self.DROP
            t = h_real(a / 2.0 ** self.FXA) * sc
            if len(np.unique(off)) == 1:
                Bc[s] = int(round((t.max() + t.min()) / 2)); continue
            k, b = np.polyfit(off, t, 1)
            e = t - (k * off + b); b += (e.max() + e.min()) / 2
            K[s], Bc[s] = int(round(k)), int(round(b))
        return K, Bc

    def _y(self, h, mq, q):
        half = np.int64(1) << (self.HF - 1)
        return np.clip((mq * h + q * half + half) >> self.HF, -128, 127)

    def outputs(self, K=None, Bc=None):
        K = self.K if K is None else K
        Bc = self.B if Bc is None else Bc
        h = np.where(self.inr, (K[self.seg] * self.off + Bc[self.seg]) >> self.KS, np.int64(1) << (self.HF - 1))
        return self._y(h, self.mq, self.V["q"])

    def _search(self, kr=3, br=16, rounds=2, cap=40000, seed=0):
        V, rng = self.V, np.random.default_rng(seed)
        bstep = 1 << max(self.KS - 2, 0)
        for s in range(self.NSEG):
            ids = np.where(self.inr & (self.seg == s))[0]
            if len(ids) == 0:
                continue
            if len(ids) > cap:
                ids = rng.choice(ids, cap, replace=False)
            off, mq, q, tg = self.off[ids], self.mq[ids], V["q"][ids], V["gold"][ids]
            bk, bb = self.K[s], self.B[s]
            def evaluate(ks, bs):
                h = (ks[:, None] * off[None, :] + bs[:, None]) >> self.KS
                d = np.abs(self._y(h, mq[None, :], q[None, :]) - tg[None, :])
                return d.max(axis=1) * 1e7 + (d > 0).sum(axis=1)
            best = evaluate(np.array([bk]), np.array([bb]))[0]
            for _ in range(rounds):
                for k in range(bk - kr, bk + kr + 1):
                    bs = bb + bstep * np.arange(-br, br + 1)
                    sc = evaluate(np.full(len(bs), k), bs)
                    i = int(np.argmin(sc))
                    if sc[i] < best:
                        best, bk, bb = sc[i], k, int(bs[i])
            self.K[s], self.B[s] = bk, bb

    def score(self):
        d = np.abs(self.outputs() - self.V["gold"])
        E = self.V["E"]
        per_E = {int(e): int((d[E == e] > 0).sum()) for e in np.unique(E)}
        return dict(max=int(d.max()), mism=int((d > 0).sum()), n=int(d.size), per_E=per_E)

    def cost(self):
        h = (self.K[self.seg] * self.off + self.B[self.seg]) >> self.KS
        KW, BW = sbits(self.K), sbits(self.B)
        HW = sbits(np.concatenate([h[self.inr], [1 << (self.HF - 1)]]))
        return dict(a_bits=self.FXA + 3, KW=KW, BW=BW, OFFW=self.WB - self.DROP, HW=HW,
                    table_bits=self.NSEG * (KW + BW),
                    mult_qm="8x11", mult_k=f"{KW}x{self.WB - self.DROP}", mult_qh=f"8x{HW}")

    # exports for RTL work
    def export_table(self, path):
        with open(path, "w") as f:
            for s, (k, b) in enumerate(zip(self.K, self.B)):
                f.write(f"{s} {int(k)} {int(b)}\n")

def run(configs, out_csv=None, fit="search"):
    V = load_vectors()
    rows = []
    for c in configs:
        t = time.time()
        m = AFP16(V, fit=fit, **c)
        sc, co = m.score(), m.cost()
        row = {**c, "max_lsb": sc["max"], "mism": sc["mism"],
               "mism_pct": round(100 * sc["mism"] / sc["n"], 4), **co, "sec": round(time.time() - t, 1)}
        rows.append(row)
        print(", ".join(f"{k}={v}" for k, v in row.items()), flush=True)
    if out_csv and rows:
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    return rows


if __name__ == "__main__":
    grid = [dict(FXA=f, NSEG=n, OW=None, HF=h, KS=k)
        for f, n, h, k in product([8, 9, 10],     # |x| fraction bits
                                  [16, 32, 64],   # segments
                                  [11, 12, 13],   # h fraction bits
                                  [3, 4])]        # extra slope bits

    run(grid, fit="ls")