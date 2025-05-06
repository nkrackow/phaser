import unittest

import numpy as np
from migen import *

import interpolate


def feed(endpoint, x, rate):
    n, d = rate
    t = 0
    for i, xi in enumerate(x):
        while t * n < i * d:
            yield
            t += 1
        yield endpoint.data.eq(int(xi))
        yield endpoint.stb.eq(1)
        yield
        t += 1
        while not (yield endpoint.ack):
            yield
        yield endpoint.stb.eq(0)


@passive
def retrieve(endpoint, o):
    yield
    while True:
        yield endpoint.ack.eq(1)
        yield
        while not (yield endpoint.stb):
            yield
        o.append(((yield endpoint.data0), (yield endpoint.data1)))
        yield endpoint.ack.eq(0)


class TestInter(unittest.TestCase):
    def setUp(self):
        self.dut = interpolate.InterpolateChannel()

    def test_init(self):
        self.assertEqual(len(self.dut.input.data), 14)
        self.assertEqual(len(self.dut.output.data0), 16)

    def test_seq(self):
        # impulse response plus latency
        x = [(1 << 13) - 1] + [0] * (30 + 10)
        y = []
        run_simulation(
            self.dut,
            [feed(self.dut.input, x, rate=(1, 10)), retrieve(self.dut.output, y)],
            vcd_name="int.vcd",
        )
        y = np.ravel(y)
        print(repr(y))
        # y0 =
        # np.testing.assert_equal(y, y0)

    def test_sine_overflow(self):
        # sine has the zero crossing at 0 so no hard edge
        sps = 1e9 / 20  # interpolation rate 20

        num_samples = 1000
        amplitude = (1 << 13) - 1
        freq = 1.2e6
        sine = [
            int(round(np.sin(2 * np.pi * i * freq / sps) * amplitude))
            for i in range(num_samples)
        ]
        y = []
        run_simulation(
            self.dut,
            [feed(self.dut.input, sine, rate=(1, 10)), retrieve(self.dut.output, y)],
            vcd_name="sine.vcd",
        )
        y = np.ravel(y)
        # prev sample is close to +1 and current is below one
        assert not any(
            prev >= 0x7FF0 and current <= 0 for prev, current in zip(y[:-1], y[1:])
        )
