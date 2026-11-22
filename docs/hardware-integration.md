# Ghép gateway ESP32-C3 và PC theo Phương án B

Sketch [PBL4_Gateway_B.ino](../firmware/PBL4_Gateway_B/PBL4_Gateway_B.ino) dùng cùng mạch UT-06 và giữ các lệnh chẩn đoán của R01. Mở sketch trong thư mục `firmware/PBL4_Gateway_B`. [Phương án B](https://docs.google.com/document/d/1OBTQ_S2pkf3wWKKqeCmY9V37gosZpCLJ-DULTzvpLpU/edit) · [Logbook ECE411](https://docs.google.com/document/d/1cgZ2Ah7xPj9pMx1PBW8e7ucmRjqLIAIC/edit)

1. Rút USB và kiểm dây theo bảng. Cắm lại cáp USB dữ liệu vào PC.

   | nRF24L01+ | ESP32-C3 |
   |---|---|
   | VCC | 3V3 |
   | GND | GND |
   | CE | GPIO3 |
   | CSN | GPIO10 |
   | SCK | GPIO4 |
   | MISO | GPIO5 |
   | MOSI | GPIO6 |
   | IRQ | Để trống |

2. Trong Arduino IDE, dùng **ESP32 core 3.3.12** và **RF24 1.6.2**, chọn **ESP32C3 Dev Module**, bật **USB CDC On Boot** và chọn đúng COM. Bấm **Verify**, sau đó **Upload** với `PBL4_PC_BENCH=0`.
3. Mở Serial Monitor ở **115200 baud + New Line**. `PING` phải trả `PONG PBL4-GW-B-R01`. `STATUS` phải có `RADIO=OK`, `VENUE=1`, `CH=76`, `RF=31` và `USB=NDJSON2`. Gửi `TEST CALL` để nhận JSON `CALL` cho bàn 1, loại `BILL`. Dán dòng dưới đây trong 60 giây, kiểm trace bắt đầu bằng `TEST TX 0210`, gửi `TEST STOP` rồi đóng Serial Monitor.

   ```json
   {"protocol_version":2,"venue_id":1,"message_type":"CALL_RECEIPT","node_id":1,"boot_id":123,"call_token":7,"request_id":"01234567-89ab-cdef-0123-456789abcdef","command_id":null,"payload":{"led":"RED","revision":1,"category":"BILL","request_seq":1}}
   ```

4. Để ghép gateway với PC trước khi có bàn, nạp với `PBL4_PC_BENCH=1` và đóng Serial Monitor. Chạy [profile hardware theo README](../README.md#chạy-với-gateway-thật) với `PBL_SERIAL_PORT` là COM vừa chọn, `PBL_SERIAL_BAUD=115200`, `PBL_VENUE_ID=1` và `PBL_DATA_DIR` là thư mục thử riêng. Vào **Cấu hình** tại `http://127.0.0.1:8000` và thêm **Bàn 1** (`node_id=1`).
5. Trong bench, gateway đưa vector `CALL Bill` vào hàm nhận RF mỗi 3 giây khi USB mở. Sau hai `CALL_RECEIPT`, gateway dừng phát vector. Kiểm `/api/health` có `gateway.connected=true` và `gateway.frames_in` tăng. Web phải có đúng một yêu cầu **Thanh toán – Bàn 1**, giữ nguyên ID, giờ đăng ký và FIFO sau gói trùng. Trong nhật ký phải có một `REGISTERED` trước `CALL_RECEIPT`, sau đó là `DUPLICATE`.
6. Nạp lại với `PBL4_PC_BENCH=0` để chạy radio. Cả bàn và thiết bị tay dùng [bảng địa chỉ và frame RF 31 byte](protocol.md#rf-gateway--thiết-bị-frame-31-byte). Thêm một nút bàn rồi chạy IT-01. Sau đó khai báo thiết bị tay `101` và chạy IT-02. Dùng `STATUS` trong Serial Monitor ở lượt chẩn đoán riêng để xem số frame nhận, frame lỗi, lần lỡ cửa sổ và ACK radio.

Chạy lại UT-06 trên firmware này. Kiểm dòng USB chia mảnh, nhiều dòng liền, mốc 4096/4097 byte, sai venue/đích, phản hồi quá cửa sổ và ngắt PC. Thử đóng và mở COM khi ESP còn nguồn trong một lượt, rồi rút và cắm cáp trong lượt khác. Ghi thời điểm nhận tại gateway và PC để đo cửa sổ 250 ms. Kết quả R03/R04 của V2.1 dùng làm bằng chứng cho firmware cũ. Cấu hình này còn chờ đo trên mạch thật.

## Phía PC đã sẵn sàng gì

- Đọc/ghi USB serial bằng pyserial, parser NDJSON có giới hạn độ dài và tự kết nối lại (1–16 giây). PC đặt DTR và RTS về mức không kích hoạt trước khi mở cổng, theo cách đã dùng ở UT-06 R04.
- Gateway và PC dùng chung [giao thức v2](protocol.md). Gateway giữ định danh RF, chuyển trạng thái qua NDJSON và định tuyến bản trả đúng phiên. PC lưu bền trước khi trả xác nhận ứng dụng.
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

## Điểm cần đo và đối chiếu khi ghép thiết bị

- Đối soát `NODE_HELLO` sau khi nút khởi động lại, dùng cùng bảng mã RF với gateway.
- Bắt đầu với bàn đang có yêu cầu poll 5 giây và thiết bị nhân viên poll 2 giây. Đo độ trễ thực và đối chiếu cờ mất liên lạc của PC.
- Cách báo pin: trung tâm ưu tiên cờ `battery_low` do thiết bị đặt; `battery_mv` chỉ để hiển thị.
- `boot_id` phải đổi sau mỗi lần khởi động lại và `call_token` không lặp trong một lần boot.
