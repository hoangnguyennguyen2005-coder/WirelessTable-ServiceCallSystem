# Bảng chuyển trạng thái

Nguồn: logbook Step 1 §1.5.2, Step 5 "Request state and fault rules". Mọi thay đổi + nhật ký + outbox nằm trong một transaction. Thời gian lấy từ đồng hồ trung tâm.

Một yêu cầu có **hai chiều độc lập**:

- **Vòng đời** (điều khiển đèn bàn): `REGISTERED` (đỏ) → `ACKNOWLEDGED` (xanh) → `COMPLETED` (tắt).
- **Giao việc** (không đổi đèn): `NONE` → `DISPATCHED` → `DELIVERED` → `ACCEPTED`, có thể thu hồi hoặc giao lại.

Quá hạn, mất liên lạc, pin yếu, chưa đồng bộ là cờ kèm theo, không phải trạng thái.

## Vòng đời

| Trước | Sự kiện | Điều kiện | Sau | Lệnh xuống bàn | Từ chối |
|---|---|---|---|---|---|
| bàn rảnh | CALL | node đã đăng ký và đang bật; có category | REGISTERED, cấp `seq`, `received_at` | CALL_RECEIPT RED rev 1 | unknown_node, disabled_node, wrong_venue |
| đang mở | CALL (gửi lại hoặc token mới) | cùng bàn | không đổi (loại, thời gian, thứ tự giữ nguyên) | trạng thái hiện hành | — (ghi DUPLICATE) |
| REGISTERED | quản lý ACK | `expected_version` khớp | ACKNOWLEDGED, rev +1 | SET_REQUEST_STATUS GREEN | version cũ |
| ACKNOWLEDGED | ACK lặp | — | không đổi | — | — |
| REGISTERED / ACKNOWLEDGED | DONE | correlation trỏ đúng yêu cầu | COMPLETED, `closed_from` = `vòng đời/giao việc`, rev +1 | DONE_RECEIPT OFF; gỡ việc khỏi thiết bị NV | no_request_for_correlation |
| COMPLETED | DONE gửi lại | cùng correlation | không đổi | gửi lại DONE_RECEIPT | — (ghi DUPLICATE) |
| đang mở | NODE_HELLO | phiên mới của cùng bàn | không đổi, gắn phiên mới | trạng thái hiện hành | correlation_mismatch |
| đang mở | STATUS_APPLIED | đúng yêu cầu, đúng rev và đèn | ghi nhận bàn đã hiển thị | — | stale_device_status |
| đang mở | đủ ≥ 300 giây từ `received_at` | chưa nhắc | không đổi; `reminded_at`, sự kiện OVERDUE một lần | — | — |

DONE hợp lệ ở REGISTERED (chưa được xác nhận) và ở mọi giai đoạn giao việc (ER-F09). Nhắc áp dụng cả khi đã xác nhận hoặc đã có người nhận; không reset tuổi hay thứ tự (ER-F08).

## Giao việc

| Trước | Sự kiện | Điều kiện | Sau | Lệnh tới thiết bị NV | Từ chối |
|---|---|---|---|---|---|
| NONE | quản lý giao | yêu cầu đang mở; nhân viên hoạt động, khả dụng, có thiết bị | DISPATCHED, phiên giao +1 | DISPATCH | version cũ, không khả dụng, chưa gán thiết bị |
| DISPATCHED | STAFF_APPLIED SHOWN | đúng phiên hiện hành | DELIVERED | — | phiên cũ → DISPATCH_CANCEL |
| DISPATCHED / DELIVERED | STAFF_ACCEPT | đúng nhân viên và phiên | ACCEPTED | ACCEPT_RECEIPT | stale_assignment |
| ACCEPTED | STAFF_ACCEPT lặp | — | không đổi | gửi lại ACCEPT_RECEIPT | — (ghi DUPLICATE) |
| đã giao | giao cho người khác | nếu ACCEPTED cần `confirm` | DISPATCHED với phiên mới | DISPATCH_CANCEL cho máy cũ, DISPATCH cho máy mới | thiếu confirm |
| đã giao | thu hồi | nếu ACCEPTED cần `confirm` | NONE | DISPATCH_CANCEL | thiếu confirm |
| DISPATCHED / DELIVERED | gửi lại | — | không đổi, tạo lệnh mới | DISPATCH | đã nhận |
| đã giao | yêu cầu hoàn tất | — | phiên giao đóng (giữ lại tên nhân viên trong lịch sử) | DISPATCH_CANCEL | — |

Không có chuyển trạng thái nào từ giao việc sang vòng đời: nhân viên nhận việc không làm đèn xanh và không đóng yêu cầu (ER-F04, ER-F07). Thiếu phản hồi không bao giờ được hiểu là đã xác nhận hay đã hoàn tất (ER-R03).

## Cờ "chưa giải quyết" (hiển thị và ghi FAILURE một lần mỗi đợt)

ER-R03 yêu cầu trạng thái chưa giải quyết hiện trên màn hình quản lý trong 10 giây. Cờ bật ở 8 giây để còn 2 giây cho nhịp kiểm tra (0,5 giây) và lúc màn hình tải lại; không bao giờ dưới 1 chu kỳ poll của thiết bị + 2 giây. Mốc 10 giây của đèn bàn (đỏ chớp đôi) là hành vi của nút, giữ nguyên.

| Cờ | Điều kiện |
|---|---|
| table_state_not_applied | bàn chưa báo hiển thị đúng rev sau > 8 giây |
| table_contact_lost | bàn đang có yêu cầu không liên lạc > 8 giây (10 − 2 giây dự phòng; tối thiểu 1 chu kỳ poll + 2) |
| dispatch_not_delivered | đã giao > 8 giây mà thiết bị chưa báo hiển thị |
| staff_device_contact_lost | thiết bị đang có việc không liên lạc > 8 giây |
| command_failed / command_expired | lệnh không được xác nhận sau 5 lần / 120 giây |

## Nút bàn (mô phỏng trong `simulator.py`, đề xuất cho firmware)

| Hiển thị | Khi nào |
|---|---|
| đỏ nhấp nháy | đang giữ nút; và sau khi gửi, trong 5 giây chờ xác nhận |
| đỏ sáng | trung tâm xác nhận đã ghi nhận |
| xanh sáng | xác nhận của quản lý đã tới bàn |
| đỏ chớp đôi | đăng ký chưa được xác nhận sau 5 giây, hoặc mất liên lạc 10 giây |
| đỏ/xanh luân phiên | đã báo hoàn tất, chờ trung tâm xác nhận |
| tắt | rảnh, hoặc hoàn tất đã được xác nhận |

Các mẫu đèn là đề xuất của logbook (Step 6 §6.3), còn chờ thử với người dùng theo ER-U02.
