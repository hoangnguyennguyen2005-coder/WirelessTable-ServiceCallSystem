# Kết quả kiểm tra — phần mềm trung tâm

Ngày chạy: 2026-11-19 (cập nhật sau buổi kiểm tra UT-11, UT-12, AT-07), Windows 10, Python 3.14, Node 26. Mọi bằng chứng dưới đây là **phần mềm**; không có phần cứng nào được nối. Ánh xạ yêu cầu ↔ test ở `traceability.md`.

## Lệnh đã chạy

| Lệnh (tại thư mục gốc) | Kết quả |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q` | 63 passed, 1 skipped (test PTY chỉ chạy trên Linux) |
| `.venv\Scripts\python.exe -m ruff check backend tools` | sạch |
| `.venv\Scripts\python.exe -m pip check` | sạch |
| `npm --prefix frontend run typecheck` | qua |
| `npm --prefix frontend run lint` | qua |
| `npm --prefix frontend run format:check` | qua |
| `npm --prefix frontend run build` | qua |
| `npm --prefix frontend run test:e2e` với `PBL_E2E_CHANNEL=chrome` | 3 passed |

Ghi chú trung thực về các lần chạy:

- `test_emulator_loopback_table_and_staff_round_trip` hỏng **một lần** trong một lần chạy cả bộ, ngay sau khi E2E kết thúc. Chạy lại cả bộ 2 lần và riêng test đó hơn 60 lần (kể cả khi ép tải CPU) đều qua; chưa tái hiện được và chưa xác định nguyên nhân. Test này chạy hai luồng theo thời gian thực nên nhiều khả năng là lỗi thời gian của test, nhưng điều đó chưa được chứng minh.
- `npx playwright install chromium` bị treo khi giải nén trên máy này, nên E2E chạy bằng Chrome cài sẵn qua biến `PBL_E2E_CHANNEL`. Chưa chạy với Chromium do Playwright tải về trên Windows.
- `test_shipped_emulator_real_pty` (emulator chạy tiến trình riêng qua PTY thật) không chạy được trên Windows; lần gần nhất nó chạy là trên Linux với giao thức v1, **chưa chạy lại với giao thức v2**.
- Emulator qua cặp cổng COM ảo trên Windows chưa được thử (máy không có driver cặp cổng).

## E2E (Chrome, 1366×768 và 390×844)

1. Giữ ngắn bị hủy; giữ 5 giây gọi Thanh toán → quản lý xác nhận → bàn báo đèn xanh → giao việc → thiết bị nhân viên hiện việc → nhận việc → bấm đúp nút ẩn → đèn tắt, việc rời thiết bị, lịch sử và nhật ký có bản ghi. Không có nút hoàn tất trên web. Không tràn ngang, không lỗi trang.
2. Bốn bàn gọi đồng thời, tua 300 giây → 4 yêu cầu quá hạn; ngắt/nối gateway mô phỏng; trình duyệt offline rồi online lại vẫn chỉ một kết nối SSE.
3. API thiết bị nhân viên lỗi 503 rồi phục hồi; giao việc tới thiết bị đang tắt hiện "Chưa tới thiết bị nhân viên".

Ảnh `screenshots/dashboard.png` và `screenshots/staff.png` do lần chạy E2E này sinh ra và đã được xem lại.

## Chưa kiểm chứng

- Mọi thứ cần phần cứng: tầm phủ, độ trễ và tỷ lệ truyền RF, dòng tiêu thụ, pin, vỏ, lắp đặt, thử với người dùng, tương thích firmware. Các phiếu IT-01…IT-03 và AT-01…AT-07 của logbook chưa phiếu nào được thực hiện.
- Mất điện thật của PC (chỉ thử đóng/mở lại tiến trình và database).
- Chạy liên tục nhiều giờ, dữ liệu 30 ngày thật (chỉ thử bằng đồng hồ giả).
- Migrate database v1 có dữ liệu vận hành thật (chỉ thử với dữ liệu dựng trong test).

## Buổi kiểm tra UT-11, UT-12, AT-07 (2026-11-19)

Làm theo hướng dẫn test của nhóm, trên chế độ mô phỏng. Bằng chứng nằm trong `evidence/` (chưa commit); bản điền phiếu ở `evidence/dien-phieu-logbook.md`. Buổi kiểm tra tìm ra 6 lỗi, đều đã sửa và có test hoặc E2E tương ứng:

| Lỗi | Sửa | Kiểm lại |
|---|---|---|
| Trung tâm ghi mất liên lạc với bàn sau 12,1 s (> 10 s, ER-R03) | Bốn cờ chưa giải quyết bật ở 8 s (10 − 2 s dự phòng) | `test_watch_records_unresolved_conditions_once`; trên màn hình, trường hợp xấu nhất 6,1–8,5 s |
| "Chưa tới thiết bị nhân viên" hiện sau 10,5–10,7 s | Cùng ngưỡng 8 s | AT-07 lần cuối: 8,3 s |
| Lỗi giả lập một lần bị bàn khác dùng mất | Lỗi gắn với bàn đang chọn | `test_fault_armed_for_one_table_is_not_used_by_another` |
| Tab Nhật ký sự kiện không tự cập nhật | Tải lại theo `generation` của snapshot | E2E test 2 |
| Đồng hồ chờ có lúc dừng hoặc nhảy 2 giây | Giữ độ lệch đồng hồ cố định, vẽ lại 4 lần/giây | 40 s, 4 đồng hồ: 157 lần đổi, 0 lần nhảy |
| Máy nhân viên mô phỏng tự bật lại khi trung tâm khởi động lại | Lưu trạng thái tắt/bật | `test_switched_off_staff_device_stays_off_after_centre_restart` |

Kết quả cuối: UT-11 và UT-12 đạt; AT-07 (diễn tập mô phỏng) đạt 10/10 dòng phần mềm, dòng 5b không làm, cả phiếu BLOCKED chờ phần cứng. Đèn bàn mô phỏng chuyển sang "chưa xác nhận" đúng ở 5,0 s, đạt ranh giới "trong 5 s" nhưng không có khoảng dư; đã ghi để nhóm firmware cân nhắc.
