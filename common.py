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


from enum import IntEnum
from dataclasses import dataclass

class SEI(IntEnum):
    BufferingPeriod = 0
    PictureTiming = 1
    Filler = 3
    UserDataUnregistered = 5
    RecoveryPoint = 6
    DecRefPicMarking = 7

class MPEGClock(IntEnum):
    PTS = 90000
    STC = 27000000

@dataclass
class AccessUnit:
    size: int = 0
    
@dataclass
class TSPair:
    pts: int
    dts: int | None = None
    def __post_init__(self) -> None:
        if self.dts is None:
            self.dts = self.pts
    
    def get_pts_dts_flag(self) -> int:
        return 0b11 if self.pts != self.dts else 0b10
