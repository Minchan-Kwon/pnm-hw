"""Build and run the reduction-unit cocotb tests with Icarus Verilog.

Usage:
    conda activate hdl
    pytest -v pnm-hw/reduction/tb/test_runner.py
    WAVES=1 pytest ... -k default    # also dump an FST waveform
"""

import os
from pathlib import Path

import pytest
from cocotb_tools.runner import get_results, get_runner

TB_DIR = Path(__file__).resolve().parent
RTL_DIR = TB_DIR.parent / "rtl"
BUILD_ROOT = TB_DIR / "sim_build"
WAVES = os.environ.get("WAVES", "0") == "1"

# (id, LANES, IN_WIDTH, MAX_TERMS, DEPTH, OUT_WIDTH or None = full accumulator width)
CONFIGS = [
    ("default", 64, 8, 16, 32, None),   # 64 lanes, INT8, 32-beat window
    ("sat8", 64, 8, 16, 32, 8),         # Clamp the result back to INT8
    ("depth1", 64, 8, 4, 1, None),      # Pure adder + register, no address
    ("int16", 8, 16, 7, 4, None),       # Other precision, non-power-of-2 terms
]


@pytest.mark.parametrize("cfg", CONFIGS, ids=[c[0] for c in CONFIGS])
def test_reduction(cfg):
    tag, lanes, in_w, terms, depth, out_w = cfg
    params = {"LANES": lanes, "IN_WIDTH": in_w, "MAX_TERMS": terms, "DEPTH": depth}
    env = {"RED_LANES": str(lanes), "RED_IN_WIDTH": str(in_w),
           "RED_MAX_TERMS": str(terms), "RED_DEPTH": str(depth)}
    if out_w is not None:
        params["OUT_WIDTH"] = out_w
        env["RED_OUT_WIDTH"] = str(out_w)

    runner = get_runner("icarus")
    build_dir = BUILD_ROOT / tag
    runner.build(
        sources=[RTL_DIR / "reduction.v"],
        hdl_toplevel="reduction",
        parameters=params,
        build_args=["-Wall"],
        build_dir=build_dir,
        always=True,
        timescale=("1ns", "1ps"),
        waves=WAVES,
    )
    results_xml = runner.test(
        hdl_toplevel="reduction",
        test_module="test_reduction",
        test_dir=TB_DIR,
        build_dir=build_dir,
        extra_env=env,
        waves=WAVES,
    )
    num_tests, num_failed = get_results(results_xml)
    assert num_tests > 0, "no cocotb tests ran"
    assert num_failed == 0, f"{num_failed}/{num_tests} cocotb tests failed (see log above)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
