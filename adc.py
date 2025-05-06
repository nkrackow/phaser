from collections import namedtuple

from migen import *
from migen.genlib.io import DDROutput, DifferentialInput, DifferentialOutput

# all times in cycles
AdcParams = namedtuple(
    "AdcParams",
    [
        "channels",  # number of channels per lane
        "lanes",  # number of SDO? data lanes
        # lanes need to be named alphabetically and contiguous
        # (e.g. [sdoa, sdob, sdoc, sdoc] or [sdoa, sdob])
        "width",  # bits to transfer per channel
        "t_cnvh",  # CNVH duration (minimum)
        "t_conv",  # CONV duration (minimum)
        "t_rtt",  # upper estimate for clock round trip time from
        # sck at the FPGA to clkout at the FPGA (cycles)
        # this avoids having synchronizers and another counter
        # to signal end-of transfer
        # and it ensures fixed latency early in the pipeline
    ],
)


class Adc(Module):
    """Multi-lane, multi-channel, triggered, source-synchronous, serial
    ADC interface.
    * Supports ADCs like the LTC2320-16.
    * Hardcoded timings.
    """

    def __init__(self, pins, params):
        self.params = p = params  # ADCParams
        self.data = [
            Signal((p.width, True), reset_less=True) for _ in range(p.channels)
        ]  # ADC output data
        self.data_inv = [
            Signal((p.width, True), reset_less=True) for _ in range(p.channels)
        ]  # retrieved ADC data (inverted)
        self.start = Signal()  # start conversion and reading
        self.reading = Signal()  # data is being read (outputs are invalid)
        self.done = Signal()  # data is valid and a new conversion can be started

        ###

        self.sck = sck = Signal()
        self.sck_en = sck_en = Signal()
        # self.clkout_in = clkout_in = Signal()
        self.clkout = clkout = Signal()
        self.cnvn = cnvn = Signal()
        self.sdo = sdo = [Signal(), Signal()]
        self.sdo2n = sdo2n = Signal()  # inverted input
        self.ddr_clk_synth = ddr_clk_synth = Signal(
            6, reset=0b000111
        )  # signal to generate a 10ns period clock

        if pins != None:
            self.specials += [
                DifferentialOutput(sck, pins.sck_n, pins.sck_p),  # swapped
                DifferentialInput(pins.clkout_p, pins.clkout_n, clkout),
                DifferentialOutput(~cnvn, pins.cnvn_n, pins.cnvn_p),  # swapped
                DifferentialInput(pins.sdo_p[0], pins.sdo_n[0], sdo[0]),
                DifferentialInput(pins.sdo_n[1], pins.sdo_p[1], sdo2n),  # swapped
                DDROutput(ddr_clk_synth[1], ddr_clk_synth[0], sck, ClockSignal("sys")),
            ]

        self.comb += [
            sdo[1].eq(~sdo2n),  # invert due to swapped input
        ]

        # set up counters for the four states CNVH, CONV, READ, RTT
        t_read = 3 * p.width * p.channels // p.lanes  # SDR
        assert p.lanes * t_read == p.width * p.channels * 3
        assert all(_ > 0 for _ in (p.t_cnvh, p.t_conv, p.t_rtt))
        assert p.t_conv > 1
        count = Signal(max=max(p.t_cnvh, p.t_conv, t_read, p.t_rtt), reset_less=True)
        count_load = Signal.like(count)
        count_done = Signal()
        update = Signal()

        self.comb += count_done.eq(count == 0)
        self.sync += [
            count.eq(count - 1),
            If(
                count_done,
                count.eq(count_load),
            ),
            # 6 bit barrel shifter that shifts by two each cycle
            If(sck_en, Cat(ddr_clk_synth).eq(Cat(ddr_clk_synth[-2:], ddr_clk_synth))),
        ]

        self.submodules.fsm = fsm = FSM("IDLE")
        fsm.act(
            "IDLE",
            self.done.eq(1),
            If(self.start, count_load.eq(p.t_cnvh - 1), NextState("CNVH")),
        )
        fsm.act(
            "CNVH",
            count_load.eq(p.t_conv - 1),
            cnvn.eq(1),
            If(count_done, NextState("CONV")),
        )
        fsm.act("CONV", count_load.eq(t_read - 1), If(count_done, NextState("READ")))
        fsm.act(
            "READ",
            self.reading.eq(1),
            count_load.eq(p.t_rtt - 1),
            sck_en.eq(1),
            If(count_done, NextState("RTT")),
        )
        fsm.act(
            "RTT",  # account for sck->clkout round trip time
            self.reading.eq(1),
            If(count_done, update.eq(1), NextState("IDLE")),
        )

        self.clock_domains.cd_ret = ClockDomain("ret", reset_less=True)
        self.comb += self.cd_ret.clk.eq(clkout)

        k = p.channels // p.lanes
        assert t_read == k * p.width * 3
        # flip sdos because the inputs on the ADC are flipped on schematic
        for i, sdo in enumerate(reversed(sdo)):
            sdo_sr = Signal(2 * t_read)
            self.sync.ret += [
                sdo_sr[1:].eq(sdo_sr),
                sdo_sr[0].eq(sdo),
            ]
            self.sync += [
                If(
                    update,
                    # flip the sign when latching out
                    [d.eq(~d_inv + 1) for d, d_inv in zip(self.data, self.data_inv)],
                )
            ]
            self.comb += [
                Cat(reversed([self.data_inv[i * k + j] for j in range(k)])).eq(sdo_sr)
            ]
