"""Make test vectors for tb_silu_a.v.

Expected outputs come from the bit-accurate model (same fit as gen_params_vh.py), NOT from golden.
  model vs golden  = accuracy question (answered in the DSE)
  RTL   vs model   = correctness question (must be 0 mismatches)

Word format (one per line, hex): {scale[15:0], q[7:0], y_expected[7:0]}

Modes:
  quick : every one of the 65,536 scale codes x edge q {-128,-127,-1,0,1,127} + random vectors
  full  : all 3,407,872 active-band vectors (exp 2..14, all mantissas, all q)
          + every scale code with edge q (covers bypass + invalid)

Usage (use the SAME config flags you gave gen_params_vh.py):
  python3 gen_vectors.py --XFB 8 --NSEG 32 --HTANFB 11 --GB 3 --mode quick --out ../vec.hex
"""
import argparse
import numpy as np
from design_exploration import load_vectors, SiLU_UNIT


def full_spec_outputs(m, sb, q):
    """Expected RTL output for any (scale bits, q): bypass rules + the model's LUT path."""
    sb, q = np.asarray(sb, np.int64), np.asarray(q, np.int64)
    ex, man, sign = (sb >> 10) & 31, sb & 1023, sb >> 15
    invalid = (sign == 1) | ((ex == 0) & (man == 0)) | (ex == 31)
    abs_q = np.abs(q)
    P = abs_q * (1024 + man)
    rs = np.clip(25 - m.XFB - ex, 0, 40)
    x_abs = np.minimum(((2 * P) + (np.int64(1) << rs)) >> (rs + 1), m.XMAX)
    in_range = x_abs < m.XMAX
    x_in = np.where(in_range, x_abs, 0)
    seg, off = x_in >> m.SEGLSB, (x_in & (m.W - 1)) >> m.DROP
    htan = np.where(in_range, (m.SLOPE[seg] * off + m.ICPT[seg]) >> m.GB, np.int64(1) << (m.HTANFB - 1))
    ylut = m._y(htan, abs_q, q)
    y = np.where(ex >= 15, np.maximum(q, 0),          # s >= 1      -> ReLU(q)
        np.where(ex <= 1, (q + 1) >> 1,                # s < 2^-13   -> round(q/2)
                 ylut))
    return np.where(invalid, 0, y)                     # bad scale   -> 0


def build(mode, n_rand, seed):
    rng = np.random.default_rng(seed)
    all_s = np.arange(65536, dtype=np.int64)
    edge_q = np.array([-128, -127, -1, 0, 1, 127], dtype=np.int64)
    sb = [np.repeat(all_s, len(edge_q))]
    q = [np.tile(edge_q, len(all_s))]
    if mode == "full":
        act_s = np.array([s for s in range(1 << 15) if 2 <= (s >> 10) <= 14], dtype=np.int64)
        qs = np.arange(-128, 128, dtype=np.int64)
        sb.append(np.repeat(act_s, 256)); q.append(np.tile(qs, len(act_s)))
    else:
        sb.append(rng.integers(0, 65536, n_rand)); q.append(rng.integers(-128, 128, n_rand))
    return np.concatenate(sb), np.concatenate(q)


def write_vectors(m, path, mode="quick", n_rand=200000, seed=1):
    sb, q = build(mode, n_rand, seed)
    y = full_spec_outputs(m, sb, q)
    words = (sb << 16) | ((q & 0xFF) << 8) | (y & 0xFF)
    with open(path, "w") as f:
        f.write("\n".join(f"{w:08x}" for w in words) + "\n")
    print(f"wrote {len(words)} vectors to {path}   (pass -P tb.N={len(words)} to iverilog)")
    return len(words)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--XFB", type=int, default=8)
    ap.add_argument("--NSEG", type=int, default=32)
    ap.add_argument("--HTANFB", type=int, default=11)
    ap.add_argument("--GB", type=int, default=3)
    ap.add_argument("--OW", type=int, default=None)
    ap.add_argument("--fit", default="search", choices=["ls", "search"])
    ap.add_argument("--mode", default="quick", choices=["quick", "full"])
    ap.add_argument("--nrand", type=int, default=200000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="vec.hex")
    a = ap.parse_args()

    m = SiLU_UNIT(load_vectors(), XFB=a.XFB, NSEG=a.NSEG, OW=a.OW, HTANFB=a.HTANFB, GB=a.GB, fit=a.fit)
    write_vectors(m, a.out, a.mode, a.nrand, a.seed)