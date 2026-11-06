# Wireless Table Call Service — MVP specification
Ngày: 2026-11-06. Nguồn: requirements-source.txt (toàn bộ yêu cầu gốc, có hiệu lực).
Repo ban đầu chỉ README; không có AGENTS.md, logbook, firmware, manifest hoặc test.

## Phạm vi đã chốt
Concept C: Pro Mini 3.3V/≤4MHz/BOD1.8V/2AAA → nRF24L01+ → ESP32-C3 → USB serial → PC offline. Không thay đổi BOM/firmware. Không SaaS, gọi món hoặc thanh toán.

## Journeys và acceptance
- US1/P1 Khách gọi: Given bàn rảnh, When giữ 4.9s rồi thả Then không CALL; giữ 5s Then CALL lưu đúng một request. Retry/restart không đổi received_at. LED đỏ liên tục chỉ sau receipt.
- US2/P1 Điều phối: Given WAITING_ACK, When manager ACK Then ACKNOWLEDGED + outbox cùng transaction; LED chưa được xem là xanh. Poll + STATUS_APPLIED xác nhận đèn. Assign → đúng nhân viên ACCEPT; version/revision cũ bị conflict. Accept không đóng.
- US3/P1 Hoàn tất: Given ACKNOWLEDGED/ASSIGNED/ACCEPTED, When double press tại bàn Then DONE đóng request; receipt mới tắt LED. DONE cũ không đóng CALL mới. WAITING_ACK từ chối DONE và ghi log.
- US4/P2 Vận hành: Given active trên 300s When worker chạy Then nhắc một lần; restart giữ timestamp/dedup/outbox. Có lịch sử, lọc, CSV, cấu hình bàn/nhân viên.
- US5/P2 Tích hợp: Given simulator hoặc serial emulator When cùng sự kiện Then cùng domain; parser chịu lỗi/fragmentation, bounded retry/reconnect. Hardware không có simulator endpoints, DB riêng.

## Functional requirements
FR-001: Một active/table, transaction SQLite + partial unique index, CALL correlation/dedup bền vững.
FR-002: Chuyển trạng thái theo state-machine.md; optimistic version, assignment revision; idempotency cho actions và events.
FR-003: Outbox commit trước gửi, gateway-delivered riêng node-applied, supersede lệnh cũ, TTL/retry/backoff, poll khi active.
FR-004: Reminder >300 giây, một lần, backend worker, UTC persistence/Asia_Ho_Chi_Minh display.
FR-005: Dashboard, panel timeline, staff web prototype không có DONE; SSE reconnect tải snapshot, pending/error/empty/overflow/accessibility.
FR-006: Simulator 24 bàn/2 staff, hold/cancel/double press, active polling, faults/delay/duplicates/disconnect/clock jump riêng demo.
FR-007: Serial NDJSON validated bounded parser, device/staff adapter boundaries, RF frame ≤32B proposal, emulator.
FR-008: History pagination/filter + safe CSV, statistics, table/staff config, health, backup/reset demo.
FR-009: Loopback only MVP, same-origin writes, no secrets/demo selectors in hardware as auth; LAN deliberately unsupported.
FR-010: Automated domain/API/serial/UI lifecycle checks and reproducible README, honest hardware limits.

## Success criteria
SC-001: 24 bàn/2 staff từ seed demo, lifecycle end-to-end có persistence, reload/restart giữ active.
SC-002: Các case bắt buộc 1–16 trong nguồn có evidence/limit rõ trong verification.md.
SC-003: Desktop 1366×768/mobile390 usable, không có success giả hoặc telemetry bịa.
SC-004: Build local phục vụ UI/API không cần Internet sau khi cài dependency.

Entities: tables, staff, requests, assignments, observations, events, processed events, commands, action keys. Chi tiết schema: backend/app/db/store.py; API: /openapi.json.
Assumptions/exclusions: assumptions.md. Hardware measurements excluded from software acceptance.
