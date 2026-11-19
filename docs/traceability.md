# Truy vết logbook ↔ phần mềm trung tâm

Đối chiếu Table 3.4.1 (33 ER), Table 3.4.2 (C-01…C-09) và kế hoạch test Step 6 của logbook với mã nguồn trong repository này (work package 4: web/app tại máy trung tâm, kèm simulator và công cụ giả lập gateway).

Cách đọc cột **Mức**:

- **PM** — phần mềm trung tâm đã triển khai và có test tự động. Đây là bằng chứng *phần mềm*, chưa phải kết quả phiếu AT/IT của logbook, vì các phiếu đó yêu cầu phần cứng thật.
- **PM một phần** — phần thuộc máy trung tâm đã có; phần còn lại thuộc firmware/phần cứng.
- **PC** — chỉ kiểm được trên phần cứng hoặc tại quán; repository không có bằng chứng.

Test nằm trong `backend/tests/`: `D` = `test_domain.py`, `R` = `test_records.py`, `A` = `test_adapters.py`, `P` = `test_api.py`, `E` = `test_emulator.py`, `e2e` = `frontend/tests/e2e.spec.ts`.

## 33 yêu cầu kỹ thuật

| ER | Nội dung kiểm (logbook) | Mức | Trong phần mềm | Test |
|---|---|---|---|---|
| P01 | Tầm phủ, 10/10 vị trí | PC | — | — |
| P02 | Lô 100 cuộc gọi, kết quả nhìn thấy được | PM một phần | Mỗi lần gọi kết thúc bằng "đã ghi nhận" hoặc "chưa xác nhận"; đo tỷ lệ RF là việc của AT-03 | A `test_registration_unconfirmed_after_5_seconds_then_reconciled`, `test_delayed_then_lost_call_claims_nothing_until_registered` |
| P03 | 24 ID đang mở, FIFO, tuổi ≥1 Hz | PM | `seq` tăng dần, hàng đợi theo `seq`, đồng hồ chờ 1 giây ở giao diện | D `test_24_tables_fifo_by_acceptance_sequence_with_equal_timestamps` |
| P04 | Thời gian ACK tới bàn và hoàn tất quay về | PM một phần | Ghi `acknowledged_at`, thời điểm bàn báo đã hiển thị, cờ `table_state_not_applied` sau 10 giây; trị số thật phải đo trên RF | A `test_ack_reaches_table_on_next_poll_and_latency_is_recorded` |
| P05 | Thời gian giao việc và nhận việc | PM một phần | Tách đã gửi / đã hiển thị / đã nhận, cờ `dispatch_not_delivered` | D `test_dispatch_delivery_and_acceptance_are_distinct`; A `test_dispatch_to_powered_off_device_stays_unresolved_then_delivers`; e2e 3 |
| F01 | Đúng bàn / loại / ID | PM | Frame v2 có `venue_id`, `node_id`, `payload.category`; trung tâm cấp ID | D `test_category_is_registered_and_never_replaced`; A `test_parser_rejects_frames_that_break_the_v2_contract` |
| F02 | Giữ 5 giây, thả sớm, không lặp | PM một phần | Mô hình trong simulator; debounce GPIO là UT-01 của firmware | A `test_hold_qualification_exactly_one_attempt_at_5_seconds`, `test_first_control_wins_and_continued_hold_adds_nothing`; e2e 1 |
| F03 | Commit trước khi đỏ; mất phản hồi | PM | Phản hồi chỉ sinh sau commit `synchronous=FULL` | R `test_no_confirmation_without_durable_commit`, `test_crash_after_commit_before_reply_is_reconciled_by_retry`; A `test_lost_registration_reply_is_reconciled_by_retry` |
| F04 | Chỉ quản lý làm đèn xanh | PM | ACK USB/RF, giao việc, nhận việc không đổi vòng đời | D `test_only_manager_ack_turns_table_green` |
| F05 | Trùng lặp / cũ / khởi động lại | PM | Bảng correlation, fingerprint sự kiện, NODE_HELLO | D `test_registration_retry_restart_and_concurrent`, `test_event_collision_unknown_node_venue_and_idempotency`, `test_node_restart_reconciles_before_new_request`; A `test_duplicated_registration_frame_gives_one_request`, `test_restarted_node_reconciles_before_admitting_a_new_request` |
| F06 | Không thay yêu cầu đang mở, không reset tuổi | PM | Unique index một yêu cầu mở mỗi bàn | D `test_category_is_registered_and_never_replaced`, `test_registration_retry_restart_and_concurrent` |
| F07 | Thiết bị chuyên dụng, nhận tường minh | PM một phần | Kênh `staff` của giao thức, phiên giao, thiết bị ảo; màn hình/rung là UT-07 | D `test_reassign_invalidates_old_assignment_and_stale_accept`, `test_cancel_and_retry_dispatch`; A `test_staff_device_shows_task_once_and_accepts_explicitly`, `test_acceptance_stays_pending_until_confirmed_or_cancelled`, `test_reassignment_clears_the_old_device` |
| F08 | Quá hạn từ 300 giây dù đã ACK/nhận | PM | `remind()` với ≥300 giây, một lần | D `test_reminder_from_300_seconds_once_without_reset`, `test_completed_before_threshold_is_never_reminded`; e2e 2 |
| F09 | Bấm đúp đúng ID; bấm đơn và lúc rảnh | PM một phần | DONE đóng mọi yêu cầu đã ghi nhận; cửa sổ ≤1 giây trong simulator | D `test_done_closes_any_registered_request_and_old_done_cannot_close_new`, `test_done_without_registered_request_creates_nothing`; A `test_double_press_window_single_press_and_idle` |
| F10 | Đóng bền trước khi tắt đèn; chờ / gửi lại | PM | DONE_RECEIPT sau commit; bàn giữ trạng thái chờ tới khi nhận | A `test_completion_stays_pending_until_centre_confirms`; R `test_crash_after_commit_before_reply_is_reconciled_by_retry` |
| F11 | 8 loại sự kiện, ≥30 ngày, CSV | PM | Bảng `events`, `/api/events.csv`, `PBL_RETENTION_DAYS` ≥ 30 | R `test_eight_event_types_are_recorded_and_exported`, `test_event_retention_never_deletes_before_30_days` |
| E01 | Điện tích chu kỳ / ngủ, dung lượng | PC | Poll 5 giây chỉ là giả định của mô hình năng lượng | — |
| E02 | 3,2–2,0 V, cảnh báo / cắt | PM một phần | Trung tâm hiển thị và ghi BATTERY_LOW theo cờ thiết bị hoặc ngưỡng tùy chọn; ngưỡng thật còn OPEN | D `test_low_battery_flag_and_optional_threshold`; A `test_simulated_battery_warning_reaches_the_centre` |
| O01–O03 | Lau, dầu, tràn nước, kích thước, lực | PC | — | — |
| R01 | Toàn quy trình khi tắt Internet và router | PM một phần | Không gọi dịch vụ ngoài, không CDN, chỉ loopback; chưa thử tại quán | P `test_api_lifecycle_security_history_config`; e2e 1 |
| R02 | Lỗi một nút, các nút khác vẫn chạy | PM một phần | Lỗi và outbox tách theo thiết bị | A `test_failed_node_does_not_block_other_tables_or_invent_calls` |
| R03 | Lộ lỗi trong 5 giây / 10 giây | PM | `watch()` và 4 cờ chưa giải quyết; nút tự báo "chưa xác nhận" sau 5 giây | D `test_watch_records_unresolved_conditions_once`; A `test_contact_loss_is_visible_within_10_seconds_and_recovers`, `test_command_backoff_limit_expiry_restart` |
| R04 | Khởi động lại / mất điện, thời gian khôi phục | PM một phần | Khôi phục từ SQLite, ghi CENTRE_START kèm thời gian; mất điện thật của PC chưa thử | R `test_restart_restores_requests_order_states_and_commands`; A `test_simulator_rehydrates_active_requests_after_restart`; `test_backup.py` |
| C01 | BOM 24 bàn | PC | — | — |
| U01 | 9/10 tác vụ, đào tạo ≤10 phút | PC | Giao diện tiếng Việt, mọi trạng thái có chữ; chưa thử với người dùng | — |
| U02 | 10 khách, 5 nhân viên đánh giá | PC | Mẫu đèn trong simulator là đề xuất để đem thử | — |
| M01, M02 | Lắp đặt, thay pin | PC | — | — |
| M03 | Dựng lại, quán thứ hai cách ly | PM một phần | `PBL_VENUE_ID`, database gắn venue, frame sai venue bị từ chối | R `test_database_belongs_to_one_venue`, `test_second_venue_differs_only_by_configuration`; P `test_database_of_another_venue_is_refused` |
| S01, S02 | Quy định tần số, an toàn pin | PC | — | — |

## Ràng buộc

| Mã | Phần mềm đáp ứng thế nào |
|---|---|
| C-01 | Quy trình 6 bước giữ nguyên; xem `state-machine.md`. |
| C-02 | Cấu hình radio miễn cấp phép: thuộc firmware/ER-S01; phần mềm không đặt kênh hay công suất. |
| C-03 | Không có gọi món, tính tiền, thanh toán, POS, cloud. "Thanh toán" chỉ là loại yêu cầu gọi nhân viên. |
| C-04 | Nhân viên dùng thiết bị chuyên dụng qua gateway; trang `/staff` chỉ là máy ảo (simulation) hoặc stub chẩn đoán có token (hardware). Seed demo có 2 thiết bị. |
| C-05 | Chạy trên PC tại quán, loopback, không phụ thuộc Internet; Concept C cũng không cần router của quán. |
| C-06 | Không dùng điện thoại cá nhân của khách hay nhân viên trong quy trình. |
| C-07, C-08 | Lịch demo và ngân sách: ngoài phạm vi mã nguồn (logbook ghi UNKNOWN). |
| C-09 | Không khoan, không đi dây: thuộc phần cứng; PC chỉ cần một cổng USB cho gateway. |

## Kế hoạch test Step 6

| Phiếu | Chủ đề | Tình trạng ở repository |
|---|---|---|
| UT-10 | Tiếp nhận, FIFO, khử trùng lặp, 24 ID | Tự động: `test_domain.py` |
| UT-11 | Lưu bền, thứ tự commit/xác nhận, khôi phục, CSV, lưu giữ | Tự động: `test_records.py`, `test_backup.py` |
| UT-12 | Giao diện quản lý, tuổi, nhắc 300 giây, giao việc | Tự động: `test_domain.py`, `test_api.py`, e2e |
| UT-01…UT-03 | Nút, cửa sổ thời gian, trạng thái/đèn của nút bàn | Chỉ có mô hình tham chiếu trong simulator (`test_adapters.py`); firmware chưa có |
| UT-04…UT-06 | Khung RF, lập lịch, cầu USB | Phía PC: parser NDJSON, kết nối lại, outbox (`test_adapters.py`, `test_emulator.py`); phía gateway chưa có |
| UT-07, UT-08 | Hiển thị và nhận việc trên thiết bị nhân viên | Mô hình thiết bị ảo; thiết bị thật chưa có |
| UT-09 | Đo áp, ngủ | Phần cứng |
| IT-01 | Bàn – gateway – PC | Chạy được với `tools/serial_emulator.py`; chưa chạy với phần cứng |
| IT-02 | Giao việc – nhận – đóng | Như trên; stub chỉ để chẩn đoán |
| IT-03 | Nguồn và khôi phục | Chỉ phần khởi động lại phần mềm |
| AT-01, AT-07 | Quy trình và lỗi/khôi phục | Có kịch bản tương ứng trong simulator và test; phiếu chính thức cần phần cứng thật |
| AT-02…AT-06 | Lắp đặt, tầm phủ, BOM, pin, người dùng | Phần cứng / tại quán |

## Các nhóm vấn đề còn mở trong logbook và chỗ phần mềm chờ

- Cửa sổ bấm đúp, mẫu đèn, nội dung hiển thị: đang là tham số/đề xuất (`PBL_DOUBLE_MS`, simulator), đổi sau khi thử với người dùng.
- Ngưỡng pin yếu và cắt: `PBL_LOW_BATTERY_MV` tắt mặc định; trung tâm tin cờ `battery_low` của firmware.
- Khung RF, kênh, địa chỉ, tốc độ, số lần gửi lại: không định nghĩa ở đây; `protocol.md` chỉ quy định ranh giới USB giữa gateway và PC.
- Timeout khi nhân viên chưa nhận: chưa đặt; trung tâm chỉ hiển thị, không tự leo thang.
