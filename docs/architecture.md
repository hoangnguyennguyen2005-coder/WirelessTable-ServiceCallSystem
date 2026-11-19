# Kiến trúc và hợp đồng triển khai

Phạm vi: work package 4 của logbook (web/app tại máy trung tâm), simulator và công cụ giả lập gateway. Concept C là cố định, không xét lại ở đây.

## Nguyên tắc

1. **Máy trung tâm là nguồn sự thật.** Yêu cầu chỉ tồn tại khi đã commit vào SQLite; đèn bàn và màn hình nhân viên chỉ phản ánh trạng thái đã commit.
2. **ACK truyền dẫn không phải nghiệp vụ.** ACK radio, ACK USB (`COMMAND_ACK`), "đã hiển thị" và "đã nhận" là bốn sự kiện khác nhau, lưu riêng.
3. **Im lặng không có nghĩa.** Thiếu phản hồi không bao giờ được hiểu là đã ghi nhận, đã xác nhận hay đã hoàn tất; nó trở thành cờ "chưa giải quyết".
4. **Hai chiều độc lập.** Vòng đời (đèn bàn) và giao việc (thiết bị nhân viên) không điều khiển lẫn nhau.

## Thành phần

```
nút bàn ──RF── gateway ESP32-C3 ──USB/NDJSON── SerialGateway ─┐
thiết bị NV ─RF─┘                                             ├─ Service ── Store (SQLite)
Simulator (bàn ảo) + VirtualStaffHub (thiết bị NV ảo) ────────┘      │
                                             FastAPI: REST + SSE ────┘── React (quản lý, bàn mô phỏng, thiết bị NV)
```

| Tệp | Vai trò |
|---|---|
| `backend/app/db/store.py` | Schema v2, migrate v1 (sao lưu `.v1-backup`), WAL + `synchronous=FULL`, `BEGIN IMMEDIATE`, gắn `venue_id`. |
| `backend/app/domain/models.py` | Frame v2 (Pydantic, cấm trường lạ), `Action`, hằng số. |
| `backend/app/domain/service.py` | Toàn bộ nghiệp vụ: `exchange`, `action`, `remind`, `watch`, `prune`, `snapshot`, nhật ký. Không import serial hay UI. |
| `backend/app/adapters/serial_gateway.py` | pyserial, parser NDJSON có giới hạn, kết nối lại 1–16 giây. |
| `backend/app/adapters/simulator.py` | Mô hình nút bàn (giữ 5 giây, mẫu đèn, bấm đúp, poll, lỗi giả lập). |
| `backend/app/adapters/staff.py` | Thiết bị nhân viên ảo: dùng cho simulation và làm stub khi tích hợp. |
| `backend/app/main.py` | HTTP, SSE, vòng lặp nền (đồng hồ, nhắc, theo dõi, dọn nhật ký), kiểm tra Host/Origin. |
| `tools/serial_emulator.py` | Đóng vai gateway + nút + thiết bị NV ở đầu kia cổng serial. |

Simulator và gateway thật gọi cùng một hàm `Service.exchange(event, source)`, nên test trên simulator đi qua đúng đường nghiệp vụ của phần cứng.

## Hợp đồng

- **Giao dịch.** Thay đổi trạng thái + bản ghi nhật ký + lệnh outbox nằm trong một transaction. Khung phản hồi chỉ được tạo từ dữ liệu đã commit.
- **Định danh.** ID yêu cầu là UUID do trung tâm cấp; `seq` tăng dần quyết định FIFO. `(node_id, boot_id, call_token)` ánh xạ bền tới đúng một yêu cầu và không tái sử dụng. `event_id` có fingerprint: cùng ID khác nội dung bị từ chối.
- **Một yêu cầu mở mỗi bàn.** Unique index riêng phần trên `requests`.
- **Outbox.** Kênh `table` và `staff`; `pending → gateway_received → applied`, hoặc `superseded / failed / expired`. Lệnh xuống bàn chỉ phát khi nút liên lạc (nút ngủ). Tối đa 5 lần, TTL 120 giây. Khi nút đã báo hiển thị đúng revision, phản hồi poll là bản tin không theo dõi (`command_id: null`).
- **Giao việc.** Mỗi lần giao là một phiên (`assignment_revision`); nhận việc phải khớp nhân viên và phiên. Thu hồi/giao lại/hoàn tất gửi `DISPATCH_CANCEL`.
- **Đồng thời.** Thao tác của quản lý mang `expected_version` + `idempotency_key`; lệch phiên bản trả 409.
- **API.** Lỗi luôn là `{detail}`; 409 xung đột, 422 không hợp lệ, 403 sai Host/Origin/token, 404 cho endpoint mô phỏng ở chế độ phần cứng. Danh sách đầy đủ ở `/docs`.
- **SSE.** `/api/events` chỉ báo "có thay đổi" (theo `Store.generation`); client tải lại `/api/snapshot`. Mất kết nối thì kết nối lại và tải snapshot mới.
- **Một tiến trình.** Cổng serial và simulator chỉ có một chủ; không chạy nhiều worker.

## Rủi ro đã tính trước

| Rủi ro | Biện pháp |
|---|---|
| Gói trùng hoặc nút khởi động lại đóng nhầm yêu cầu | Correlation bền, DONE chỉ đóng yêu cầu mà correlation trỏ tới, NODE_HELLO đối soát trước khi nhận yêu cầu mới. |
| Lệnh "xanh" tới sau khi đã hoàn tất | Hoàn tất thay thế mọi lệnh cũ; nút so `request_id` + `revision`. |
| Crash giữa commit và phản hồi | Nút gửi lại cùng `call_token`; trung tâm trả lại kết quả đã commit. |
| Thiết bị nhân viên khởi động lại | `STAFF_POLL` với boot mới làm trung tâm gửi lại các việc hiện hành. |
| Hai trình duyệt cùng thao tác | `expected_version`, khóa idempotency. |
| Rút gateway | Outbox bền; yêu cầu đang mở hiện cờ mất liên lạc, không tự đổi trạng thái. |

## Giao diện

Laptop tại quầy 1366×768 và màn hẹp 390 px. Nền trung tính, màu chỉ dùng cho ngữ nghĩa (đỏ/xanh/hổ phách) và luôn đi kèm chữ. Lưới bàn + hàng đợi FIFO + bảng chi tiết; quá hạn và lỗi liên lạc là nhãn riêng, không trộn vào trạng thái. Không biểu đồ trang trí, không số đo giả, không phần trăm pin.

## Phụ thuộc

Runtime: FastAPI, Pydantic, uvicorn, sqlite3 (stdlib), pyserial; React, react-dom, zod. Kiểm tra: pytest, httpx, ruff; Vite, TypeScript, ESLint, Prettier, Playwright. Phiên bản khóa trong `backend/requirements.lock` và `frontend/package-lock.json`. Không CDN, không font ngoài, không broker, không dịch vụ hệ thống.
