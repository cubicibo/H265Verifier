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


from typing import Any, BinaryIO, Generator, Callable
from bitstream import BitReader
from enum import IntEnum


class NALUnitType(IntEnum):
    TRAIL_N = 0
    TRAIL_R = 1
    TSA_N   = 2
    TSA_R   = 3
    STSA_N  = 4
    STSA_R  = 5
    RADL_N  = 6
    RADL_R  = 7
    RASL_N  = 8
    RASL_R  = 9
    BLA_W_LP = 16
    BLA_W_RADL=17
    BLA_N_LP = 18
    IDR_W_RADL=19
    IDR_N_LP= 20
    CRA_NUT = 21
    VPS_NUT = 32
    SPS_NUT = 33
    PPS_NUT = 34
    AUD_NUT = 35
    EOS_NUT = 36
    EOB_NUT = 37
    FD_NUT  = 38
    SEI_NUT = 39
    unk_nal_type=63

    def _missing_(cls, v: ...) -> 'NALUnitType':
        return cls(63)

def parse_nal_unit_type(nal_first_byte) -> NALUnitType:
    assert nal_first_byte >> 7 == 0, "forbidden_zero_bit not zero"
    return NALUnitType((nal_first_byte >> 1) & 0x3F)

def nal_requires_annexb_zero_byte(nal_unit_type: NALUnitType) -> bool:
    return nal_unit_type in (NALUnitType.AUD_NUT, NALUnitType.VPS_NUT,
                             NALUnitType.SPS_NUT, NALUnitType.PPS_NUT)

def parse_nal_unit_header(nal: bytes) -> list[int]:
    return parse_nal_unit_type(nal[0]), (nal[1] >> 3) | (nal[0] & 1) << 5, (nal[1] & 0b111)

def parse_vps(bs: BitReader):
    vps = {}

    vps["vps_video_parameter_set_id"] = bs.read_bits(4)
    vps["vps_base_layer_internal_flag"] = bs.read_bit()
    vps["vps_base_layer_available_flag"] = bs.read_bit()
    vps["vps_max_layers_minus1"] = bs.read_bits(6)
    vps["vps_max_sub_layers_minus1"] = bs.read_bits(3)
    vps["vps_temporal_id_nesting_flag"] = bs.read_bit()
    vps["vps_reserved_0xffff_16bits"] = bs.read_bits(16)

    vps["profile_tier_level"] = parse_profile_tier_level(
        bs, vps["vps_max_sub_layers_minus1"]
    )

    vps["vps_sub_layer_ordering_info_present_flag"] = bs.read_bit()

    start = 0 if vps["vps_sub_layer_ordering_info_present_flag"] else vps["vps_max_sub_layers_minus1"]

    vps["sub_layer_ordering_info"] = []
    for i in range(start, vps["vps_max_sub_layers_minus1"] + 1):
        layer = {}
        layer["vps_max_dec_pic_buffering_minus1"] = bs.read_ue()
        layer["vps_max_num_reorder_pics"] = bs.read_ue()
        layer["vps_max_latency_increase_plus1"] = bs.read_ue()
        vps["sub_layer_ordering_info"].append(layer)

    vps["vps_max_layer_id"] = bs.read_bits(6)
    vps["vps_num_layer_sets_minus1"] = bs.read_ue()

    vps["layer_id_included_flag"] = []
    for i in range(vps["vps_num_layer_sets_minus1"] + 1):
        flags = []
        for j in range(vps["vps_max_layer_id"] + 1):
            flags.append(bs.read_bit())
        vps["layer_id_included_flag"].append(flags)

    vps["vps_timing_info_present_flag"] = bs.read_bit()

    if vps["vps_timing_info_present_flag"]:
        vps["vps_num_units_in_tick"] = bs.read_bits(32)
        vps["vps_time_scale"] = bs.read_bits(32)
        vps["vps_poc_proportional_to_timing_flag"] = bs.read_bit()
        if vps["vps_poc_proportional_to_timing_flag"]:
            vps["vps_num_ticks_poc_diff_one_minus1"] = bs.read_ue()
        vps["vps_num_hrd_parameters"] = bs.read_ue()
        vps["hrd_parameters"] = []
        for i in range(vps["vps_num_hrd_parameters"]):
            hrd = {}
            hrd["hrd_layer_set_idx"] = bs.read_ue()
            if i > 0:
                hrd["cprms_present_flag"] = bs.read_bit()
            else:
                hrd["cprms_present_flag"] = True
            hrd["hrd"] = parse_hrd_parameters(bs, True,
                                              vps["vps_max_sub_layers_minus1"])
            vps["hrd_parameters"].append(hrd)

    vps["vps_extension_flag"] = bs.read_bit()

    return vps
def parse_sps(bs: BitReader):
    sps = {}

    sps["sps_video_parameter_set_id"] = bs.read_bits(4)
    sps["sps_max_sub_layers_minus1"] = bs.read_bits(3)
    sps["sps_temporal_id_nesting_flag"] = bs.read_bit()
    sps["profile_tier_level"] = parse_profile_tier_level(bs, sps["sps_max_sub_layers_minus1"])

    sps["sps_seq_parameter_set_id"] = bs.read_ue()
    sps["chroma_format_idc"] = bs.read_ue()
    if sps["chroma_format_idc"] == 3:
        sps["separate_colour_plane_flag"] = bs.read_bit()

    sps["pic_width_in_luma_samples"] = bs.read_ue()
    sps["pic_height_in_luma_samples"] = bs.read_ue()

    sps["conformance_window_flag"] = bs.read_bit()
    if sps["conformance_window_flag"]:
        sps["conf_win_left_offset"] = bs.read_ue()
        sps["conf_win_right_offset"] = bs.read_ue()
        sps["conf_win_top_offset"] = bs.read_ue()
        sps["conf_win_bottom_offset"] = bs.read_ue()

    sps["bit_depth_luma_minus8"] = bs.read_ue()
    sps["bit_depth_chroma_minus8"] = bs.read_ue()
    sps["log2_max_pic_order_cnt_lsb_minus4"] = bs.read_ue()

    start = 0
    sps["sps_sub_layer_ordering_info_present_flag"] = bs.read_bit()
    if not sps["sps_sub_layer_ordering_info_present_flag"]:
        start = sps["sps_max_sub_layers_minus1"]

    sps["sub_layer_ordering_info"] = []
    for i in range(start, sps["sps_max_sub_layers_minus1"] + 1):
        layer = {}
        layer["sps_max_dec_pic_buffering_minus1"] = bs.read_ue()
        layer["sps_max_num_reorder_pics"] = bs.read_ue()
        layer["sps_max_latency_increase_plus1"] = bs.read_ue()
        sps["sub_layer_ordering_info"].append(layer)

    sps["log2_min_luma_coding_block_size_minus3"] = bs.read_ue()
    sps["log2_diff_max_min_luma_coding_block_size"] = bs.read_ue()
    sps["log2_min_luma_transform_block_size_minus2"] = bs.read_ue()
    sps["log2_diff_max_min_luma_transform_block_size"] = bs.read_ue()
    sps["max_transform_hierarchy_depth_inter"] = bs.read_ue()
    sps["max_transform_hierarchy_depth_intra"] = bs.read_ue()

    sps["scaling_list_enabled_flag"] = bs.read_bit()
    if sps["scaling_list_enabled_flag"]:
        sps["sps_scaling_list_data_present_flag"] = bs.read_bit()
        if sps["sps_scaling_list_data_present_flag"]:
            raise NotImplementedError

    sps["amp_enabled_flag"] = bs.read_bit()
    sps["sample_adaptive_offset_enabled_flag"] = bs.read_bit()
    sps["pcm_enabled_flag"] = bs.read_bit()
    if sps["pcm_enabled_flag"]:
        sps["pcm_sample_bit_depth_luma_minus1"] = bs.read_bits(4)
        sps["pcm_sample_bit_depth_chroma_minus1"] = bs.read_bits(4)
        sps["log2_min_pcm_luma_coding_block_size_minus3"] = bs.read_ue()
        sps["log2_diff_max_min_pcm_luma_coding_block_size"] = bs.read_ue()
        sps["pcm_loop_filter_disabled_flag"] = bs.read_bit()

    sps["num_short_term_ref_pic_sets"] = bs.read_ue()
    if sps["num_short_term_ref_pic_sets"] > 0:
        raise NotImplementedError

    sps["long_term_ref_pics_present_flag"] = bs.read_bit()
    if sps["long_term_ref_pics_present_flag"]:
        sps["num_long_term_ref_pics_sps"] = bs.read_ue()
        sps["lt_ref_pic"] = []
        for _ in range(sps["num_long_term_ref_pics_sps"]):
            entry = {}
            entry["lt_ref_pic_poc_lsb_sps"] = bs.read_bits(
                sps["log2_max_pic_order_cnt_lsb_minus4"] + 4
            )
            entry["used_by_curr_pic_lt_sps_flag"] = bs.read_bit()
            sps["lt_ref_pic"].append(entry)

    sps["sps_temporal_mvp_enabled_flag"] = bs.read_bit()
    sps["strong_intra_smoothing_enabled_flag"] = bs.read_bit()

    sps["vui_parameters_present_flag"] = bs.read_bit()
    if sps["vui_parameters_present_flag"]:
        sps["vui"] = parse_vui_parameters(bs, sps["sps_max_sub_layers_minus1"])
    return sps

def parse_vui_parameters(
        bs: BitReader,
        max_sub_layers_minus1: int
    ) -> dict[str, Any]:
    vui = {}

    vui["aspect_ratio_info_present_flag"] = bs.read_bit()
    if vui["aspect_ratio_info_present_flag"]:
        vui["aspect_ratio_idc"] = bs.read_bits(8)
        if vui["aspect_ratio_idc"] == 255:
            vui["sar_width"] = bs.read_bits(16)
            vui["sar_height"] = bs.read_bits(16)

    vui["overscan_info_present_flag"] = bs.read_bit()
    if vui["overscan_info_present_flag"]:
        vui["overscan_appropriate_flag"] = bs.read_bit()

    vui["video_signal_type_present_flag"] = bs.read_bit()
    if vui["video_signal_type_present_flag"]:
        vui["video_format"] = bs.read_bits(3)
        vui["video_full_range_flag"] = bs.read_bit()
        
        vui["colour_description_present_flag"] = bs.read_bit()
        if vui["colour_description_present_flag"]:
            vui["colour_primaries"] = bs.read_bits(8)
            vui["transfer_characteristics"] = bs.read_bits(8)
            vui["matrix_coeffs"] = bs.read_bits(8)

    vui["chroma_loc_info_present_flag"] = bs.read_bit()
    if vui["chroma_loc_info_present_flag"]:
        vui["chroma_sample_loc_type_top_field"] = bs.read_ue()
        vui["chroma_sample_loc_type_bottom_field"] = bs.read_ue()

    vui["neutral_chroma_indication_flag"] = bs.read_bit()
    vui["field_seq_flag"] = bs.read_bit()
    vui["frame_field_info_present_flag"] = bs.read_bit()

    vui["default_display_window_flag"] = bs.read_bit()
    if vui["default_display_window_flag"]:
        vui["def_disp_win_left_offset"] = bs.read_ue()
        vui["def_disp_win_right_offset"] = bs.read_ue()
        vui["def_disp_win_top_offset"] = bs.read_ue()
        vui["def_disp_win_bottom_offset"] = bs.read_ue()

    vui["vui_timing_info_present_flag"] = bs.read_bit()
    if vui["vui_timing_info_present_flag"]:
        vui["vui_num_units_in_tick"] = bs.read_bits(32)
        vui["vui_time_scale"] = bs.read_bits(32)
        
        vui["vui_poc_proportional_to_timing_flag"] = bs.read_bit()
        if vui["vui_poc_proportional_to_timing_flag"]:
            vui["vui_num_ticks_poc_diff_one_minus1"] = bs.read_ue()
        
        vui["vui_hrd_parameters_present_flag"] = bs.read_bit()
        if vui["vui_hrd_parameters_present_flag"]:
            vui["hrd_parameters"] = parse_hrd_parameters(
                bs, True, max_sub_layers_minus1
            )

    vui["bitstream_restriction_flag"] = bs.read_bit()
    if vui["bitstream_restriction_flag"]:
        vui["tiles_fixed_structure_flag"] = bs.read_bit()
        vui["motion_vectors_over_pic_boundaries_flag"] = bs.read_bit()
        vui["restricted_ref_pic_lists_flag"] = bs.read_bit()
        vui["min_spatial_segmentation_idc"] = bs.read_ue()
        vui["max_bytes_per_pic_denom"] = bs.read_ue()
        vui["max_bits_per_min_cu_denom"] = bs.read_ue()
        vui["log2_max_mv_length_horizontal"] = bs.read_ue()
        vui["log2_max_mv_length_vertical"] = bs.read_ue()
    return vui

def parse_profile_tier_level(bs: BitReader, max_sub_layers_minus1: int) -> dict[str, Any]:
    ptl = {}
    ptl["general_profile_space"] = bs.read_bits(2)
    ptl["general_tier_flag"] = bs.read_bit()
    ptl["general_profile_idc"] = bs.read_bits(5)
    ptl["general_profile_compatibility_flags"] = bs.read_bits(32)
    ptl["general_constraint_indicator_flags"] = bs.read_bits(48)
    ptl["general_level_idc"] = bs.read_bits(8)

    ptl["sub_layer_profile_present_flag"] = []
    ptl["sub_layer_level_present_flag"] = []

    for i in range(max_sub_layers_minus1):
        ptl["sub_layer_profile_present_flag"].append(bs.read_bit())
        ptl["sub_layer_level_present_flag"].append(bs.read_bit())

    if max_sub_layers_minus1 > 0:
        for _ in range(max_sub_layers_minus1, 8):
            bs.read_bits(2)

    ptl["sub_layers"] = []
    for i in range(max_sub_layers_minus1):
        sub = {}
        if ptl["sub_layer_profile_present_flag"][i]:
            sub["sub_layer_profile_space"] = bs.read_bits(2)
            sub["sub_layer_tier_flag"] = bs.read_bit()
            sub["sub_layer_profile_idc"] = bs.read_bits(5)
            sub["sub_layer_profile_compatibility_flags"] = bs.read_bits(32)
            sub["sub_layer_constraint_indicator_flags"] = bs.read_bits(48)
        if ptl["sub_layer_level_present_flag"][i]:
            sub["sub_layer_level_idc"] = bs.read_bits(8)
        ptl["sub_layers"].append(sub)
    return ptl

def parse_hrd_parameters(
        bs: BitReader,
        common_inf_present_flag: bool,
        max_sub_layers_minus1: int
    ) -> dict[str, Any]:
    hrd = {}
    if common_inf_present_flag:
        hrd["nal_hrd_parameters_present_flag"] = bs.read_bit()
        hrd["vcl_hrd_parameters_present_flag"] = bs.read_bit()

        if (hrd["nal_hrd_parameters_present_flag"] or
                hrd["vcl_hrd_parameters_present_flag"]):

            hrd["sub_pic_hrd_params_present_flag"] = bs.read_bit()
            if hrd["sub_pic_hrd_params_present_flag"]:
                hrd["tick_divisor_minus2"] = bs.read_bits(8)
                hrd["du_cpb_removal_delay_increment_length_minus1"] = bs.read_bits(5)
                hrd["sub_pic_cpb_params_in_pic_timing_sei_flag"] = bs.read_bit()
                hrd["dpb_output_delay_du_length_minus1"] = bs.read_bits(5)

            hrd["bit_rate_scale"] = bs.read_bits(4)
            hrd["cpb_size_scale"] = bs.read_bits(4)
            if hrd["sub_pic_hrd_params_present_flag"]:
                hrd["cpb_size_du_scale"] = bs.read_bits(4)
            hrd["initial_cpb_removal_delay_length_minus1"] = bs.read_bits(5)
            hrd["au_cpb_removal_delay_length_minus1"] = bs.read_bits(5)
            hrd["dpb_output_delay_length_minus1"] = bs.read_bits(5)

    hrd["sub_layer_hrd_parameters"] = []
    for i in range(max_sub_layers_minus1 + 1):
        layer = {}
        layer["fixed_pic_rate_general_flag"] = bs.read_bit()
        if not layer["fixed_pic_rate_general_flag"]:
            layer["fixed_pic_rate_within_cvs_flag"] = bs.read_bit()
        if layer.get("fixed_pic_rate_within_cvs_flag", True):
            layer["elemental_duration_in_tc_minus1"] = bs.read_ue()
        else:
            layer["low_delay_hrd_flag"] = bs.read_bit()
        if not layer.get("low_delay_hrd_flag", False):
            layer["cpb_cnt_minus1"] = bs.read_ue()
        if hrd["nal_hrd_parameters_present_flag"]:
            layer['bit_rate_value_minus1'] = bs.read_ue()
            layer['cpb_size_value_minus1'] = bs.read_ue()
            if hrd['sub_pic_hrd_params_present_flag']:
                layer['cpb_size_du_value_minus1'] = bs.read_ue()
                layer['bit_rate_du_value_minus1'] = bs.read_ue()
            layer['cbr_flag'] = bs.read_bit()
        hrd["sub_layer_hrd_parameters"].append(layer)
    return hrd


def split_annexb_and_yield_nal(
        fp: BinaryIO,
        chunk_size: int = 4 << 20,
        f_requires_zero_byte: Callable[[bytes | bytearray], bool] = lambda *args, **kwargs : False
    ) -> Generator[bytes, None, None]:
    assert chunk_size >= 4096, "chunk_size shall at least be 4 KiB." 
    bytestream = bytearray(fp.read(chunk_size))
    start_pos = bytestream.find(b'\x00\x00\x01')
    if f_requires_zero_byte(bytestream[start_pos+3]):
        start_pos -= 1
        assert start_pos >= 0 and bytestream[start_pos] == 0, "Incorrect start code for NALU."

    while True:
        end_pos = bytestream.find(b'\x00\x00\x01', start_pos+3)
        
        # look ahead next NAL_unit_type to not steal its zero_byte
        if end_pos != -1:
            if f_requires_zero_byte(bytestream[end_pos+3]):
                end_pos -= 1
                assert bytestream[end_pos] == 0, "Incorrect start code for NALU."
            yield bytes(bytestream[start_pos:end_pos])
            bytestream = bytestream[end_pos:]
        else:
            new_data = fp.read(chunk_size)
            if len(new_data):
                bytestream += new_data
                continue
            yield bytes(bytestream[start_pos:])
            break
        start_pos = 0
    ####
####
