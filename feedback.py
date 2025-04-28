from artiq.experiment import *



class Phaser(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("phaser0")

    @rpc(flags={"async"})
    def p(self, *p):
        print([hex(_ & 0xFFFFFFFF) for _ in p])

    def run(self):
        self.do()

    @kernel
    def do(self):
        # self.core.reset()
        self.core.break_realtime()

        ch = 0
        osc = 0

        ph = self.phaser0

        ph.init(debug=True)

        ph.channel[ch].set_att(0 * dB)
        ph.channel[ch].set_duc_frequency(100 * MHz)
        ph.channel[ch].set_duc_phase(0.25)
        ph.channel[ch].set_duc_cfg(select=0, clr=0)
        delay(0.1 * ms)

        ph.duc_stb()

        ftw = 1.0 * MHz
        asf = 0.99
        ph.channel[ch].oscillator[osc].set_frequency(ftw)
        delay(0.1 * ms)
        ph.channel[ch].oscillator[osc].set_amplitude_phase(asf, phase=0.25, clr=0)
        delay(0.1 * ms)
