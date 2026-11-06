# Hardware integration / chưa kiểm chứng
PC software implements pyserial read/write, bounded NDJSON parser, reconnect and persistent outbox. No firmware sources or hardware supplied. Không có logbook, pinout, radio channel/address settings để xác minh. Không viết firmware giả theo pin tưởng tượng.

## Kết nối thật
1. Build frontend, run hardware profile on PC at quán; no Internet required at runtime.
2. Register tables with node IDs and staff via Cấu hình; hardware DB initially empty.
3. Set PBL_MODE=hardware,PBL_SERIAL_PORT=COM3 (Windows) or /dev/ttyACM0 (Linux),PBL_SERIAL_BAUD=115200. Value baud is proposed, must match gateway firmware.
4. Stop serial monitor applications before starting server. Linux account must already have port permission (operator config, app does not modify system groups).
5. Implement protocol.md on ESP32-C3 USB and compact RF translation. Pro Mini hold5s/poll active5s/double hidden600ms defaults need firmware confirmation. Concept C power/clock unchanged.
6. Optional hardware staff web prototype requires server PBL_STAFF_TOKEN/PBL_STAFF_ID and matching token input. It is not a complete physical staff device firmware.

## Software serial emulator
Linux terminal A: `.venv/bin/python tools/serial_emulator.py --pty`; copy printed `/dev/pts/N` to PBL_SERIAL_PORT of hardware server in terminal B. Register node1 in UI. Type `call 1`, ACK in manager, assign/accept via staff prototype if configured, type `done 1`. Node emulator polls while active and sends applied evidence; all marked EMULATED. `fragment 1`, `bad`, `oversized`, `duplicate` exercise parser/dedup. `--no-apply` tests waiting-for-device UI.
On Windows the real COM adapter works with pyserial. For emulator use Linux PTY/WSL or a separately supplied virtual-port pair; interactive emulator's select loop is Linux only (not a Windows COM-pair driver).

## Handover checklist (hardware tests pending)
- CALL receipt only after durable commit, including host restart and duplicate packets.
- Red LED after receipt; manager ACK→next active poll→green; verify STATUS_APPLIED.
- Real hold4.9s cancel,5s CALL; debounce and two hidden presses window verified.
- DONE receipt loss/retry, green stays until receipt, no false closing newer call.
- USB unplug/reconnect, outbox persistence, radio packet duplicates and boot correlation loss recovery.
- Staff device transport/identity/notification delivery/accept revision validation.
- RF range, RF latency, delivery success, idle/active current, battery lifetime and firmware interoperability: **CHƯA ĐO/CHƯA XÁC MINH**.
Software fake transports, PTY and browser tests do not replace these measurements.
