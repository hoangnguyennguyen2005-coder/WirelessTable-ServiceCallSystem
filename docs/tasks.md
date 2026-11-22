# Tiến độ

## Đợt 1 — MVP theo bản yêu cầu ban đầu (2026-11-06)

Hoàn thành khi chưa có logbook: một loại yêu cầu, luồng xác nhận → giao → nhận → hoàn tất trên web nhân viên, giao thức v1. Chi tiết nằm trong lịch sử git.

## Đợt 2 — chỉnh theo logbook ECE411 (2026-11-17)

- [x] Đọc logbook Step 1–6; lấy 33 ER, 9 ràng buộc, kế hoạch test làm nguồn có hiệu lực.
- [x] Mô hình: vòng đời `REGISTERED → ACKNOWLEDGED → COMPLETED` tách khỏi giao việc; loại Service/Bill; `seq` FIFO.
- [x] Schema v2 và migrate v1 tại chỗ có sao lưu; database gắn `venue_id`.
- [x] Giao thức v2: `venue_id`, category, NODE_HELLO, kênh thiết bị nhân viên, phản hồi cho mọi lần liên lạc.
- [x] DONE hợp lệ trước khi xác nhận; nhắc từ ≥300 giây; cửa sổ bấm đúp mặc định 1000 ms.
- [x] Nhật ký 8 loại sự kiện, lưu ≥30 ngày, `/api/events.csv`.
- [x] Cờ "chưa giải quyết" (10 giây), cảnh báo pin yếu.
- [x] Thiết bị nhân viên ảo thay cho trang web nhân viên; stub có token ở chế độ phần cứng.
- [x] Simulator: hai nút, mẫu đèn, khởi động lại nút, pin, lỗi giả lập.
- [x] Giao diện: tổng quan, chi tiết, bàn mô phỏng, thiết bị nhân viên, lịch sử + nhật ký, cấu hình.
- [x] `tools/serial_emulator.py` viết lại cho v2, chạy được trên Windows với `--port`.
- [x] Test: 61 pytest + 3 E2E; tài liệu viết lại, thêm `traceability.md`.
- [x] 2026-11-19: chạy UT-11, UT-12, AT-07 (mô phỏng) theo hướng dẫn test; sửa 6 lỗi tìm thấy (`verification.md`). 63 pytest + 3 E2E.

## Đợt 3 — Gateway và PC theo Phương án B (2026-11-22)

- [x] T301 [FR-13, FR-16] Sửa đọc USB tại `serial_gateway.py`, đặt DTR/RTS trước khi mở cổng và gắn `event_id` vào chiều trả. Sửa chặn outbox sai venue trong `service.py`. Kiểm với `test_adapters.py`, `test_domain.py` và `test_emulator.py`.
- [x] T302 [FR-16, SC-05] Hoàn thiện `firmware/PBL4_Gateway_B/PBL4_Gateway_B.ino` theo R01. Biên dịch cả chế độ radio và bench cho ESP32-C3 bằng ESP32 core 3.3.12, RF24 1.6.2 và USB CDC On Boot. Kiểm codec, lọc sai CRC/venue/chiều, tách/gộp dòng, mốc 4096/4097, địa chỉ bàn/tay, tag và bản trả quá hạn trên host.
- [x] T303 [FR-03, SC-05] Nối logic sketch bench qua PTY với adapter Python và SQLite. Hai uplink CALL Bill giống nhau tạo một yêu cầu và hai receipt. ID, thời điểm, loại và số FIFO giữ nguyên. Suite Python có 66 test đạt, gồm PTY.
- [x] T304 [FR-16] Đối chiếu tên lệnh, địa chỉ RF, mã lỗi và vector trong `protocol.md` với `PBL4_Gateway_B.ino`. Bổ sung hướng dẫn nạp và ghép ở `hardware-integration.md`.
- [ ] T305 [SC-04, SC-05] Chạy UT-04–06 trên mạch thật và IT-01/02 khi có firmware bàn và tay. Đo độ trễ, thử đóng/mở COM khi gateway còn nguồn và thử rút/cắm cáp riêng. Lưu log theo phiếu ECE411.

## Còn mở

- [ ] Tìm nguyên nhân một lần hỏng không tái hiện được của test emulator loopback (`verification.md`).
- [x] Chạy lại test PTY trên Linux với giao thức v2 trong T303.
- [ ] Ghép firmware bàn và tay theo bảng địa chỉ, mã và vector tại `protocol.md`.
- [ ] Thực hiện các phiếu IT/AT của logbook khi có phần cứng (AT-07: các dòng 1a radio, 2a USB/RF, 4 nút thật, 5b mất điện thật).
- [ ] Nhóm firmware chốt mốc báo "chưa xác nhận đăng ký": hiện đúng 5,0 s, không có khoảng dư so với ER-R03.
- [ ] Chốt các giá trị PROPOSED sau khi thử với người dùng (`assumptions.md`).
