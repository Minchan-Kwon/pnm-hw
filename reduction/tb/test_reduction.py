"""cocotb tests for reduction.v.

Streams partial sums for several output vectors with beats from different
addresses interleaved in random order, random bubbles, and back-to-back reuse
of the same address, then compares each emitted beat against a Python sum
(clamped when OUT_WIDTH < ACC_WIDTH).
"""

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

LANES = int(os.environ["RED_LANES"])
IN_WIDTH = int(os.environ["RED_IN_WIDTH"])
MAX_TERMS = int(os.environ["RED_MAX_TERMS"])
DEPTH = int(os.environ["RED_DEPTH"])
ACC_WIDTH = IN_WIDTH + (MAX_TERMS - 1).bit_length()
OUT_WIDTH = int(os.environ.get("RED_OUT_WIDTH", ACC_WIDTH))
CLK_NS = 2.5


def pack(values, width):
    mask = (1 << width) - 1
    word = 0
    for l, v in enumerate(values):
        word |= (v & mask) << (l * width)
    return word


def unpack(word, width):
    mask = (1 << width) - 1
    out = []
    for l in range(LANES):
        v = (word >> (l * width)) & mask
        out.append(v - (1 << width) if v >> (width - 1) else v)
    return out


def reference(terms):
    """Sum each lane over all partial sums, then clamp like the RTL."""
    s = [sum(col) for col in zip(*terms)]
    if OUT_WIDTH < ACC_WIDTH:
        m = (1 << (OUT_WIDTH - 1)) - 1
        s = [max(-m, min(m, v)) for v in s]
    return s


def rand_partial(rng, corner):
    lo, hi = -(1 << (IN_WIDTH - 1)), (1 << (IN_WIDTH - 1)) - 1
    if corner == "max":
        return [hi] * LANES
    if corner == "min":
        return [lo] * LANES
    return [rng.randint(lo, hi) for _ in range(LANES)]


def build_stream(rng, rounds, corner=None, bubble_prob=0.2):
    """Return (beats, expected). A beat is None (bubble) or (first, last, addr, data)."""
    beats, expected = [], []
    for _ in range(rounds):
        # Each address gets 1..MAX_TERMS partial sums; interleave addresses randomly
        queues = {}
        for a in range(DEPTH):
            n = MAX_TERMS if corner else rng.randint(1, MAX_TERMS)
            queues[a] = [rand_partial(rng, corner) for _ in range(n)]
        progress = {a: 0 for a in range(DEPTH)}
        while queues:
            a = rng.choice(list(queues))
            terms = queues[a]
            i = progress[a]
            first, last = i == 0, i == len(terms) - 1
            if rng.random() < bubble_prob:
                beats.append(None)
            beats.append((first, last, a, terms[i]))
            if last:
                expected.append((a, reference(terms)))
                del queues[a]
            else:
                progress[a] = i + 1
    return beats, expected


async def run_stream(dut, beats, expected):
    dut.in_valid.value = 0
    dut.in_first.value = 0
    dut.in_last.value = 0
    dut.in_addr.value = 0
    dut.in_data.value = 0
    dut.rstn.value = 0
    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    await ClockCycles(dut.clk, 3)
    dut.rstn.value = 1
    await RisingEdge(dut.clk)

    got = []

    async def monitor():
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            if dut.out_valid.value == 1:
                got.append((int(dut.out_addr.value), unpack(int(dut.out_data.value), OUT_WIDTH)))

    cocotb.start_soon(monitor())

    for b in beats:
        if b is None:
            dut.in_valid.value = 0
        else:
            first, last, a, data = b
            dut.in_valid.value = 1
            dut.in_first.value = int(first)
            dut.in_last.value = int(last)
            dut.in_addr.value = a
            dut.in_data.value = pack(data, IN_WIDTH)
        await RisingEdge(dut.clk)
    dut.in_valid.value = 0
    await ClockCycles(dut.clk, 3)

    assert len(got) == len(expected), f"got {len(got)} outputs, expected {len(expected)}"
    for k, ((ga, gd), (ea, ed)) in enumerate(zip(got, expected)):
        assert ga == ea, f"output {k}: addr {ga}, expected {ea}"
        bad = [l for l in range(LANES) if gd[l] != ed[l]]
        assert not bad, f"output {k} addr {ea}: lane {bad[0]} = {gd[bad[0]]}, expected {ed[bad[0]]}"


@cocotb.test()
async def random_interleaved(dut):
    beats, expected = build_stream(random.Random(1), rounds=4)
    await run_stream(dut, beats, expected)


@cocotb.test()
async def back_to_back_no_bubbles(dut):
    beats, expected = build_stream(random.Random(2), rounds=3, bubble_prob=0.0)
    await run_stream(dut, beats, expected)


@cocotb.test()
async def overflow_corners(dut):
    """MAX_TERMS copies of the largest / smallest INT value: must not wrap."""
    rng = random.Random(3)
    b1, e1 = build_stream(rng, rounds=1, corner="max", bubble_prob=0.0)
    b2, e2 = build_stream(rng, rounds=1, corner="min", bubble_prob=0.0)
    await run_stream(dut, b1 + b2, e1 + e2)
