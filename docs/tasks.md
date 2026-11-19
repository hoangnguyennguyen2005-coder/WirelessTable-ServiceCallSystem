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

## Còn mở

- [ ] Tìm nguyên nhân một lần hỏng không tái hiện được của test emulator loopback (`verification.md`).
- [ ] Chạy lại test PTY trên Linux với giao thức v2.
- [ ] Thống nhất với nhóm firmware các điểm ở cuối `hardware-integration.md`.
- [ ] Thực hiện các phiếu IT/AT của logbook khi có phần cứng (AT-07: các dòng 1a radio, 2a USB/RF, 4 nút thật, 5b mất điện thật).
- [ ] Nhóm firmware chốt mốc báo "chưa xác nhận đăng ký": hiện đúng 5,0 s, không có khoảng dư so với ER-R03.
- [ ] Chốt các giá trị PROPOSED sau khi thử với người dùng (`assumptions.md`).
