# Giả định, mặc định triển khai và giới hạn

## Thứ tự ưu tiên nguồn

Logbook ECE411 (nhóm 3) là nguồn có hiệu lực. Bản `requirements-source.txt` viết trước khi có logbook; các điểm sau đã đổi theo logbook:

| Chủ đề | Bản cũ | Theo logbook (đang triển khai) |
|---|---|---|
| Loại yêu cầu | một nút gọi | Service / Bill (ER-F01) |
| DONE khi chưa xác nhận | từ chối | hợp lệ với mọi yêu cầu đã ghi nhận (ER-F09) |
| Mốc nhắc | > 300 giây | ≥ 300 giây (ER-F08, UT-12) |
| Giao việc | chỉ sau khi xác nhận | độc lập với xác nhận, không đổi đèn (ER-F04, IT-02) |
| Thiết bị nhân viên | trang web | thiết bị chuyên dụng qua gateway; web chỉ là máy ảo/stub (C-04, C-06) |
| Cửa sổ bấm đúp | 600 ms | ≤ 1 giây, tạm thời (ER-F09) |
| Nhật ký | mọi frame | 8 loại sự kiện + phụ trợ, giữ ≥ 30 ngày, CSV (ER-F11) |

## Giá trị đề xuất (PROPOSED trong logbook, chưa được người dùng/firmware xác nhận)

- Giữ 5 giây; kết quả đăng ký trong 5 giây; nhắc 300 giây; ngưỡng "chưa giải quyết" 10 giây; bấm đúp ≤ 1000 ms.
- Poll 5 giây khi có yêu cầu là **giả định của mô hình năng lượng**, không phải yêu cầu. Poll thiết bị nhân viên 2 giây là đề xuất của phần mềm này.
- Trung tâm bật cả bốn cờ chưa giải quyết (mất liên lạc bàn/thiết bị nhân viên, đèn chưa tới bàn, việc chưa tới thiết bị) sau 8 giây: 10 giây (ER-R03) trừ 2 giây dự phòng cho nhịp kiểm tra 0,5 giây và thời gian màn hình tải lại, nhưng không dưới 1 chu kỳ poll + 2 giây. Đo trên màn hình, trường hợp xấu nhất (ngắt ngay sau một lần poll): 7,1–7,7 giây (`evidence/AT-07/2a-do-tren-man-hinh.txt`). Ngưỡng cũ 12 giây vượt ER-R03 và đã bị bỏ ngày 2026-11-19.
- Serial 115200 8N1, TTL lệnh 120 giây, tối đa 5 lần gửi, lùi 1–16 giây.
- Các mẫu đèn (đỏ chớp đôi, đỏ/xanh luân phiên) và việc giữ đỏ nhấp nháy trong lúc chờ xác nhận đăng ký là đề xuất, cần thử theo ER-U02.
- Nút đang giữ thì nút còn lại bị bỏ qua (nút giữ trước thắng).

Đổi bằng biến môi trường: `PBL_POLL_SECONDS`, `PBL_STAFF_POLL_SECONDS`, `PBL_DOUBLE_MS`, `PBL_REMINDER_SECONDS`, `PBL_UNRESOLVED_SECONDS`, `PBL_RETENTION_DAYS` (≥ 30), `PBL_LOW_BATTERY_MV`, `PBL_VENUE_ID`.

## Quyết định của phần mềm chưa có trong logbook

- **Giao việc không tự xác nhận.** Giao trước khi xác nhận thì đèn bàn vẫn đỏ; giao diện nhắc điều này.
- **Gửi lại** tạo lệnh mới cho cùng phiên giao; **thu hồi** và **giao lại** tăng/đóng phiên. Không có tự động leo thang khi nhân viên chưa nhận (logbook nói chưa đặt timeout).
- **Pin yếu:** ưu tiên cờ `battery_low` do thiết bị báo (firmware giữ ngưỡng từ phép đo). `PBL_LOW_BATTERY_MV` mặc định 0 = tắt, vì logbook chưa chốt ngưỡng. Không hiển thị phần trăm pin.
- **NODE_HELLO** để nút mất RAM đối soát; logbook yêu cầu hành vi (ER-F05) nhưng chưa đặt tên bản tin.
- **Một không gian địa chỉ** cho nút bàn và thiết bị nhân viên; cấu hình chặn trùng.
- **Lỗi lặp** cùng thiết bị và cùng lý do chỉ ghi một lần mỗi 30 giây; polling bình thường không ghi vào nhật ký.
- Nhật ký bị xóa khi quá `PBL_RETENTION_DAYS` (mặc định 90); yêu cầu trong lịch sử thì giữ.
- Database gắn với một `venue_id`; mở bằng venue khác sẽ bị từ chối khởi động.

## Giới hạn

- Simulation dùng `data/simulation.sqlite3`, hardware dùng `data/hardware.sqlite3`; chỉ profile simulation có seed 24 bàn / 2 nhân viên (thiết bị 101, 102).
- Chỉ loopback, kiểm tra Host/Origin. Quản lý tại máy trung tâm được coi là tin cậy; không có đăng nhập.
- Stub thiết bị nhân viên ở chế độ phần cứng chỉ để tích hợp từng phần (logbook IT-02: "a stub is diagnostic only"); kết quả với stub không thay cho thiết bị thật.
- Liên kết radio không mã hóa và không xác thực (logbook loại khỏi phạm vi prototype): bất kỳ frame hợp lệ nào mang đúng `venue_id` và `node_id` đều được tin.
- UTC epoch trong SQLite; hiển thị và CSV theo +07:00. Đồng hồ demo chỉ có ở simulation.
- Chưa đo: tầm phủ, độ trễ và tỷ lệ truyền RF, dòng tiêu thụ, tuổi thọ pin, vỏ hộp, chi phí, tuân thủ tần số. Xem `hardware-integration.md`.
