# PBL4 — Gọi phục vụ tại bàn (Wireless Table-Service Call System)

Phần mềm tại máy trung tâm của dự án ECE411, nhóm 3, theo **Concept C** trong logbook: nút bàn Pro Mini + nRF24L01+ (2×AAA) → gateway ESP32-C3 qua USB → PC tại quán → thiết bị nhân viên chuyên dụng. Repository gồm backend FastAPI/SQLite, giao diện quản lý React tiếng Việt, simulator nút bàn và thiết bị nhân viên, công cụ giả lập gateway. Chạy hoàn toàn tại quán, không cần Internet. Không có firmware ở đây.

**Nguồn yêu cầu: logbook ECE411 (Step 1–6).** Xem [đặc tả](docs/spec.md) và [bảng truy vết 33 ER](docs/traceability.md).

## Quy trình được triển khai

1. Khách chọn **Phục vụ** hoặc **Thanh toán**, giữ 5 giây. Đèn đỏ sáng chỉ khi trung tâm đã lưu bền yêu cầu.
2. Trung tâm xếp hàng theo thứ tự ghi nhận, hiển thị thời gian chờ.
3. Quản lý **xác nhận** → đèn bàn chuyển xanh (khi bàn báo đã nhận lệnh).
4. Quản lý **giao việc** cho thiết bị nhân viên; nhân viên bấm **nhận việc**. Giao việc không đổi màu đèn.
5. Từ 300 giây kể từ lúc ghi nhận mà chưa xong: nhắc quản lý, giữ nguyên thứ tự.
6. Nhân viên **bấm đúp nút ẩn** tại bàn → trung tâm đóng yêu cầu → đèn tắt. Web không có nút hoàn tất.

Lỗi liên lạc, lệnh chưa tới bàn hay thiết bị, pin yếu đều hiện tại trung tâm trong vòng 10 giây (cờ bật ở 8 giây) và được ghi vào nhật ký sự kiện. Lỗi giả lập ở trang Bàn mô phỏng áp cho gói tiếp theo của bàn đang chọn.

## Cài đặt

| Công cụ | Yêu cầu | Đã thử |
|---|---|---|
| Python | ≥ 3.12 | 3.14 (Windows 10), 3.12 (Linux) |
| Node.js | ≥ 22.12 | 26 (Windows 10), 24 (Linux) |

Windows PowerShell, tại thư mục gốc (lần đầu cần Internet):

```powershell
py -0p                                   # xem bản Python có trên máy
py -3.14 -m venv .venv                   # thay 3.14 bằng bản bạn có
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
npm --prefix frontend ci
npm --prefix frontend run build
```

Linux/macOS: thay `.\.venv\Scripts\python.exe` bằng `.venv/bin/python`.

## Chạy demo

```powershell
.\.venv\Scripts\python.exe tools/demo.py --mode simulation
```

Mở http://127.0.0.1:8000 (quản lý) và http://127.0.0.1:8000/staff (thiết bị nhân viên mô phỏng). Dừng bằng **Ctrl+C**. Profile simulation có sẵn 24 bàn và 2 nhân viên (thiết bị #101, #102); dữ liệu còn sau khi khởi động lại.

Database cũ (schema v1) được tự nâng cấp lên v2 khi mở; bản gốc được giữ ở `data/<mode>.sqlite3.v1-backup`.

Khi phát triển giao diện, chạy thêm `npm --prefix frontend run dev` và mở http://127.0.0.1:5173.

### Kịch bản demo (khoảng 7 phút)

1. **Tổng quan**: 24 bàn rảnh. Vào **Bàn mô phỏng**, giữ nút Thanh toán rồi thả sớm: không có gì xảy ra. Giữ đủ 5 giây: đỏ nhấp nháy → "Trung tâm đã ghi nhận · đèn đỏ sáng".
2. **Tổng quan** → Bàn 01 → **Xác nhận yêu cầu**. Chi tiết hiện "đang chờ bàn"; tới lần poll kế tiếp bàn báo đèn xanh.
3. Chọn **Giao cho nhân viên**. Mở `/staff` ở tab khác: việc hiện ra, trung tâm thấy "đã tới thiết bị". Bấm **Nhận việc**: trung tâm thấy "nhân viên đã nhận", đèn bàn vẫn xanh.
4. Quay lại **Bàn mô phỏng**, bấm **Nút ẩn hoàn tất** hai lần trong 1 giây: yêu cầu đóng, đèn tắt, việc biến khỏi thiết bị. Xem **Lịch sử** → tab **Nhật ký sự kiện**, tải CSV.
5. **Gọi đồng thời 4 bàn**, **Tua +300 giây**: bốn yêu cầu được nhắc, thứ tự không đổi.
6. Thử lỗi: **Mất phản hồi trung tâm một lần** (bàn tự gửi lại, không tạo yêu cầu thứ hai), **Ngắt gateway mô phỏng**, **Tắt nguồn thiết bị** nhân viên rồi giao việc (hiện "Chưa tới thiết bị nhân viên"), **Khởi động lại nút (thay pin)**, **Giả lập pin yếu**.
7. Dừng rồi chạy lại server: mọi yêu cầu, thứ tự và trạng thái còn nguyên. **Reset dữ liệu demo…** có hộp xác nhận.

## Chạy với gateway thật

Database hardware tách riêng và ban đầu trống: vào **Cấu hình** khai báo bàn (node ID) và nhân viên (ID thiết bị) trước.

```powershell
$env:PBL_SERIAL_PORT = 'COM3'
$env:PBL_VENUE_ID = '1'                   # phải khớp venue trong firmware
.\.venv\Scripts\python.exe tools/demo.py --mode hardware
```

Chưa có thiết bị nhân viên thật: đặt thêm `PBL_STAFF_TOKEN` (tự sinh chuỗi ngẫu nhiên) và `PBL_STAFF_ID` để dùng `/staff` như **stub chẩn đoán**. Đóng mọi serial monitor trước khi chạy. Giao thức USB ở [protocol.md](docs/protocol.md); việc cần làm với phần cứng ở [hardware-integration.md](docs/hardware-integration.md).

Giả lập gateway bằng phần mềm: `tools/serial_emulator.py --pty` (Linux/WSL) hoặc `--port COMx` với một cặp cổng COM ảo (Windows). Gõ `call 1 bill`, `done 1`, `staff 101 on`, `accept 101`… Kết quả của emulator không phải số đo phần cứng.

## Cấu hình

Đặt bằng biến môi trường (ứng dụng không tự đọc `.env`; xem [.env.example](.env.example)).

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `PBL_MODE` | `simulation` | `simulation` hoặc `hardware`, mỗi chế độ một database |
| `PBL_DATA_DIR` | `data` | Thư mục database |
| `PBL_VENUE_ID` | `1` | Mã quán, gắn với database và kiểm tra trên mọi frame |
| `PBL_SERIAL_PORT`, `PBL_SERIAL_BAUD` | —, `115200` | Cổng gateway (chế độ hardware) |
| `PBL_POLL_SECONDS` | `5` | Chu kỳ poll của nút bàn khi có yêu cầu |
| `PBL_STAFF_POLL_SECONDS` | `2` | Chu kỳ poll của thiết bị nhân viên |
| `PBL_DOUBLE_MS` | `1000` | Cửa sổ bấm đúp |
| `PBL_REMINDER_SECONDS` | `300` | Mốc nhắc |
| `PBL_UNRESOLVED_SECONDS` | `10` | Sau bao lâu thì báo "chưa giải quyết" |
| `PBL_RETENTION_DAYS` | `90` | Thời gian giữ nhật ký, tối thiểu 30 |
| `PBL_LOW_BATTERY_MV` | `0` (tắt) | Ngưỡng pin yếu tùy chọn; cờ của thiết bị luôn được dùng |
| `PBL_STAFF_TOKEN`, `PBL_STAFF_ID` | —, `1` | Stub thiết bị nhân viên ở chế độ hardware |

Các giá trị thời gian là đề xuất của logbook, chưa được chốt bằng thử nghiệm ([giả định](docs/assumptions.md)).

## API

Tài liệu tương tác: http://127.0.0.1:8000/docs. Chính:

- `GET /api/snapshot`, `GET /api/requests/{id}`, `GET /api/history`, `GET /api/health`
- `POST /api/requests/{id}/ack | dispatch | cancel-dispatch | retry-dispatch` (kèm `expected_version`, `idempotency_key`; lệch phiên bản trả 409)
- `GET /api/event-log`, `GET /api/events.csv` (nhật ký sự kiện, giờ +07:00), `GET /api/export.csv` (lịch sử yêu cầu)
- `GET /api/events` (SSE báo có thay đổi)
- `GET /api/staff-device/{id}`, `POST /api/staff-device/{id}/accept` (thiết bị mô phỏng / stub)
- `POST /api/config/tables`, `POST /api/config/staff`
- `POST /api/sim/event`, `POST /api/sim/action` (chỉ có ở simulation)

Server chỉ nghe trên 127.0.0.1 và từ chối Host/Origin lạ. Chưa có đăng nhập nên chưa mở ra mạng LAN. Chỉ chạy một worker.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend tools
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run format:check
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

E2E dùng cổng 8000 nên phải **dừng server demo trước**, và cần build trước; database của E2E nằm trong thư mục temp. Cần trình duyệt: `cd frontend; npx playwright install chromium`, hoặc dùng Chrome/Edge có sẵn bằng `$env:PBL_E2E_CHANNEL = 'chrome'` (hoặc `msedge`). Test PTY chỉ chạy trên Linux. Kết quả gần nhất ở [verification.md](docs/verification.md).

## Sao lưu và khôi phục

```powershell
.\.venv\Scripts\python.exe tools/backup.py backup --mode simulation --file backups/demo.sqlite3
# dừng server trước khi khôi phục
.\.venv\Scripts\python.exe tools/backup.py restore --mode simulation --file backups/demo.sqlite3 --confirm-restore
```

Sao lưu dùng SQLite backup API nên chạy được khi server đang mở. Thêm `--data-dir` nếu đã đổi `PBL_DATA_DIR`. Không commit database.

## Tài liệu

- [Đặc tả](docs/spec.md) · [Truy vết logbook](docs/traceability.md) · [Bảng trạng thái](docs/state-machine.md) · [Giao thức USB v2](docs/protocol.md)
- [Kiến trúc](docs/architecture.md) · [Giả định và giới hạn](docs/assumptions.md) · [Tích hợp phần cứng](docs/hardware-integration.md)
- [Kết quả kiểm tra](docs/verification.md) · [Tiến độ](docs/tasks.md) · ảnh [quản lý](docs/screenshots/dashboard.png), [thiết bị nhân viên](docs/screenshots/staff.png)

**Chưa kiểm chứng:** tầm phủ, độ trễ và tỷ lệ truyền RF, dòng tiêu thụ và tuổi thọ pin, vỏ hộp, chi phí, tương thích firmware. Giao diện không hiển thị số đo hay phần trăm pin giả.
