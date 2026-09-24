"""
Copyright (C) 2026 cibo
This file is derived from BluFlow/HRDConf

This is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

It is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
alongside.  If not, see <http://www.gnu.org/licenses/>.
"""


from dataclasses import dataclass
from typing import Iterable, Any
from fractions import Fraction
from common import MPEGClock, SEI
from hevc import HEVCParser, HEVCAccessUnit

@dataclass(frozen=True)
class BufferingPeriod:
    InitialCpbRemovalDelay: int
    InitialCpbRemovalDelayOffset: int

    @classmethod
    def from_sei(cls, bp: dict[str, Any]) -> 'BufferingPeriod':
        hrd_bp = bp['NalHrdBp']
        assert len(hrd_bp) == 1, "Only one temporal layer supported"
        assert len(hrd_bp[0]) == 1, "Only one CPB supported"
        layer_cpb_init = hrd_bp[0][0]

        ini_cpb_rd = layer_cpb_init['nal_initial_cpb_removal_delay']
        ini_cpb_offset = layer_cpb_init['nal_initial_cpb_removal_offset']
        return cls(ini_cpb_rd, ini_cpb_offset)

@dataclass(frozen=True)
class HRD:
    ClockTick: Fraction
    CpbSize: int
    BitRate: int
    FixedPicRate: bool
    Cbr: bool
    InitialBP: BufferingPeriod
    
    @classmethod
    def initialize(cls, au: HEVCAccessUnit) -> 'HRD':
        hrd_parameters = au.sequence_parameter_set['vui']['hrd_parameters']
        baseCpbHrdParam =  hrd_parameters['sub_layer_hrd_parameters'][0]
        assert baseCpbHrdParam['fixed_pic_rate_general_flag'], "VFR not supported"

        bit_rate = (baseCpbHrdParam['bit_rate_value_minus1'] + 1) << (6 + hrd_parameters['bit_rate_scale'])
        cpb_size = (baseCpbHrdParam['cpb_size_value_minus1'] + 1) << (4 + hrd_parameters['cpb_size_scale'])

        cbr_flag = bool(baseCpbHrdParam['cbr_flag'])
        assert cbr_flag is False, "CBR HRD not implemented"

        clock_tick = Fraction(au.sequence_parameter_set['vui']['vui_num_units_in_tick'],
                              au.sequence_parameter_set['vui']['vui_time_scale'])
    
        initBP = BufferingPeriod.from_sei(au.sei[SEI.BufferingPeriod])
        return cls(clock_tick, cpb_size, bit_rate, baseCpbHrdParam['fixed_pic_rate_general_flag'], baseCpbHrdParam['cbr_flag'], initBP)

@dataclass(frozen=True)
class HSSAuPictureTiming:
    AuCpbEarliestArrivalTime: Fraction
    AuCpbNominalRemovalTime: Fraction
    DpbOutputTime: Fraction
    AuCpbFill: Fraction
    AuFinalArrivalTime: Fraction
    DpbDurationTicks: int = 1

@dataclass(frozen=True)
class HrdHssStream:
    hrd: HRD
    hss: list[HSSAuPictureTiming]

    def test_dpb(self) -> bool:
        """
        Test C.3.3: Picture Output
        """
        assert self.hrd.FixedPicRate, "DPB analysis supported only with fixed pic rate"
        last_display_timestamp = None
        DisplayPicCount = 0
        is_stream_cfr = True
        for au_poc_order in sorted(self.hss, key=lambda au: au.DpbOutputTime):
            if last_display_timestamp != au_poc_order.DpbOutputTime:
                if last_display_timestamp is None:
                    last_display_timestamp = au_poc_order.DpbOutputTime
                else:
                    print(f"DPB output time GAP after access unit at DisplayPicCount {DisplayPicCount}.")
                    is_stream_cfr = False
                    break
            last_display_timestamp += au_poc_order.DpbDurationTicks * self.hrd.ClockTick
            DisplayPicCount += au_poc_order.DpbDurationTicks
        return is_stream_cfr

    def evaluate_cpb(self) -> tuple[list[int], list[int], bool]:
        """
        Evaluate the CPB usage
        Get CPB buffer occupancy (Y) at time (X)
        """
        hss = self.hss
        hrd = self.hrd
        assert len(hss), "Empty stream (no access unit)"
        
        X = [0]
        Y = [0]

        for au_timing in hss:
            fill_duration = au_timing.AuCpbFill
            X.append(au_timing.AuFinalArrivalTime)
            Y.append(fill_duration * hrd.BitRate)

        # amend with the removal time of each access unit, and carry the removed size
        offset = 0
        for au_timing in hss:
            while len(X) > offset and X[offset] <= au_timing.AuCpbNominalRemovalTime:
                offset += 1
            
            X[offset:offset] = [au_timing.AuCpbNominalRemovalTime]
            Y[offset:offset] = [-1 * au_timing.AuCpbFill * hrd.BitRate]
        
        cumsum = Fraction(0, 1)
        valid = True
        for k in range(len(Y)):
            step = Y[k]
            Y[k] += cumsum
            cumsum += step
            if Y[k] > hrd.CpbSize:
                print("CPB overflow at {float(X[k]):.03f}: {Y[k]} > {hrd.CpbSize}.")
                valid = False
            if Y[k] < 0:
                print("CPB underflow at {float(X[k]):.03f}: {Y[k]} < 0.")
                valid = False
        return X, Y, valid

    def plot(self, X, Y, file: str) -> None:
        import matplotlib
        if file is not None:
            matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.plot(X, Y, linewidth=0.6)
        ax = plt.gca()
        cpbRemDel = self.hrd.InitialBP.InitialCpbRemovalDelay/90e3
        plt.vlines(cpbRemDel, 0, self.hrd.CpbSize, 'black', linestyles='dashed')
        plt.hlines(self.hrd.CpbSize, 0, X[-1],'red', linestyles='dashed')
        plt.text(0, self.hrd.CpbSize*1.01, "cpbSize", color='red')
        plt.text(cpbRemDel*1.05, self.hrd.CpbSize*0.01, 'initCpbRemDel', color='black')
        plt.fill_between([float(x) for x in X], 0, [float(y) for y in Y], alpha=0.5, linewidth=0.5, zorder=2,)
        
        if len(self.hss) < 110:
            lines = ax.vlines([timing.AuCpbNominalRemovalTime for timing in self.hss], 0, self.hrd.CpbSize, 'black', linestyles='dotted', linewidth=0.5)
            lines.set_label('cpbRemovalTime')
            plt.legend(loc=(0.775, 0.96), prop={'size': 6})
        ax.set_ylim(0,)
        ax.set_title("CPB usage")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Bits in buffer")
        plt.grid()
        if not file:
            plt.show()
        else:
            plt.savefig(file, dpi=350)

class StreamScheduler:
    def __init__(self, hstream: HEVCParser, gop_offset: int = 0) -> None:
        self._stream = hstream
        self.gop_offset = gop_offset
    
    def get_au_iterable(self) -> Iterable[HEVCAccessUnit]:
        iau = iter(self._stream)

        skipped = 0
        while skipped < self.gop_offset:
            try:
                au = next(iau)
            except StopIteration:
                return iter([])
            else:
                if SEI.BufferingPeriod in au.sei:
                    skipped += 1
        return iau

    def get_hrd(self) -> HRD | None:
        for au in self.get_au_iterable():
            if SEI.BufferingPeriod in au.sei:
                return HRD.initialize(au)        

    def get_all_access_units(self) -> None:
        stream = []
        found_bp = False
        for au in self.get_au_iterable():
            if found_bp or SEI.BufferingPeriod in au.sei:
                found_bp = True
                stream.append(au)
        return stream

    def test_buffering_period(self, hrd_hss: HrdHssStream) -> bool:
        """
        Test that every buffering period is a valid starting point
        (Section C.4: Bitstream conformance)
        """
        iau = self.get_au_iterable()
        hrd = hrd_hss.hrd
        first_bp = True
        AuFinalArrivalTimePrev = None

        all_valid = True
        for k, (au, timing) in enumerate(zip(iau, hrd_hss.hss)):
            if SEI.BufferingPeriod in au.sei:
                bp = BufferingPeriod.from_sei(au.sei[SEI.BufferingPeriod])
                if not first_bp:
                    delta_time = 90000 * (timing.AuCpbNominalRemovalTime - AuFinalArrivalTimePrev)
                    ceiled_delta_time = int(delta_time) + (1 if int(delta_time) < delta_time else 0)
                    valid = bp.InitialCpbRemovalDelay <= ceiled_delta_time
                    if hrd.Cbr:
                        valid = valid and int(delta_time) <= bp.InitialCpbRemovalDelay
                    
                    if not valid:
                        print(f"Access Unit {k} with Buffering Period SEI breaches C-17/18: InitialCpbRemovalDelay={bp.InitialCpbRemovalDelay} > deltaTime90k={ceiled_delta_time}.")
                        all_valid = False
                first_bp = False
            AuFinalArrivalTimePrev = timing.AuFinalArrivalTime
        return all_valid

    def get_hypothetical_stream_scheduling(self) -> list[HSSAuPictureTiming]:
        """
        Perform C.2.x: Operation of the CPB
        """
        hrd = None
        AuFinalArrivalTime = 0

        hss_timing = []
        for au in self.get_au_iterable():
            has_buffering_period = SEI.BufferingPeriod in au.sei
            initialize_hrd = False
            if hrd is None:
                if has_buffering_period:
                    hrd = HRD.initialize(au)
                    initialize_hrd = True
                else:
                    continue
            
            picture_timing = au.sei[SEI.PictureTiming]
        
            if initialize_hrd:
                buffering_period = BufferingPeriod.from_sei(au.sei[SEI.BufferingPeriod])
                AuNominalRemovalTime = Fraction(buffering_period.InitialCpbRemovalDelay, MPEGClock.PTS) # C-9
                AuNominalRemovalTimeFirstPicInThisBuffPeriod = AuNominalRemovalTime
                initArrivalEarliestTime = Fraction(0, 1)
            else:
                AuCpbRemovalDelay = 1 + picture_timing['au_cpb_removal_delay_minus1']
    
                # C-10
                AuNominalRemovalTime = AuNominalRemovalTimeFirstPicInThisBuffPeriod
                AuNominalRemovalTime += hrd.ClockTick * AuCpbRemovalDelay
    
                initArrivalEarliestTime = AuNominalRemovalTime
                if has_buffering_period:
                    buffering_period = BufferingPeriod.from_sei(au.sei[SEI.BufferingPeriod])
                    initArrivalEarliestTime -= Fraction(buffering_period.InitialCpbRemovalDelay, MPEGClock.PTS) # Eq. C-7
    
                    # update for subsequent pictures in this buffering period
                    AuNominalRemovalTimeFirstPicInThisBuffPeriod = AuNominalRemovalTime
                else:
                    # C-6
                    initArrivalEarliestTime -= Fraction(buffering_period.InitialCpbRemovalDelay + buffering_period.InitialCpbRemovalDelayOffset, MPEGClock.PTS) # Eq. C-6
    
            # C-15
            DpbOutputTime = AuNominalRemovalTime + picture_timing['pic_dpb_output_delay'] * hrd.ClockTick

            # C-7 Picture can only arrive after the previous
            initArrivalTime = max(initArrivalEarliestTime, AuFinalArrivalTime)
    
            # C-8 duration of the fill for this access unit
            AuCpbFill = Fraction(8*au.size, hrd.BitRate)
            AuFinalArrivalTime = initArrivalTime + AuCpbFill

            # no low delay, the last possible arrival time is the cpb removal time
            if AuFinalArrivalTime > AuNominalRemovalTime:
                print(f"CPB underflow for access unit {len(hss_timing)}")
            
            # returns progressive if frame_field_info chunk is not present
            DpbDurationTicks = [1, 1, 1, 2, 2, 3, 3, 2, 3, 1, 1, 1, 1][picture_timing.get('pic_struct', 0)]
            hss_timing.append(HSSAuPictureTiming(initArrivalTime, AuNominalRemovalTime, DpbOutputTime, AuCpbFill, AuFinalArrivalTime, DpbDurationTicks))
        return HrdHssStream(hrd, hss_timing)