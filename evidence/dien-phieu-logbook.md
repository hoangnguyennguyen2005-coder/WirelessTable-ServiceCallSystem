# Bản điền sẵn phiếu logbook: UT-10, UT-11, UT-12, AT-07

Các ô giữ tiếng Anh như phiếu trong logbook. Số liệu lấy từ lần chạy cuối ngày 19/11/2026 trên bản phần mềm đã sửa. Những chỗ `<...>` bạn tự điền. Cột P/F/N/A là đề xuất của tôi; người duyệt quyết định.

Ô **Tester** nên ghi đúng cách chạy, ví dụ: `<tên bạn> (supervised; steps executed by automated scripts in evidence/cong-cu on the team PC)`. Người duyệt phải khác người chạy.

**Hardware and software versions** (dùng chung cho ba phiếu):
HW: none (software-only) on venue PC, Windows 10 Pro build 19045, Intel Core i5-1145G7, 15.7 GB RAM. App: PBL4 central app (working tree of 19/11/2026, after fixes), DB schema v2, USB protocol v2, Python 3.14.10, pytest 8.4.2, FastAPI 0.121.0, Node 26.13.0, Chrome 157.0.8103.80, Playwright 1.56.1. Defaults: poll 5 s, unresolved 10 s (flags at 8 s), reminder 300 s, retention 90 d.

---

## UT-10 — Run UT10-20261119-02 · Overall: **PASS**

(-01 = buổi sáng, trước khi sửa, bản lưu ở UT-10/truoc-sua. -02 = chạy lại trên bản cuối.)

| # | P/F | Actual result and evidence |
|---|---|---|
| 1 | P | 1 test PASSED (buoc-1.txt): 24 distinct IDs; queue order = admission order (7, 3, 24, 1, …); sequence 1–24 with identical registration times. |
| 2 | P | 3 tests PASSED (buoc-2.txt): SERVICE from an active BILL table ignored and logged as DUPLICATE; category, time and sequence unchanged; replay after restart and 8 concurrent sends → one ID. |
| 3 | P | 4 cases PASSED (buoc-3.txt): new ID after completion; replayed old completion leaves the new request open (before ACK, after ACK, delivered, accepted); late green status rejected. |
| 4 | P | 4 tests PASSED (buoc-4.txt): duplicate acceptance has no effect (DUPLICATE); restarted node reconciles its original request; rejected frames logged as FAILURE while other tables continue; a failed table does not block the others. |

Reset and overall result: Temporary test databases removed automatically; no production data. All 4 rows P → PASS.

---

## UT-11 — Run UT11-20261119-02 · Overall: **PASS**

(-01 = buổi sáng, trước khi sửa, bản lưu ở UT-11/truoc-sua. -02 = toàn bộ bước 1–4 chạy lại trên bản cuối.)

| # | P/F | Actual result and evidence |
|---|---|---|
| 1 | P | Registration test PASSED (buoc-1.txt). Supplementary closure test PASSED (buoc-1b.txt): injected commit failure on completion → request stays REGISTERED, no DONE_RECEIPT; DONE retry → DONE_RECEIPT with LED OFF, exactly one COMPLETED. |
| 2 | P | 2 tests PASSED (buoc-2.txt). Reopened store identical: 3 requests (ACKNOWLEDGED / REGISTERED+ACCEPTED / REGISTERED), sequence 1–3 and times kept; pending green command still delivered after restart. Crash after commit before reply → retry gives the same request and original time, log REGISTERED + DUPLICATE. Real process kill: see AT-07 row 5a. |
| 3 | P | PASSED (buoc-3.txt). Live export from AT-07 (AT-07/pbl4-events.csv): 14 columns, all 8 types present, ISO 8601 +07:00, no guest column (AT-07/dem-loai.txt). |
| 4 | P | 2 tests PASSED (buoc-4.txt). Controlled clock fixture (simulated days 29/30/31): day 29 and 30 kept, day 31 pruned, each step across a restart; retention below 30 d rejected by config and raised to 30 by the service. Online backup/restore identical. Not a month-long live trial. |

Reset and overall result: Temporary pytest databases only; no production data. All rows P → PASS.

---

## UT-12 — Run UT12-20261119-02 · Overall: **PASS**

(-01 = buổi chiều trước khi sửa: đồng hồ trên màn hình có lúc nhảy 2 giây, xem README-bang-chung.txt mục 5.)

| # | P/F | Actual result and evidence |
|---|---|---|
| 1a | P | Fake clock 299.9 s: no reminder (buoc-1.txt). Screen: every change of the waiting time was +1 s; 40 s check of 4 timers sampled every 100 ms: 157 changes, 0 skips (dong-ho-cho-40s.txt); 10 s sample + 11 per-second frames (dong-ho-cho-mau.txt, dong-ho-cho/). Defect found and fixed during this test: the timer could stall or skip one second; run -01 showed 0:02 → 0:04. |
| 1b | P | At 300.0 s: exactly one reminder (OVERDUE recorded once); repeated check and check after restart → no second reminder (buoc-1.txt). |
| 1c | P | Second request at its own 300.1 s (t = 1310.1): one reminder; already-reminded request not repeated (buoc-1.txt). |
| 2 | P | Request acknowledged, dispatched, delivered and accepted before 300 s still reminded at 300.0 s; registration time and sequence unchanged; queue order kept (buoc-1.txt). Screen after +300 s: 4 tables “Quá 5 phút”, banner “Nhắc: 4 yêu cầu…”, order 01–04 unchanged (UT12_nhac-5-phut.png). |
| 3 | P | 2 tests PASSED (buoc-3.txt): dispatched → delivered (not accepted) → accepted only after the staff press; acceptance never completes the request; acceptance during link loss stays pending. |
| 4 | P | 3 tests PASSED (buoc-4.txt): reassignment requires confirmation, clears the old device, late old acceptance rejected. Completed request + 600 s → no reminder (buoc-1.txt). |

Reset and overall result: Fake clock and temporary DB; screen checks on a separate data-test profile, removed afterwards. All rows P → PASS.

---

## AT-07 — Run AT07-20261119-04 · Overall: **BLOCKED** (pending hardware session)

Simulation rehearsal: 24 simulated tables, simulated gateway, simulated staff devices #101/#102, separate data-at07 database (backed up). Instrument: scripted Chrome session (evidence/cong-cu/at07.cjs), state polled every 0.1 s, timeline.txt instead of a phone stopwatch. Runs -01 to -03 found the defects listed in README-bang-chung.txt and are kept in lan-01 to lan-03.

| # | P/F | Actual result and evidence |
|---|---|---|
| 1a | P* | SIMULATION: gateway disconnected; after the 5 s hold the table showed “unconfirmed · double red blink” at 5.0 s (other runs 4.8–4.9 s); never steady red; 0 requests during the outage. After reconnect: steady red after 5.1 s, exactly 1 request. *The indication changes exactly at 5.0 s after the hold qualifies, so it meets “by 5 s” with no margin; flagged to WP1. Real radio-ACK case BLOCKED (no hardware). AT07_1a_*.png, timeline.txt. |
| 1b | P | SIMULATION: fault “drop centre reply once” armed for table 02 only; table retried and showed steady red after 1.1 s; 1 BILL request; log REGISTERED then DUPLICATE; fault used once. AT07_1b_chi-tiet.png. |
| 2a | P | SIMULATION, measured on screen, 3 cycles, disconnect right after a poll (worst case): gateway banner 0.1 s; overview “Mất liên lạc với bàn” 6.1–6.4 s; event-log row 6.6–7.0 s; simulated table “contact lost” 8.2–8.5 s (2a-do-tren-man-hinh.txt, AT07_2a_man-hinh_*.png). Green kept, nothing closed. New hold during the outage → unconfirmed at 5.0 s, no request. Defects found and fixed during this test: centre record at 12.1 s (run -01) and an event-log tab that did not refresh. Real USB/RF disconnect BLOCKED. |
| 2b | P | SIMULATION: double press during the outage → “completion sent · waiting for centre” for the whole 10 s, request still open; after reconnect closed once (1 COMPLETED), LED off, history “Hoàn tất”. AT07_2b_*.png. |
| 2c | P | SIMULATION: Accept pressed during the outage → device “Đã bấm nhận · đang chờ trung tâm xác nhận.”, centre stays “Chờ nhân viên nhận” for 10 s; accepted 1.7 s after reconnect; no completion button on the device. Powered-off device → “Chưa tới thiết bị nhân viên” after 8.3 s. AT07_2c_*.png. |
| 3 | P | SIMULATION: after reconnect the same IDs, sequence numbers, registration times and categories (trang-thai-2a-truoc-ngat.json vs trang-thai-sau-noi-lai.json); no table with two requests; table 02 new call got a new ID and sequence #4. Stale-completion replay: automated UT-10 row 3 (PASSED). |
| 4 | P | SIMULATION: “restart node (replace cells)” on table 01 → RECONCILED (node_restart) in the log, original request (same ID, category, time) and green restored; the “reconciling” display lasted under 0.1 s because the link was up. Table 04 called normally meanwhile. Low-battery warning reached the centre. Node removal: UT-10 row 4 (PASSED). Real cell removal BLOCKED. |
| 5a | P | Process force-killed (Stop-Process -Force); restarted: 4 active requests restored identical in ID, sequence, time, state and staff stage (trang-thai-truoc-khi-tat.json vs trang-thai-sau-khi-tat.json); recovery_ms = 73 (khoi-phuc.txt); API ready 1.0 s and manager screen usable 1.1 s after the restart command (operator reaction time not included). “Trung tâm khởi động” in the log. |
| 5b | — | NOT RUN / BLOCKED: no safe mains-loss setup; the PC is a laptop whose battery masks mains loss. |
| 6 | P | CSV exported from the UI (pbl4-events.csv): all 8 types present (dem-loai.txt: REGISTERED 5, ACKNOWLEDGED 1, DISPATCHED 2, ACCEPTED 1, OVERDUE 4, COMPLETED 1, DUPLICATE 1, FAILURE 10); +07:00 times; rows from before the forced restart kept; no guest identifiers. <Mở bằng Excel và chụp màn hình nếu cần.> |
| 7 | P | Controlled-clock fixture (simulated): day 29/30 kept, day 31 pruned, PASSED (buoc-7.txt). Not a month-long run. Configuration restored. |

Reset and overall result: Simulation rehearsal: links and faults restored, staff devices powered on, data-at07 archived (so-sau-cung.sqlite3), demo data untouched. Software-side rows: 10 P (1a at the 5 s boundary), 0 F. Hardware-dependent parts (1a radio ACK, 2a USB/RF, 4 physical node, 5b mains loss) not executed → Overall: BLOCKED pending hardware session.

---

## Chỗ cần sửa trong file hướng dẫn

1. Mục 1.5 và 6.2: nay là **63 passed, 1 skipped**, không còn là 60 hay 61.
2. Mục 5.2: hàm `Mark` ghi vào `evidence\AT07\timeline.txt`, thiếu dấu gạch ngang. Thư mục thật là `evidence\AT-07`, nên viết như cũ sẽ báo lỗi không tìm thấy đường dẫn.
3. Bước 1b: lỗi giả lập giờ chỉ áp cho bàn đang chọn. Phải **chọn Bàn 02 trước**, rồi mới chọn lỗi.
4. Bước 2a: ghi chú "dòng (c) xuất hiện khoảng 10–15 giây" đã cũ; nay khoảng 6–7 giây. Tab Nhật ký sự kiện giờ tự cập nhật, không cần F5.
5. Bước 4: khi gateway đang nối, chữ "Nút vừa khởi động · đang đối soát" chỉ hiện chưa tới 0,1 giây, mắt thường không kịp thấy. Bằng chứng nằm ở dòng `RECONCILED node_restart` trong nhật ký.
6. Mục 4.3: chuỗi ảnh chụp mỗi giây thay được video.
