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

from hevc import HEVCParser, HEVCAccessUnit
from hrd import StreamScheduler, HrdHssStream

import sys
from pathlib import Path
from argparse import ArgumentParser

def dump_dpb(dpb_dump: Path, access_units: list[HEVCAccessUnit], hrd_hss: HrdHssStream) -> None:
    assert len(access_units) == len(hrd_hss.hss), f"{len(hrd_hss.hss)} {len(access_units)}" 
    from datetime import timedelta
    
    tick = hrd_hss.hrd.ClockTick
    first_pts = None
    
    with open(dpb_dump, 'w') as f:
        f.write(f"Display Framerate={tick**-1}\nCodedIx NUT\n")
        for k, au_timing in sorted(enumerate(hrd_hss.hss), key=lambda p: p[1].DpbOutputTime):
            if first_pts is None:
                first_pts = au_timing.DpbOutputTime
            f.write(f"{k:4}  {access_units[k].misc['nals'][-1].name} PTS={timedelta(seconds=float(au_timing.DpbOutputTime-first_pts))}, duration={float(au_timing.DpbDurationTicks*tick):.03f}\n")

def test_conformance(args) -> tuple[HrdHssStream, bool]:
    hevc_stream = HEVCParser(args.input)
    scheduler = StreamScheduler(hevc_stream, args.offset)
    hrd_hss = scheduler.get_hypothetical_stream_scheduling()
    X, Y, valid = hrd_hss.evaluate_cpb()
    if valid:
        valid = hrd_hss.test_dpb()
    if args.plot is not None:
        hrd_hss.plot(X, Y, args.plot)
    if valid:
        valid = scheduler.test_buffering_period(hrd_hss)
    if args.dpb:
        dump_dpb(args.dpb, scheduler.get_all_access_units(), hrd_hss)
    return hrd_hss, valid

def parse_args():
    def fmt_path_input(fp: str) -> Path:
        fp = Path(fp).expanduser().resolve()
        if fp.exists():
            return fp
        else:
            raise FileNotFoundError("Input bitstream file does not exist.")
            
    def fmt_path_output(fp: str) -> Path:
        fp = Path(fp).expanduser().resolve()
        if fp.parent.exists():
            return fp
        else:
            raise RuntimeError("Parent directory of output file does not exist.")
    
    parser = ArgumentParser()
    parser.add_argument('-l', '--logfile', help="Dump the HRD datastructures to a log file.", type=fmt_path_output, required=False, default=None)
    parser.add_argument('-p', '--plot', help="Output CPB (VBV) plot to file.", type=fmt_path_output, required=False, default=None)
    parser.add_argument('-o', '--offset', help="GOP (Buffering Period) to start from, default is first gop (0).", type=int, default=0)
    parser.add_argument('-d', '--dpb', help="Dump DPB timing and frame types to a file.", type=fmt_path_output, default=None, required=False)
    parser.add_argument('input', help="HEVC bitstream to verify", type=fmt_path_input)
    return parser.parse_args()

def dump_content(logfile: Path, hrd_hss: HrdHssStream) -> None:
    with open(logfile, 'w') as f:
        f.write("== HRD ==\n")
        f.write(repr(hrd_hss.hrd))
        f.write("\n\n== HSS ==\n")
        for timing in hrd_hss.hss:
            f.write(repr(timing))
            f.write("\n")
####

valid = False
if __name__ == '__main__':
    args = parse_args()
    hh, valid = test_conformance(args)
    if args.logfile:
        dump_content(args.logfile, hh)
    if valid:
        print("OK")
    else:
        print("! NOT conformant (see logs) !")

sys.exit(int(not valid))
