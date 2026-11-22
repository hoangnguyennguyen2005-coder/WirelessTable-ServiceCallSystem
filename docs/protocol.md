# Protocol v2 — hợp đồng tích hợp Phương án B

Hợp đồng này dùng cho Concept C (logbook Step 4). RF/USB đã nhận, trung tâm đã lưu bền, quản lý đã xác nhận và thiết bị đã hiển thị là bốn mốc riêng. Xem [cách nạp và chạy lượt ghép đầu](hardware-integration.md).

Thay đổi so với v1: thêm `venue_id`, loại yêu cầu `category` (SERVICE/BILL), `NODE_HELLO`, toàn bộ nhóm thiết bị nhân viên, và phản hồi ở mọi lần liên lạc. Frame `protocol_version: 1` bị từ chối.

## USB PC ↔ gateway (ESP32-C3 + nRF24L01+)

115200 baud 8N1 (đề xuất; đổi bằng `PBL_SERIAL_PORT`/`PBL_SERIAL_BAUD`). UTF-8 NDJSON, mỗi frame một dòng, tối đa 4096 byte trước LF. Frame bị cắt hoặc ghép nhiều dòng đều được xử lý; dòng sai JSON/schema/quá dài bị bỏ, bộ đếm lỗi tăng và ghi một sự kiện FAILURE (tối đa 30 giây một lần). Gateway chỉ làm cầu nối: giữ nguyên định danh và **không bao giờ tự tạo xác nhận đăng ký hay hoàn tất**.

### Frame từ thiết bị lên PC

```json
{"protocol_version":2,"venue_id":1,"message_type":"CALL","event_id":"1.123.7.1.CALL","node_id":1,"boot_id":123,"call_token":7,"request_id":null,"command_id":null,"payload":{"category":"BILL"}}
```

| Trường | Ý nghĩa |
|---|---|
| `venue_id` | 1..65535, bắt buộc. Khác `PBL_VENUE_ID` thì bị từ chối `wrong_venue` (ER-M03). |
| `node_id` | Địa chỉ thiết bị gửi: nút bàn hoặc thiết bị nhân viên. Một không gian địa chỉ chung, không trùng nhau. |
| `boot_id` | uint32, định danh phiên của thiết bị; đổi sau mỗi lần khởi động lại. |
| `call_token` | uint32, ổn định cho một lần gọi và mọi lần gửi lại của nó (chỉ nút bàn). |
| `event_id` | 1..100 ký tự an toàn; gateway sinh ổn định từ node+boot+token+sequence+type. |
| `request_id` / `payload.request_seq` | UUID do PC cấp, hoặc số thứ tự tiếp nhận (uint32) để dùng trên RF. |
| `payload` | Chỉ các trường: `category`, `led`, `revision`, `battery_mv`, `battery_low`, `assignment_revision`, `request_seq`, `task`. Trường lạ bị từ chối. |

Nút bàn:
- `CALL` — bắt buộc `payload.category`. Gửi sau khi giữ đủ 5 giây. Gửi lại cùng `call_token` trả về cùng yêu cầu, không đổi thời điểm ghi nhận. CALL mới khi bàn đang có yêu cầu: trả yêu cầu hiện có, **không đổi loại, không reset thời gian** (ER-F06), ghi DUPLICATE.
- `STATUS_POLL` — chỉ khi đang có yêu cầu hoặc giao dịch chưa xong. Bàn rảnh ngủ, không heartbeat.
- `DONE` — bấm đúp nút ẩn. Hợp lệ với mọi yêu cầu đã ghi nhận, kể cả chưa được xác nhận hay chưa có nhân viên nhận (ER-F09). Không có correlation → từ chối `no_request_for_correlation`. Gửi lại sau khi đã đóng → gửi lại `DONE_RECEIPT`, ghi DUPLICATE.
- `STATUS_APPLIED` — bắt buộc `led` và `revision` đúng trạng thái hiện hành. Đây là bằng chứng duy nhất rằng đèn đã đổi.
- `NODE_HELLO` — gửi một lần sau khi khởi động lại/thay pin, trước khi nhận yêu cầu mới (ER-F05). PC trả trạng thái yêu cầu đang mở của bàn và gắn phiên mới vào yêu cầu đó; nếu không có thì trả `request_id: null`, `led: OFF`, `revision: 0`.
- `DEVICE_STATUS` — đo pin: `battery_mv`, `battery_low`. Không chứng minh trạng thái đèn.

Gateway:
- `COMMAND_ACK` — `command_id` + `node_id` đích. Chỉ nghĩa là gateway đã nhận qua USB.

Thiết bị nhân viên (luôn gửi `boot_id`; `call_token` bỏ qua):
- `STAFF_POLL` — liên lạc định kỳ (đề xuất 2 giây), có thể kèm pin.
- `STAFF_APPLIED` — thiết bị báo đang hiển thị gì: `payload.task` = `SHOWN` (biên nhận giao việc), `ACCEPTED`, `CLEARED`; kèm `assignment_revision` và `request_id` hoặc `request_seq`.
- `STAFF_ACCEPT` — người dùng bấm nhận, kèm `assignment_revision`. Phiên giao đã cũ → từ chối `stale_assignment` và PC gửi `DISPATCH_CANCEL`.

### Frame từ PC xuống thiết bị

Chung: `protocol_version`, `venue_id`, `message_type`, `command_id` (UUID, hoặc `null` với phản hồi không cần theo dõi), `node_id`, `request_id`, `payload`. Adapter USB gắn `event_id` của bản tin lên vào mỗi phản hồi. Gateway dùng ID này để ghép đúng lượt nghe, kể cả khi cùng node đã gửi poll mới hoặc khởi động lại.

| Loại | Đích | Payload |
|---|---|---|
| `CALL_RECEIPT` | nút bàn | `led`, `revision`, `category`, `request_seq`, kèm `boot_id`/`call_token`. **Chỉ gửi sau khi commit.** |
| `SET_REQUEST_STATUS` | nút bàn | như trên; trả lời poll/hello |
| `DONE_RECEIPT` | nút bàn | `led: OFF`; xác nhận hoàn tất |
| `DISPATCH` | thiết bị NV | `table_id`, `table_name`, `category`, `assignment_revision`, `request_seq`, `task: SHOWN` |
| `ACCEPT_RECEIPT` | thiết bị NV | như trên, `task: ACCEPTED` |
| `DISPATCH_CANCEL` | thiết bị NV | như trên, `task: CLEARED`, `reason`: reassigned/cancelled/completed/stale |
| `STAFF_STATUS` | thiết bị NV | `open_tasks`; phản hồi giữ liên lạc |
| `ERROR` | bất kỳ | `event_id`, `payload.reason` |

Quy tắc:
- Các lượt `CALL`, `STATUS_POLL`, `DONE`, `NODE_HELLO`, `STAFF_POLL` và `STAFF_ACCEPT` mở cửa sổ phản hồi mức ứng dụng (ER-F03, ER-R03). Khi thiết bị đã xác nhận trạng thái hiện hành, phản hồi có `command_id: null` và không tạo dòng outbox.
- Lệnh có `command_id` nằm trong outbox: `pending → gateway_received → applied`; `failed` sau 5 lần (lùi 1, 2, 4, 8, 16 giây), `expired` sau 120 giây, `superseded` khi trạng thái đổi. Chỉ phát khi thiết bị đích liên lạc, tối đa 4 frame mỗi lần.
- Nút bàn chỉ nhận frame đúng `boot_id`/`call_token` của mình và `revision` không giảm. `revision` chỉ tăng khi đèn phải đổi: ghi nhận (đỏ) → xác nhận (xanh) → hoàn tất (tắt). Giao việc và nhận việc không đổi `revision`.
- Thiết bị nhân viên đặt task theo `payload.task`; frame lặp không tạo task mới. Khi `boot_id` đổi, PC gửi lại toàn bộ việc đang mở.

## Phiên mẫu

1. Khách giữ nút Thanh toán 5 giây. Gateway → `CALL` (boot 123, token 7, BILL).
2. PC ghi yêu cầu R1 (`seq` 1, REGISTERED), correlation, sự kiện REGISTERED rồi commit. PC → `CALL_RECEIPT` RED/rev 1. Nút sáng đỏ liên tục, gửi `STATUS_APPLIED` RED/1.
3. Mất `CALL_RECEIPT`: nút gửi lại `CALL` (mỗi giây trong 5 giây đầu). PC trả lại R1, ghi DUPLICATE. Quá 5 giây chưa có xác nhận: nút hiển thị "chưa xác nhận" và tiếp tục gửi lại cùng định danh.
4. Quản lý bấm Xác nhận → ACKNOWLEDGED/rev 2. Lần poll kế tiếp PC → `SET_REQUEST_STATUS` GREEN/2; nút → `STATUS_APPLIED` GREEN/2.
5. Quản lý giao cho nhân viên 1 (thiết bị 101) → phiên giao 1. `STAFF_POLL` kế tiếp nhận `DISPATCH`; thiết bị rung, hiển thị bàn và loại, gửi `STAFF_APPLIED` SHOWN → trung tâm ghi DELIVERED.
6. Nhân viên bấm nhận → `STAFF_ACCEPT` rev 1 → trung tâm ghi ACCEPTED, trả `ACCEPT_RECEIPT`. Đèn bàn không đổi.
7. Bấm đúp nút ẩn → `DONE`. PC đóng R1, gỡ việc khỏi thiết bị nhân viên (`DISPATCH_CANCEL` reason completed), trả `DONE_RECEIPT` OFF/rev 3. Nút tắt đèn, ngủ.
8. Mất `DONE_RECEIPT`: nút giữ trạng thái "chờ xác nhận hoàn tất" và gửi lại `DONE`; PC không đóng thêm gì.
9. Cuộc gọi mới dùng token 8 → R2. `DONE` cũ (token 7) chỉ ánh xạ về R1, không bao giờ đóng R2.

Bước 5–6 có thể diễn ra trước bước 4: giao việc không cần xác nhận trước, và không làm đèn chuyển xanh.

## RF gateway ↔ thiết bị: frame 31 byte

nRF24L01+ dùng kênh 76, 1 Mbps, địa chỉ 5 byte, dynamic payload, CRC radio 16 bit và auto-ACK. Số nhiều byte theo little-endian. Lượt ghép đầu dùng `venue_id=1`, bàn `1` và thiết bị tay `101`. Cấu hình giữ địa chỉ RF theo cách đánh số của UT-06 V2.1.

| Pipe | 5 byte theo thứ tự truyền vào RF24 |
|---|---|
| Gửi lên gateway | `50 34 01 C3 A5` |
| Trả về nút bàn `n` (1–24) | `50 34 01 01 nn` (`nn` là `n` dạng hex) |
| Trả về thiết bị tay `n` (101–102) | `50 34 01 02 nn` (`nn` là `n - 100` dạng hex) |

| Offset | Byte | Kiểu | Ý nghĩa |
|---|---:|---|---|
| 0 | 1 | u8 | protocol version = 2 |
| 1 | 1 | u8 | kind: 1 CALL, 2 POLL, 3 DONE, 4 APPLIED, 5 STATUS, 6 HELLO, 8 STAFF_POLL, 9 STAFF_APPLIED, 10 STAFF_ACCEPT, 16 CALL_RECEIPT, 17 SET_STATUS, 18 DONE_RECEIPT, 24 DISPATCH, 25 ACCEPT_RECEIPT, 26 DISPATCH_CANCEL, 27 STAFF_STATUS, 255 ERROR |
| 2 | 2 | u16 | venue_id |
| 4 | 2 | u16 | device id (nút bàn hoặc thiết bị nhân viên) |
| 6 | 4 | u32 | boot/session id |
| 10 | 4 | u32 | nút bàn: call_token · nhân viên: request_seq |
| 14 | 2 | u16 | event sequence; gửi lại giữ nguyên |
| 16 | 4 | u32 | nút bàn: LED revision · nhân viên: assignment_revision |
| 20 | 1 | u8 | nút bàn: LED 0 OFF/1 RED/2 GREEN · nhân viên: task 1 SHOWN/2 ACCEPTED/3 CLEARED |
| 21 | 1 | u8 | category: 0 không có, 1 SERVICE, 2 BILL |
| 22 | 1 | u8 | flags: bit0 có số đo pin, bit1 pin yếu |
| 23 | 2 | u16 | Theo loại frame, xem bảng ngay dưới |
| 25 | 4 | u32 | gateway command tag; 0 nếu không theo dõi |
| 29 | 2 | u16 | CRC16-CCITT-FALSE của byte 0..28 (đề xuất, bổ sung cho CRC radio) |

| Loại frame | Byte 20 và 23–24 |
|---|---|
| `DEVICE_STATUS`, `STAFF_POLL` và uplink có kèm pin | Byte 23–24 là mV nếu bit 0 của flags bật. Bit 1 báo pin yếu. `DEVICE_STATUS` với bit 1 tắt báo pin bình thường. Với các uplink khác, hai bit đều tắt nghĩa là bỏ qua pin. |
| `DISPATCH`, `ACCEPT_RECEIPT`, `DISPATCH_CANCEL` | Byte 20 lần lượt là 1, 2, 3. Byte 23–24 là `table_id`. Tên bàn và lý do thu hồi lưu ở PC. |
| `STAFF_STATUS` | Byte 23–24 là `open_tasks` dạng `u16`, tối đa 24 việc với cấu hình 24 bàn. Byte 20 bằng 0. |
| `ERROR` | Byte 23–24 là mã lý do. Byte 20 bằng 0. |

Mã `ERROR` của R01 gồm `1 wrong_venue`, `2 unknown_node`, `3 unknown_staff_device`, `4 no_request_for_correlation`, `5 correlation_mismatch`, `6 stale_device_status`, `7 stale_assignment`, `8 event_id_collision`, `9 unknown_command`, `10 unknown_request` và `255` cho các lý do khác. Khung RF sai venue bị lọc tại gateway. Nếu PC từ chối venue, thông báo `ERROR` chỉ được chuyển khi khớp cấu hình và đúng lượt nghe.

Gateway ghi nhớ 48 ánh xạ gần nhất giữa `command_tag` và `command_id`. Tag `0` dành cho phản hồi không theo dõi. Khi thiết bị báo `STATUS_APPLIED` hoặc `STAFF_APPLIED` với tag còn trong bộ nhớ, gateway kiểm node, boot, token hoặc `request_seq`, revision và trạng thái. Sau khi mất ánh xạ, PC vẫn đối soát theo các trường ứng dụng. PC giữ ánh xạ bền từ bộ `(node, boot, call_token)` sang UUID của bàn. Gateway có thể điền UUID đã thấy vào `STATUS_APPLIED`. Thiết bị tay dùng `request_seq` để đối soát việc.

Phản hồi xuống dùng `boot_id` và `event sequence` của lượt nghe. Với nút bàn, `call_token` trong JSON cũng phải khớp. Thời gian thử là 250 ms từ uplink, gồm thời gian dự phòng cho lần phát RF. Khi lỡ lượt, gateway bỏ bản trả cũ và PC giữ cơ chế gửi lại theo outbox/poll. Chỉ `CALL_RECEIPT` hoặc `DONE_RECEIPT` do PC gửi sau commit mới xác nhận kết quả ứng dụng.

### Vector ghép đầu

`CALL Bill` cho bàn 1, `boot_id=123`, `call_token=7`, `event_seq=1`, CRC `0x53EC`:

```text
02 01 01 00 01 00 7B 00 00 00 07 00 00 00 01 00 00 00 00 00 00 02 00 00 00 00 00 00 00 EC 53
```

Frame USB tương ứng là ví dụ `CALL` ở đầu tài liệu. Gửi lại nguyên vector giữ `event_id` là `1.123.7.1.CALL`.

Các vector dưới đây dùng tag cố định để đối chiếu codec. Gateway cấp tag khi chạy để liên kết lệnh USB với báo cáo từ thiết bị.

| Vector | 31 byte theo thứ tự truyền |
|---|---|
| `CALL Service` | `02 01 01 00 01 00 7B 00 00 00 08 00 00 00 02 00 00 00 00 00 00 01 00 00 00 00 00 00 00 9D D2` |
| `SET_REQUEST_STATUS GREEN` | `02 11 01 00 01 00 7B 00 00 00 07 00 00 00 02 00 02 00 00 00 02 02 00 00 00 04 03 02 01 88 70` |
| `DONE` | `02 03 01 00 01 00 7B 00 00 00 07 00 00 00 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 BB D8` |
| `DONE_RECEIPT OFF` | `02 12 01 00 01 00 7B 00 00 00 07 00 00 00 03 00 03 00 00 00 00 02 00 00 00 00 00 00 00 2E D5` |
| `DISPATCH` | `02 18 01 00 65 00 29 00 00 00 01 00 00 00 01 00 01 00 00 00 01 02 00 01 00 05 03 02 01 9C D3` |
| `STAFF_ACCEPT` | `02 0A 01 00 65 00 29 00 00 00 01 00 00 00 02 00 01 00 00 00 00 00 00 00 00 00 00 00 00 E0 A2` |
| `ACCEPT_RECEIPT` | `02 19 01 00 65 00 29 00 00 00 01 00 00 00 02 00 01 00 00 00 02 02 00 01 00 00 00 00 00 3F AA` |
| `DISPATCH_CANCEL` | `02 1A 01 00 65 00 29 00 00 00 01 00 00 00 03 00 01 00 00 00 03 02 00 01 00 00 00 00 00 5C 82` |
| `DEVICE_STATUS`, 2150 mV và pin yếu | `02 05 01 00 01 00 7B 00 00 00 07 00 00 00 05 00 00 00 00 00 00 00 03 66 08 00 00 00 00 FE DD` |
| `ERROR no_request_for_correlation` | `02 FF 01 00 01 00 7B 00 00 00 07 00 00 00 04 00 00 00 00 00 00 00 00 04 00 00 00 00 00 00 77` |

Trả lời qua ACK payload chỉ an toàn khi biết chắc người nhận; với pipe dùng chung, gateway phải gửi phản hồi có địa chỉ trong cửa sổ nhận của thiết bị (logbook Step 5 "Return scheduling"). Chu kỳ poll 5 giây là giả định của mô hình năng lượng, không phải yêu cầu.

## Ranh giới thiết bị nhân viên

Sản phẩm dùng thiết bị cầm tay chuyên dụng qua gateway (C-04, C-06), không dùng điện thoại cá nhân. `backend/app/adapters/staff.py` cung cấp thiết bị ảo phát đúng các frame trên: dùng cho simulator, và làm stub chẩn đoán ở chế độ phần cứng khi đặt `PBL_STAFF_TOKEN` (bound với `PBL_STAFF_ID`, qua `/api/staff-device/{id}`). Không có thao tác hoàn tất trong giao thức nhân viên.
