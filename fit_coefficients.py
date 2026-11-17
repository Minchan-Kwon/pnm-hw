'''
Generate the coefficients for each linear segment and write them as silu_params.vh for the RTL
'''
import numpy as np
from design_exploration import load_vectors, SiLU_UNIT, sbits
from gen_vectors import write_vectors


def write_vh(m, path, fit="search"):
    SLOPEW, ICPTW = sbits(m.SLOPE), sbits(m.ICPT)     # signed widths of slope and intercept
    SEGB = int(np.log2(m.NSEG))                       # segment index bits
    OFFW = max(m.SEGLSB - m.DROP, 1)                  # offset width into the slope x offset multiplier
    x = np.arange(m.XMAX)                             # every in-range |x| code
    htan_all = (m.SLOPE[x >> m.SEGLSB] * ((x & (m.W - 1)) >> m.DROP) + m.ICPT[x >> m.SEGLSB]) >> m.GB
    HTANW = sbits(np.append(htan_all, 1 << (m.HTANFB - 1)))   # exact signed width of htan (incl. the 0.5 bypass)
    sc = m.score()

    L = []
    L.append("// AUTO-GENERATED -- do not edit by hand")
    L.append(f"// config: XFB={m.XFB} NSEG={m.NSEG} OW={m.OW} HTANFB={m.HTANFB} GB={m.GB} fit={fit}")
    L.append(f"// model vs golden (active band): max {sc['max']} LSB, {sc['mism']} / {sc['n']} mismatches")
    L.append("")
    L.append(f"localparam integer XFB    = {m.XFB};      // |x| fraction bits")
    L.append(f"localparam integer XW     = {m.XFB + 3};     // |x| width (3 integer bits + XFB)")
    L.append(f"localparam integer XMAX   = {m.XMAX};   // 8.0 in |x| format; at or above -> htan = 0.5")
    L.append(f"localparam integer NSEG   = {m.NSEG};     // number of segments over [0, 8)")
    L.append(f"localparam integer SEGB   = {SEGB};      // segment index bits")
    L.append(f"localparam integer SEGLSB = {m.SEGLSB};      // segment index starts at this bit of |x|")
    L.append(f"localparam integer DROP   = {m.DROP};      // low offset bits dropped before the multiply")
    L.append(f"localparam integer OFFW   = {OFFW};      // offset width into the multiplier")
    L.append(f"localparam integer HTANFB = {m.HTANFB};     // htan fraction bits")
    L.append(f"localparam integer GB     = {m.GB};      // guard bits on slope/intercept, shifted out at the end")
    L.append(f"localparam integer SLOPEW = {SLOPEW};      // signed width of slope")
    L.append(f"localparam integer ICPTW  = {ICPTW};     // signed width of intercept")
    L.append(f"localparam integer HTANW  = {HTANW};     // signed width of htan")
    L.append("")
    L.append("// constant coefficient table: returns {slope, intercept}")
    L.append("function [SLOPEW+ICPTW-1:0] htan_coef;")
    L.append("    input [SEGB-1:0] seg;")
    L.append("    begin")
    L.append("        case (seg)")
    for s in range(m.NSEG):
        k, b = int(m.SLOPE[s]), int(m.ICPT[s])
        kv = k & ((1 << SLOPEW) - 1)                  # two's complement bit patterns
        bv = b & ((1 << ICPTW) - 1)
        L.append(f"            {SEGB}'d{s:<3d}: htan_coef = {{{SLOPEW}'h{kv:0{(SLOPEW + 3) // 4}x}, "
                 f"{ICPTW}'h{bv:0{(ICPTW + 3) // 4}x}}};   // slope = {k:6d}, intercept = {b:8d}")
    L.append("            default: htan_coef = {(SLOPEW+ICPTW){1'b0}};")
    L.append("        endcase")
    L.append("    end")
    L.append("endfunction")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


V = load_vectors()
m = SiLU_UNIT(V, XFB=8, NSEG=32, HTANFB=11, GB=3)   # fits automatically (fit="search" by default)
sc = m.score()
print(sc["max"], sc["mism"])                  # should match your CSV row
print(m.SLOPE, m.ICPT)                        # slope and intercept per segment
m.export_table("coeffs.txt")                  # human-readable "segment slope intercept"
write_vh(m, "./silu_params.vh")               # what the RTL actually includes
write_vectors(m, "./vec.hex", mode="quick")   # expected outputs for the testbench, from the same m