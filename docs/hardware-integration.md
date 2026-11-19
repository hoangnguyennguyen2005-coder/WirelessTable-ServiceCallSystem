# Tích hợp phần cứng — những gì chưa kiểm chứng

Repository không chứa firmware và chưa từng được chạy với Pro Mini, nRF24L01+, ESP32-C3 hay thiết bị nhân viên thật. Mọi kết quả hiện có là phần mềm (simulator, cổng serial giả lập). Không có pinout, kênh radio hay địa chỉ nào được đặt ở đây; đó là việc của các work package 1–3.

## Phía PC đã sẵn sàng gì

- Đọc/ghi USB serial bằng pyserial, parser NDJSON có giới hạn độ dài, tự kết nối lại (1–16 giây).
- Giao thức v2 ở `protocol.md`: ranh giới **gateway ↔ PC**. Khung RF gọn giữa nút và gateway do firmware quyết định, miễn là gateway dịch được sang các trường trong `protocol.md` và giữ nguyên `boot_id`, `call_token`, `request_id`, `revision`.
- Outbox bền cho cả nút bàn và thiết bị nhân viên; lệnh chỉ phát khi thiết bị liên lạc.

## Chạy với gateway thật

1. Build frontend, chạy profile hardware trên PC tại quán (không cần Internet).
2. Database hardware ban đầu trống: vào **Cấu hình**, khai báo bàn (node ID) và nhân viên (ID thiết bị). Node ID và ID thiết bị dùng chung một không gian địa chỉ, không được trùng.
3. Đặt `PBL_SERIAL_PORT` (`COM3` hoặc `/dev/ttyACM0`), `PBL_SERIAL_BAUD` (115200 là đề xuất, phải khớp firmware), `PBL_VENUE_ID` khớp với venue nạp trong firmware.
4. Đóng mọi serial monitor đang giữ cổng. Trên Linux, tài khoản phải có quyền mở cổng.
5. Khi chưa có thiết bị nhân viên: đặt `PBL_STAFF_TOKEN` và `PBL_STAFF_ID` để bật stub tại `/staff`. Stub chỉ để chẩn đoán (logbook IT-02), không thay cho thiết bị thật.

## Giả lập gateway bằng phần mềm

`tools/serial_emulator.py` đóng vai gateway + nút bàn + thiết bị nhân viên ở đầu kia của một cặp cổng serial.

- Linux/WSL: `python tools/serial_emulator.py --pty`, lấy đường dẫn `/dev/pts/N` in ra làm `PBL_SERIAL_PORT`.
- Windows: cần một cặp cổng COM ảo do bạn tự cài (ví dụ com0com); chạy `python tools/serial_emulator.py --port COM11` và cho server mở cổng còn lại. Đường này chưa được thử trên máy phát triển vì không có driver cặp cổng; phần logic của emulator được test qua loopback trong `test_emulator.py`.

Lệnh trong emulator: `call <node> [service|bill]`, `done <node>`, `poll <node>`, `hello <node>`, `battery <node> <mV> [low]`, `staff <device> on|off`, `accept <device> [số thứ tự]`, `fragment <node> [service|bill]`, `duplicate`, `bad`, `oversized`, `venue <id>`, `quit`. `--venue` đặt venue gửi đi, `--no-apply` để nút không báo đã hiển thị (thử cờ "bàn chưa nhận trạng thái").

## Danh sách bàn giao (tất cả đang chờ phần cứng)

| Hạng mục | Phiếu logbook |
|---|---|
| Giữ 4,9 giây không gửi, 5 giây gửi một lần; debounce; chính sách hai nút cùng lúc | UT-01 |
| Cửa sổ bấm đúp ≤1 giây, bấm đơn và lúc rảnh không gửi | UT-02 |
| Đỏ chỉ sau CALL_RECEIPT; xanh sau SET_REQUEST_STATUS; tắt sau DONE_RECEIPT; các trạng thái chờ | UT-03 |
| Mã hóa khung RF, lọc venue/địa chỉ, gửi lại giữ nguyên định danh, lịch poll và ngủ | UT-04, UT-05 |
| Cầu USB: không tự sinh xác nhận, tách dòng, rút/cắm lại | UT-06 |
| Thiết bị nhân viên: hiển thị bàn + loại, rung im lặng, nhận việc, việc bị thu hồi | UT-07, UT-08 |
| Đo áp, ngưỡng cảnh báo và cắt, nguồn 2×AAA | UT-09, AT-05 |
| Chuỗi bàn–gateway–PC và giao việc với thiết bị thật | IT-01, IT-02 |
| Mất điện từng thành phần, khôi phục | IT-03 |
| Tầm phủ, lô 100 cuộc gọi, độ trễ thật | AT-03 |
| Vỏ, lau chùi, lắp đặt, BOM, quy định tần số, thử với người dùng | AT-02, AT-04, AT-06 |

**Chưa đo, chưa xác minh:** tầm phủ RF, độ trễ và tỷ lệ truyền, dòng ngủ/hoạt động, tuổi thọ pin, tương thích với firmware thật. Test bằng simulator, PTY và trình duyệt không thay thế các phép đo này.

## Điểm firmware cần chốt với phần mềm

- Tên và mã của các bản tin trong khung RF, nhất là bản tin đối soát sau khi nút khởi động lại (`NODE_HELLO` là đề xuất của phần mềm).
- Chu kỳ poll khi có yêu cầu (đang giả định 5 giây) và của thiết bị nhân viên (đề xuất 2 giây): trung tâm tính ngưỡng mất liên lạc từ hai giá trị này.
- Cách báo pin: trung tâm ưu tiên cờ `battery_low` do thiết bị đặt; `battery_mv` chỉ để hiển thị.
- `boot_id` phải đổi sau mỗi lần khởi động lại và `call_token` không lặp trong một lần boot.
