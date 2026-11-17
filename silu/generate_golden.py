"""
Generating the golden test vectors for the INT8 SiLU unit

Scale
    Output scale is equal to the input scale s.
    The SiLU unit assumes that the scales have been calibrated so that
    the scale of xWgate is equal to the SiLU output.

Definition
    x = s * q
    y_ref = clamp[-128, 127](floor(q * sigmoid(x) + 0.5))

SiLU Inputs
    q = INT8 value [-128, 127]
    s = FP16 scale
SiLU Outputs
    y = INT8 value
"""

import numpy as np

Q = np.arange(-128, 128, dtype=np.int64)    # 256 INT8 values
SCALE = np.arange(65536, dtype=np.uint32)    # All FP16 bit patterns

INVALID, HALF, ACTIVE, RELU = 0, 1, 2, 3

def decode_fp16(scale):
    '''
    Exact float64 value of each FP16 bit pattern
    '''
    return scale.astype(np.uint16).view(np.float16).astype(np.float64)

def get_scale_type(scale):
    '''
    Classify each scale pattern
    INVALID: NaN, zero, inf, negative
    HALF: exp < 2 (s<2^-13), Round
    ACTIVE: 2 <= exp < 15 (2^-13<=s<1), Compute linear approximation
    RELU: exp >= 15 (s>=1), ReLU
    '''
    sign = (scale >> 15) & 1
    exp = (scale >> 10) & 0x1F
    mantissa = scale & 0x3FF
    scale_type = np.full(scale.shape, ACTIVE, dtype=np.uint8)
    scale_type[exp >= 15] = RELU
    scale_type[exp < 2] = HALF
    invalid = (sign == 1) | ((exp == 0) & (mantissa == 0)) | (exp == 31)   # negative, zero, Inf/NaN
    scale_type[invalid] = INVALID
    return scale_type

def get_golden_row(scale):
    '''
    Golden outputs for all 256 q at a single scale
    '''
    x_abs = np.abs(Q) * s
    val = Q / 2.0 + np.abs(Q) * np.tanh(x_abs / 2.0) / 2.0  # q * sigmoid(q*s)
    return np.clip(np.floor(val + 0.5), -128, 127).astype(np.int8)

def build():
    s_all = decode_fp16(SCALE)
    scale_type = get_scale_type(SCALE)
    golden = np.zeros((65536, 256), dtype = np.int8)  # initialize to zeros, invalid scales stay 0
    ok = (scale_type != INVALID)
    s = s_all[ok][:, None]
    x_abs = np.abs(Q)[None, :] * s
    val = Q[None, :] / 2.0 + np.abs(Q)[None, :] * np.tanh(x_abs / 2.0) / 2.0
    golden[ok] = np.clip(np.floor(val + 0.5), -128, 127).astype(np.int8)
    return golden, scale_type

def export_hex(path, gold, scale_bits):
    '''
    Exports a .txt file populated with 32-bit words.
    Each word is a test vector: {scale[15:0], q[7:0], y_expected[7:0]}.
    The testbench reads each word, drives scale and q from it, and compares y.
    '''
    sb = np.asarray(scale_bits, dtype=np.uint32)
    qb = (Q & 0xFF).astype(np.uint32)
    words = (sb[:, None] << 16) | (qb[None, :] << 8) | (gold[sb].astype(np.int64) & 0xFF).astype(np.uint32)
    np.savetxt(path, words.reshape(-1), fmt="%08x")
    return words.size

if __name__ == "__main__":
    import time
    t = time.time()
    gold, scale_type = build()
    np.save("golden.npy", gold)
    np.save("scale_type.npy", scale_type)
    names = {INVALID: "invalid", HALF: "half (s<2^-13)", ACTIVE: "active", RELU: "relu (s>=1)"}
    for b, n in names.items():
        k = int((scale_type == b).sum())
        print(f"{n:16s}: {k:6d} scales x 256 q = {k * 256:9,d} vectors")
    n_active = export_hex("golden_active.hex", gold, np.where(scale_type == ACTIVE)[0])
    n_valid = export_hex("golden_all_valid.hex", gold, np.where(scale_type != INVALID)[0])
    print(f"Generated golden.npy, scale_type.npy, golden_active.hex ({n_active:,}), "
          f"golden_all_valid.hex ({n_valid:,})  in {time.time() - t:.1f}s")