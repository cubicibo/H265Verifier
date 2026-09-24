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

def remove_emulation_prevention(rbsp: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(rbsp):
        next_pos = rbsp[i:].find(b'\x00\x00\x03')
        if next_pos >= 0:
            out += rbsp[i:i+next_pos+2]
            i += next_pos + 3
        else:
            out += rbsp[i:]
            break
    return bytes(out)

class BitReader:
    def __init__(self, data: bytes):
        self.data = data
        self.bitpos = 0

    def read_bits(self, n: int) -> int:
        val = 0
        for _ in range(n):
            byte_pos = self.bitpos >> 3
            bit_offset = 7 - (self.bitpos & 7)
            val = (val << 1) | ((self.data[byte_pos] >> bit_offset) & 1)
            self.bitpos += 1
        return val

    def read_bit(self) -> int:
        return self.read_bits(1)

    def read_ue(self) -> int:
        zeros = 0
        while self.read_bit() == 0:
            zeros += 1
        if zeros == 0:
            return 0
        return (1 << zeros) - 1 + self.read_bits(zeros)
####
