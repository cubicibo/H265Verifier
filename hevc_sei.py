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


from bitstream import BitReader

def parse_buffering_period_sei(br: BitReader, sps: dict[str, int]) -> dict[str, int]:
    buff_sei = {}

    buff_sei['bp_seq_parameter_set_id'] = br.read_ue()
    if not sps['vui']['vui_hrd_parameters_present_flag']:
        raise RuntimeError("Found Buffering SEI but HRD parameters missing.")
    hrd_params = sps['vui']['hrd_parameters'] # must be present
    
    initial_cpb_removal_delay_length = 1 + hrd_params['initial_cpb_removal_delay_length_minus1']
    au_cpb_removal_delay_length = 1 + hrd_params['au_cpb_removal_delay_length_minus1']
    dpb_removal_delay_length = 1 + hrd_params['dpb_output_delay_length_minus1']
    
    sub_pic_hrd_params_present_flag = hrd_params['sub_pic_hrd_params_present_flag']
    irap_cpb_params_present_flag = False if sub_pic_hrd_params_present_flag else br.read_bit()

    if irap_cpb_params_present_flag:
        buff_sei['cpb_delay_offset'] = br.read_bits(au_cpb_removal_delay_length)
        buff_sei['dpb_delay_offset'] = br.read_bits(dpb_removal_delay_length)
    else:
        irap_cpb_params_present_flag = False
        buff_sei['cpb_delay_offset'] = buff_sei['dpb_delay_offset'] = 0
    
    buff_sei['concatenation_flag'] = br.read_bit()
    buff_sei['au_cpb_removal_delay_delta_minus1'] = br.read_bits(au_cpb_removal_delay_length)
    
    if hrd_params['nal_hrd_parameters_present_flag']:
        layers = []
        for layer_hrd_params in hrd_params['sub_layer_hrd_parameters']:
            cpbs = []
            for CpbCount in range(layer_hrd_params['cpb_cnt_minus1']+1): 
                tid_params = {
                    'nal_initial_cpb_removal_delay': br.read_bits(initial_cpb_removal_delay_length),
                    'nal_initial_cpb_removal_offset':br.read_bits(initial_cpb_removal_delay_length),
                }
                if sub_pic_hrd_params_present_flag or irap_cpb_params_present_flag:
                    tid_params['nal_initial_alt_cpb_removal_delay'] = br.read_bits(initial_cpb_removal_delay_length)
                    tid_params['nal_initial_alt_cpb_removal_offset']= br.read_bits(initial_cpb_removal_delay_length)
                cpbs.append(tid_params)
            layers.append(cpbs)
        buff_sei |= {'NalHrdBp': layers}
    if hrd_params['vcl_hrd_parameters_present_flag']:
        raise NotImplementedError("VCL HRD not supported")
    return buff_sei

def parse_picture_timing_sei(br: BitReader, sps: dict[str, int]) -> dict[str, int]:
    vui = sps['vui']
    
    pic_timing = {}
    if vui['frame_field_info_present_flag']:
        pic_timing['pic_struct'] = br.read_bits(4)
        pic_timing['source_scan_type'] = br.read_bits(2)
        pic_timing['duplicate_flag'] = br.read_bits(1)
        
    hrd_params = vui['hrd_parameters']
    CpbDpbDelaysPresentFlag = hrd_params['nal_hrd_parameters_present_flag'] or hrd_params['vcl_hrd_parameters_present_flag']
    if CpbDpbDelaysPresentFlag:
        au_cpb_removal_delay_length = 1 + hrd_params['au_cpb_removal_delay_length_minus1']
        dpb_output_delay_length = 1 + hrd_params['dpb_output_delay_length_minus1']
        
        pic_timing['au_cpb_removal_delay_minus1'] = br.read_bits(au_cpb_removal_delay_length)
        pic_timing['pic_dpb_output_delay'] = br.read_bits(dpb_output_delay_length)
        
        if vui['hrd_parameters']['sub_pic_hrd_params_present_flag']:
            raise NotImplementedError("Sub pic HRD not implemneted")   
    return pic_timing
