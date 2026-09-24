# H265Verifier
Python HEVC HRD verifier

- Only one temporal layer supported (single HRD)
- No bitstream concatenation whatsoever
- Bitstream must carry Picture Timing SEI and Buffering Period SEI, as required by the ITU H.265 standard for HRD verification.

### Command line interface
`client.py` is the command line entry point.

`python3 client.py [PARAMETERS] inputfile`

```
inputfile       HEVC bitstream with PicTiming SEI and BufferingPeriod SEI for HRD verification. [Mandatory]

 -l, --logfile  File to dump the HRD config and HSS (Hypothetical Stream Scheduler) plan of every access unit
 -p, --plot     Plot file output for the CPB occupancy through time ("VBV")
 -o, --offset   Offset the HRD initialization by [offset] Buffering Period. Default=0 (first buffering period initializes the HRD)
 -d, --dpb      File to dump DPB timing information (time given in readable timestamps)
```
