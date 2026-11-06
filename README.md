# PBL4 — Gọi phục vụ

MVP Wireless Table Call Service (ECE411), **Concept C**: Pro Mini → nRF24L01+ → ESP32-C3 → USB serial → PC tại quán. Backend FastAPI/SQLite, dashboard React tiếng Việt, SSE và prototype web nhân viên. Runtime không cần Internet. Dữ liệu nằm ở backend, không dùng localStorage làm database.

Đã kiểm tra trong Linux với Python **3.12.14**, Node **24.22.1**, npm **11.9.0**, Chromium hệ thống. Khuyến nghị Python3.12+, Node22.12+/24. Windows PowerShell có hướng dẫn dưới; chưa chạy kiểm chứng Windows/USB thật.

## Cài dependency và chạy demo
Từ thư mục gốc repository, cài dependency project (cần mạng lần đầu):

```bash
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python tools/demo.py --mode simulation
```

Mở [Dashboard](http://127.0.0.1:8000) và [Nhân viên](http://127.0.0.1:8000/staff). Seed24 bàn/2 nhân viên chỉ trong profile simulation; chạy lại không reset/seed trùng. **Dừng bằng Ctrl+C**. Script chỉ bind127.0.0.1; MVP chưa hỗ trợ LAN. Không chạy nhiều worker vì serial/simulator worker phải có một owner.

Windows PowerShell (không cần activate hoặc Docker):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
npm --prefix frontend ci
npm --prefix frontend run build
.\.venv\Scripts\python.exe tools/demo.py --mode simulation
```

## Development và kiểm tra
Terminal backend:

```bash
.venv/bin/python tools/demo.py --mode simulation
```

Terminal frontend (Vite proxy `/api` về backend8000):

```bash
npm --prefix frontend run dev
```

Mở [Vite](http://127.0.0.1:5173). Sau thay đổi frontend, build lại khi muốn backend phục vụ bản local mới.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check backend tools
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run format:check
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

PowerShell: thay `.venv/bin/python` bằng `.\.venv\Scripts\python.exe`. Các lệnh npm giữ nguyên. E2E dùng port8000 riêng: **dừng server demo trước**, build trước; DB test ở thư mục temp `pbl4-e2e`, không dùng DB demo/hardware vận hành. Trên Linux hiện có `/usr/bin/chromium`, config tự dùng nó. Nếu máy khác chưa có browser Playwright: `cd frontend` rồi `npx playwright install chromium` (browser test project, không cần Docker). PTY test chỉ Linux, sẽ skip đúng lý do trên Windows.

OpenAPI/schema tương tác: [API docs](http://127.0.0.1:8000/docs). Snapshot `/api/snapshot`, timeline `/api/requests/{id}`, nhật ký toàn cục `/api/event-log`, lịch sử `/api/history`, CSV `/api/export.csv`, health/config an toàn `/api/health`. Ghi thay đổi qua POST và expected_version/idempotency_key; conflict409 yêu cầu tải lại, không giả lập thành công.

## Kịch bản demo 5–7 phút
1. Tổng quan24 bàn/2 nhân viên. Mở **Bàn mô phỏng**; giữ ngắn rồi thả để chứng minh hủy. Giữ liên tục5 giây: LED nhấp nháy khi giữ, “đang gửi/chưa xác nhận” trước receipt, đỏ sau khi backend lưu.
2. Về Tổng quan → Bàn01 → **Xác nhận yêu cầu**. Quan sát “Đang chờ bàn nhận”; tới poll kế tiếp simulator báo LED xanh. USB/RF ACK không tự xác nhận quản lý.
3. Giao Minh Anh. Mở `/staff` trong tab khác, chọn Minh Anh (selector demo có nhãn), **Nhận việc**. Web chỉ hướng dẫn đến bàn/bấm đúp nút ẩn, không có nút hoàn tất.
4. Về simulator, bấm nút ẩn **hai lần riêng** trong600ms. DONE đóng yêu cầu; nhận DONE_RECEIPT mới tắt LED. Xem lịch sử/timeline/CSV; reload dữ liệu vẫn còn.
5. **Gọi đồng thời4 bàn**, **Tua+301 giây** (clock demo riêng). Quá hạn hiện cờ riêng, không thay state và không reset từ ACK/giao việc.
6. Chọn mất receipt một lần, ngắt/kết nối lại gateway, quan sát waiting/retry/poll. Có thể thử duplicate và trễCALL. Idle node không bị coi offline do ngủ.
7. Dừng/mở server để chứng minh persistence. Nếu cần làm lại, **Reset dữ liệu demo…** có hộp xác nhận; không reset tự động khi khởi động.

## Gateway thật / serial emulator

Simulation và hardware dùng DB khác nhau, không tự chuyển mode khi rút gateway. Hardware ban đầu trống; đăng ký node/bàn/nhân viên ở Cấu hình trước.

Linux:

```bash
PBL_SERIAL_PORT=/dev/ttyACM0 PBL_SERIAL_BAUD=115200 .venv/bin/python tools/demo.py --mode hardware
```

Windows PowerShell:

```powershell
$env:PBL_SERIAL_PORT = 'COM3'
$env:PBL_SERIAL_BAUD = '115200'
$env:PBL_STAFF_ID = '1'
# Nếu dùng staff web prototype hardware, tự tạo token bí mật:
$env:PBL_STAFF_TOKEN = '<TOKEN_NGAU_NHIEN_CUA_BAN>'
.\.venv\Scripts\python.exe tools/demo.py --mode hardware
```

Không dùng placeholder làm token thật. Hardware staff nhập ID/token đã cấu hình; server ràng buộc token đúng ID. Manager chỉ loopback; không quảng bá demo selector thành authentication. Cấu hình bằng environment, `.env.example` chỉ mẫu, không tự load `.env`. `PBL_DATA_DIR` đổi thư mục dữ liệu, `PBL_POLL_SECONDS=5`, `PBL_DOUBLE_MS=600`; đây là mặc định triển khai, chưa đo firmware.

pyserial reconnect backoff1–16s, outbox retry tối đa5/lệnh, TTL120s, chỉ gửi trạng thái bàn khi node liên lạc. Dashboard/chi tiết hiển thị gateway, delivery/apply/errors; log parser/reconnect ở terminal server. Serial monitor phải đóng để tránh chiếm port.

Linux emulator terminal A:

```bash
.venv/bin/python tools/serial_emulator.py --pty
```

Terminal B dùng đường dẫn `/dev/pts/N` emulator in ra làm PBL_SERIAL_PORT, chạy **hardware profile** (DB test riêng nếu cần `PBL_DATA_DIR=/tmp/pbl4-serial-demo`). Đăng ký node1 rồi terminal A gõ `call 1`, managerACK, `done 1`; `fragment 1`, `duplicate`, `bad`, `oversized` thử parser. Đây là **serial gateway mô phỏng**, không phải firmware đo trên RF. Emulator interactive Linux/WSL; PC adapter thật hỗ trợ COM qua pyserial. Xem [protocol](docs/protocol.md) và [hardware handover](docs/hardware-integration.md).

## Database, backup và restore

- `data/simulation.sqlite3` và `data/hardware.sqlite3` (tương đối root); có WAL/SHM phụ khi chạy. Không commit runtime DB.
- Schema v1 qua `PRAGMA user_version`; index unique active/table; phiên bản DB lạ bị từ chối. UTC epoch timestamps, UI giờ Việt Nam. Không tái sử dụng node/boot/token cho một lần gọi khác.
- Backup online bằng SQLite backup API, không copy riêng file DB đang có WAL:

```bash
.venv/bin/python tools/backup.py backup --mode simulation --file backups/demo-2026-11-06.sqlite3
```

- Restore: **dừng server trước**, giữ backup hiện tại nếu cần, rồi:

```bash
.venv/bin/python tools/backup.py restore --mode simulation --file backups/demo-2026-11-06.sqlite3 --confirm-restore
```

Dùng `--mode hardware` tường minh cho vận hành thật. Restore ghi đè DB được chỉ định nên phải xác nhận. Reset trong UI chỉ tồn tại ở simulation và chỉ xóa data demo; cấu hình bàn/staff giữ lại. Thêm `--data-dir` nếu đã đổi PBL_DATA_DIR.

## Tài liệu / giới hạn

- [Yêu cầu và stories](docs/spec.md), [kiến trúc](docs/architecture.md), [bảng transition](docs/state-machine.md), [giả định](docs/assumptions.md), [tiến độ](docs/tasks.md).
- [Kết quả kiểm tra và traceability](docs/verification.md), [ảnh desktop](docs/screenshots/dashboard.png), [ảnh mobile](docs/screenshots/staff.png).
- Firmware Pro Mini/nRF24/staff chưa được cung cấp. RF frame28byte là **đề xuất cần xác nhận**, không tự viết theo pinout/radio tưởng tượng. Chưa đo RF range/latency/delivery success, current/battery life hoặc xác minh tương thích firmware thật. UI không biến thiếu telemetry thành số đo hoặc %pin giả.
