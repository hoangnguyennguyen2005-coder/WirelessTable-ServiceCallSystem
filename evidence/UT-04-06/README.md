# UT-04 to UT-06 evidence

| Test | Logs | What the results show |
| --- | --- | --- |
| [UT-04](../UT-04/) | [RF codec host](../UT-04/UT04_B_Gateway_Codec_Host_Rerun.log), [COM8 USB filtering](../UT-04/UT04_R01_COM8_USB_Filter_2026-11-26.log), [PC standalone](../UT-04/UT04_PC_Standalone_2026-11-26.log) | The host codec matched 31-byte reference frames and rejected bad inputs (28/28). The gateway rejected 5/5 invalid USB replies. PC checks passed 4/4. Full endpoint coverage remains pending. |
| [UT-05](../UT-05/) | [Pro Mini host trace](../UT-05/UT05_B_Table_Host_Trace_Extract.log), [PC standalone](../UT-05/UT05_PC_Standalone_2026-11-26.log) | The Pro Mini retry kept the same ID and received a reply at 4.010 s, within 5 s. Its loss indication took 10.8 s against a 10 s limit, so row 3 failed. The separate PC simulation passed 6/6. |
| [UT-06](../UT-06/) | [COM8 USB bench](../UT-06/UT06_R01_COM8_USB_Bench_2026-11-26.log), [R01 gateway host](../UT-06/UT06_B_R01_Gateway_Host_Rerun.log), [PC standalone](../UT-06/UT06_PC_Standalone_2026-11-26.log) | The physical USB bench passed 10/10, including split/joined frames, 4096/4097-byte limits and COM reopen. Host checks passed 13/13 and PC checks passed 4/4. The full live bridge test is blocked. |

The extracted files record their source lines. The [complete PC run](PBL4_UT04-06_PC_Standalone.log) and [complete COM8 capture](PBL4_UT04-06_R01_20261126_132505_453776.log) provide the original context.
