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


from dataclasses import field, dataclass
from pathlib import Path

from typing import Generator

from bitstream import BitReader, remove_emulation_prevention
from common import AccessUnit, SEI

from hevc_internal import parse_sps, parse_vps, NALUnitType, parse_nal_unit_header, nal_requires_annexb_zero_byte, split_annexb_and_yield_nal
from hevc_sei import parse_buffering_period_sei, parse_picture_timing_sei

def yield_sei_units(rbsp: bytes) -> Generator[tuple[SEI | int, BitReader], None, None]:
    """
    This specific function was written by a LLM and is thereby under the MIT License.
    """
    br = BitReader(rbsp)

    while br.bitpos + 16 < len(rbsp) * 8:
        payload_type = 0
        while True:
            b = br.read_bits(8)
            payload_type += b
            if b != 0xFF:
                break

        payload_size = 0
        while True:
            b = br.read_bits(8)
            payload_size += b
            if b != 0xFF:
                break

        try:
            payload_type = SEI(payload_type)
        except ValueError:
            ...

        payload_start = br.bitpos
        payload_end = payload_start + payload_size * 8
        
        yield payload_type, br
        
        # don't use br as-is because it may not have done any parsing
        br.bitpos = payload_end
    return
####


#%% Primary parser and datastructure
@dataclass
class HEVCAccessUnit(AccessUnit):
    pic_type: int | None = None
    video_parameter_set: None | dict[str, ...] = None
    sequence_parameter_set: None | dict[str, ...] = None
    sei:  dict[str, dict[str, ...]] = field(default_factory=dict)   # sei_name -> sei_data
    misc: dict[str, ...] = field(default_factory=dict)   # user meta

class HEVCParser:
    def __init__(self, fp: Path | str) -> None:
        if not (fp := Path(fp)).exists():
            raise OSError("Input file does not exist.")
        self._fp = fp

    def __iter__(self) -> AccessUnit:
        yield from self.parse()

    def parse_stream(self, *args, **kwargs) -> list[AccessUnit]:
        return [au for au in self.parse(*args, **kwargs)]

    def get_timing_informations(self) -> dict[str, int]:
        """
        Returns:
        - time_scale: Number of time units per second.
        - num_units_in_tick: Number of time units per field (AVC is field based)

        time_scale / num_units_in_tick = fields per second = 2 * frames per second
        """
        au = next(iter(self))
        if au.sequence_parameter_set is None:
            raise RuntimeError("No SPS in first Access Unit.")
        vui = au.sequence_parameter_set.get('vui', {})
        if (hrd_parameters := vui.get('hrd_parameters', {})) is None:
            raise RuntimeError("No VUI or no HRD parameters.")

        for sublayer_hrd in hrd_parameters['sub_layer_hrd_parameters']:
            if sublayer_hrd['fixed_pic_rate_general_flag'] is False:
                raise RuntimeError("Pure VFR HEVC stream detected, not allowed.")
        return {
            'time_scale': vui['vui_time_scale'],
            'num_units_in_tick': vui['vui_num_units_in_tick']
        }

    def parse(self, parse_headers_once: bool = False) -> Generator[HEVCAccessUnit, None, None]:
        current_vps = current_sps = current_access_unit = None

        with open(self._fp, 'rb') as fio:
            for nalu in split_annexb_and_yield_nal(fio, f_requires_zero_byte=nal_requires_annexb_zero_byte):
                # drop start_code to ease indexing
                nal = nalu[4:] if nalu[2] == 0 else nalu[3:]
                nal_unit_type, nuh_layer_id, nuh_temporal_id_plus1 = parse_nal_unit_header(nal)
                match nal_unit_type:
                    case NALUnitType.AUD_NUT:
                        rbsp = BitReader(remove_emulation_prevention(nal[2:]))
                        if current_access_unit is not None:
                            yield current_access_unit
                        current_access_unit = HEVCAccessUnit(pic_type=nal[1] >> 5, misc={'nals':[]})
                    case NALUnitType.VPS_NUT:
                        if not parse_headers_once or current_vps is None:
                            rbsp = BitReader(remove_emulation_prevention(nal[2:]))
                            current_vps = current_access_unit.video_parameter_set = parse_vps(rbsp)
                            if current_vps['vps_max_layer_id'] > 0:
                                raise NotImplementedError("HEVC sublayers not supported.")
                    case NALUnitType.SPS_NUT:
                        if not parse_headers_once or current_sps is None:
                            rbsp = BitReader(remove_emulation_prevention(nal[2:]))
                            current_sps = current_access_unit.sequence_parameter_set = parse_sps(rbsp)
                    case NALUnitType.SEI_NUT:
                        rbsp = remove_emulation_prevention(nal[2:])
                        for sei_type, br in yield_sei_units(rbsp):
                            match sei_type:
                                case SEI.BufferingPeriod:
                                    current_access_unit.sei[sei_type] = parse_buffering_period_sei(br, current_sps)
                                case SEI.PictureTiming:
                                    current_access_unit.sei[sei_type] = parse_picture_timing_sei(br, current_sps)
                    ####case SEI
                current_access_unit.size += len(nalu)
                current_access_unit.misc['nals'].append(nal_unit_type)
                ####
            ####
        yield current_access_unit
    ####
####
