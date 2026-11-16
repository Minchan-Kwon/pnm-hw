'''
Generate the coefficients for each linear segment and write them as silu_params.vh for the RTL
'''
import numpy as np
from design_exploration import load_vectors, SiLU_UNIT, sbits


def write_vh(m, path, fit="search"):
    KW, BW = sbits(m.K), sbits(m.B)                   # signed widths of K and B
    SEGB = int(np.log2(m.NSEG))                       # segment index bits
    OFFW = max(m.WB - m.DROP, 1)                      # offset width into the K x off multiplier
    a = np.arange(m.AMAX)                             # every in-range |x| code
    h_all = (m.K[a >> m.WB] * ((a & (m.W - 1)) >> m.DROP) + m.B[a >> m.WB]) >> m.KS
    HW = sbits(np.append(h_all, 1 << (m.HF - 1)))     # exact signed width of h (incl. the 0.5 bypass)
    sc = m.score()

    L = []
    L.append("// AUTO-GENERATED -- do not edit by hand")
    L.append(f"// config: FXA={m.FXA} NSEG={m.NSEG} OW={m.OW} HF={m.HF} KS={m.KS} fit={fit}")
    L.append(f"// model vs golden (active band): max {sc['max']} LSB, {sc['mism']} / {sc['n']} mismatches")
    L.append("")
    L.append(f"localparam integer FXA  = {m.FXA};")
    L.append(f"localparam integer AW   = {m.FXA + 3};")
    L.append(f"localparam integer AMAX = {m.AMAX};")
    L.append(f"localparam integer NSEG = {m.NSEG};")
    L.append(f"localparam integer SEGB = {SEGB};")
    L.append(f"localparam integer WB   = {m.WB};")
    L.append(f"localparam integer DROP = {m.DROP};")
    L.append(f"localparam integer OFFW = {OFFW};")
    L.append(f"localparam integer HF   = {m.HF};")
    L.append(f"localparam integer KS   = {m.KS};")
    L.append(f"localparam integer KW   = {KW};")
    L.append(f"localparam integer BW   = {BW};")
    L.append(f"localparam integer HW   = {HW};")
    L.append("")
    L.append("// constant coefficient table: returns {K, B}")
    L.append("function [KW+BW-1:0] silu_coef;")
    L.append("    input [SEGB-1:0] seg;")
    L.append("    begin")
    L.append("        case (seg)")
    for s in range(m.NSEG):
        k, b = int(m.K[s]), int(m.B[s])
        kv = k & ((1 << KW) - 1)                      # two's complement bit patterns
        bv = b & ((1 << BW) - 1)
        L.append(f"            {SEGB}'d{s:<3d}: silu_coef = {{{KW}'h{kv:0{(KW + 3) // 4}x}, "
                 f"{BW}'h{bv:0{(BW + 3) // 4}x}}};   // K = {k:6d}, B = {b:8d}")
    L.append("            default: silu_coef = {(KW+BW){1'b0}};")
    L.append("        endcase")
    L.append("    end")
    L.append("endfunction")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


V = load_vectors()
m = SiLU_UNIT(V, FXA=9, NSEG=32, HF=12, KS=4)   # fits automatically (fit="search" by default)
print(m.score()["max"], m.score()["mism"])    # should match your CSV row
print(m.K, m.B)                               # slope and intercept per segment
m.export_table("coeffs.txt")                  # human-readable "segment K B"
write_vh(m, "./silu_params.vh")          # what the RTL actually includes