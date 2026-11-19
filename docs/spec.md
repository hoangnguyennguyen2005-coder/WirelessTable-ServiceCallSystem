# Wireless Table-Service Call System — đặc tả phần mềm trung tâm

Cập nhật 2026-11-17. **Nguồn có hiệu lực: logbook ECE411 của nhóm 3** (Step 1 §1.5.2 quy trình, Step 3 Table 3.4.1 gồm 33 ER và Table 3.4.2 gồm 9 ràng buộc, Step 4 Concept C, Step 5 phân rã chức năng, Step 6 kế hoạch test). `requirements-source.txt` là bản yêu cầu ban đầu, viết khi chưa có logbook; chỗ nào hai bên khác nhau thì theo logbook (xem `assumptions.md`).

Repository này là **work package 4** trong logbook §6.6 (web/app tại máy trung tâm) cùng simulator và công cụ giả lập gateway. Firmware nút bàn, gateway và thiết bị nhân viên không nằm ở đây.

## Phạm vi

Concept C: Pro Mini 3.3 V/ATmega328P ≤4 MHz, BOD 1.8 V, 2×AAA trực tiếp → nRF24L01+ (mạng sao) → gateway ESP32-C3 qua USB → PC tại quán. Thiết bị nhân viên chuyên dụng (hiển thị, rung, một nút nhận). Chạy không cần Internet và không cần router của quán. Ngoài phạm vi: gọi món, tính tiền, thanh toán, POS, cloud (C-03).

## Quy trình (C-01)

1. **Khách gọi.** Chọn Phục vụ hoặc Thanh toán, giữ 5 giây (đỏ nhấp nháy). Thả sớm thì không có gì. Đủ 5 giây gửi đúng một yêu cầu. Đỏ sáng liên tục chỉ khi trung tâm xác nhận đã lưu.
2. **Trung tâm.** Ghi bàn, loại, thời điểm; xếp hàng theo thứ tự tiếp nhận; hiện thời gian chờ cập nhật mỗi giây.
3. **Quản lý xác nhận.** Đèn bàn chuyển xanh khi xác nhận tới được bàn.
4. **Giao việc.** Quản lý gửi bàn + loại tới thiết bị nhân viên; nhân viên bấm nhận. Chưa tới máy hoặc chưa nhận phải hiện rõ tại trung tâm.
5. **Nhắc.** Sau 5 phút kể từ lúc ghi nhận mà chưa xong thì nhắc quản lý, giữ nguyên thời điểm gọi và thứ tự.
6. **Hoàn tất.** Nhân viên bấm đúp nút ẩn tại bàn. Trung tâm đóng đúng yêu cầu đó; đèn tắt khi bàn nhận được xác nhận hoàn tất.

## Yêu cầu chức năng của phần mềm (ánh xạ ER)

| Mã | Nội dung | ER |
|---|---|---|
| FR-01 | Yêu cầu có bàn, loại SERVICE/BILL, định danh lần gọi; trung tâm cấp ID và số thứ tự tiếp nhận tăng dần. | F01, P03 |
| FR-02 | Một yêu cầu mở mỗi bàn (transaction + unique index). Gọi lặp không tạo mới, không đổi loại, không reset thời gian. | F05, F06 |
| FR-03 | Xác nhận đăng ký chỉ phát sau khi commit bền (`synchronous=FULL`). ACK radio/USB không tạo trạng thái nào. | F03, R04 |
| FR-04 | Chỉ thao tác xác nhận của quản lý làm đèn xanh. Giao việc và nhận việc là thuộc tính riêng. | F04, F07 |
| FR-05 | Giao việc tới thiết bị, tách "đã gửi / đã hiển thị / đã nhận"; giao lại và thu hồi làm phiên cũ mất hiệu lực; gửi lại được. | F07, P05, R03 |
| FR-06 | Nhắc từ ≥300 giây, một lần, kể cả đã xác nhận hoặc đã nhận. | F08 |
| FR-07 | DONE đóng mọi yêu cầu đã ghi nhận; DONE cũ không đóng yêu cầu mới; không có đường tắt hoàn tất trên web. | F09, F10 |
| FR-08 | Nhật ký 8 loại sự kiện + phụ trợ, có bàn/loại/ID, thời gian trung tâm ISO 8601, giữ ≥30 ngày, xuất CSV, không có dữ liệu khách. | F11 |
| FR-09 | Mọi lần liên lạc đều có phản hồi mức ứng dụng; nút khởi động lại đối soát bằng NODE_HELLO. | F05, R03 |
| FR-10 | Trạng thái chưa giải quyết hiện tại trung tâm và được ghi lại: bàn chưa nhận trạng thái, mất liên lạc, chưa tới thiết bị, lệnh lỗi. | P04, P05, R03 |
| FR-11 | Cảnh báo pin yếu tại trung tâm theo cờ của thiết bị hoặc ngưỡng mV tùy chọn; không suy ra phần trăm pin. | E02 |
| FR-12 | Khởi động lại khôi phục mọi yêu cầu với ID, thời gian, thứ tự, trạng thái gốc; đo và báo thời gian khôi phục. | R04 |
| FR-13 | `venue_id` trong mọi frame và gắn với database; frame của quán khác bị từ chối. | M03 |
| FR-14 | Simulator bàn (2 nút, 2 đèn, nút ẩn) và thiết bị nhân viên ảo đi cùng luồng nghiệp vụ với gateway thật; có lỗi giả lập. | — |
| FR-15 | Chỉ loopback, kiểm tra Origin; chế độ phần cứng không có endpoint mô phỏng; stub nhân viên cần token. | C-05, C-06 |

## Thực thể

tables, staff (+ `device_id`), requests (+ `seq`, `category`, thuộc tính giao việc, `led_revision`), assignments, correlations, observations, staff_observations, events, outbox (kênh table/staff), processed, actions, meta. Schema: `backend/app/db/store.py` (v2, tự migrate từ v1 và sao lưu `.v1-backup`). API: `/docs`.

## Tiêu chí hoàn thành phần mềm

- SC-01: Demo đủ quy trình với 24 bàn / 2 nhân viên, dữ liệu còn sau khi khởi động lại.
- SC-02: Các phiếu UT-10, UT-11, UT-12 và phần mềm của AT-01/AT-07 có test tự động tương ứng (`traceability.md`).
- SC-03: Dùng được ở 1366×768 và 390 px; không hiển thị số đo giả.
- SC-04: Mọi ER phần cứng (tầm phủ, pin, vỏ, chi phí, an toàn) được ghi rõ là chưa kiểm chứng.
