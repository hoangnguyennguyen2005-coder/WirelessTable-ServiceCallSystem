# Architecture / implementation contract
## First principles và trade-off
Mục tiêu: yêu cầu phục vụ bền vững tại quán; RF/USB ACK không chứng minh nghiệp vụ hoặc LED.
| Phương án PC | Ưu | Đổi lại |
|---|---|---|
| FastAPI + SQLite + SSE (chọn) | Ít dịch vụ, transaction/outbox, offline | Một process worker, phù hợp MVP |
| Node + SQLite | Một ngôn ngữ | Khác mặc định yêu cầu, không lợi ích đủ lớn |
| Broker + DB server | Phân tán | Vượt phạm vi, tăng lỗi vận hành |
Không xem xét lại Concept C.

## Pre-mortem
1. Duplicate/reboot đóng nhầm: persistent (node,boot,token) map; event fingerprint; DONE đúng request; unique active index.
2. ACK queued sau DONE: supersede mọi status cũ khi complete; node phải so revision/correlation. Receipt DONE retry tái tạo command.
3. Disconnect/2 browsers: outbox persisted, TTL/bounded retry; optimistic version, SSE snapshot reconnect. SQLite backup API nhất quán.

## Contract
DB BEGIN IMMEDIATE, WAL, foreign keys. Domain không import serial/UI. State/event/outbox cùng commit. IDs UUID, node 1..65535, boot/token uint32, event_id bounded string. Pydantic forbid extra. event types CALL/STATUS_POLL/DONE/STATUS_APPLIED/DEVICE_STATUS/COMMAND_ACK. Fields protocol_version=1,message_type,event_id,node_id,boot_id,call_token,request_id?,command_id?,payload. Correlation map không tái sử dụng. Unknown nodes reject/log.
API GET /api/snapshot, /api/requests/{id}, /api/history, /api/export.csv, /api/health; POST request/{id}/ack|assign|accept with expected_version,idempotency_key,staff_id/revision when required; POST config tables/staff; GET /api/events SSE snapshot signals; simulation-only /api/sim/*; all errors {detail}, 409 conflicts, 422 invalid, 403 forbidden.
StaffDeviceAdapter accepts assignment+staff+revision; web prototype goes through same boundary. Hardware staff token environment with bound staff identity; manager routes loopback only. No LAN until auth added.
Outbox: pending → gateway_received → applied; failed/superseded/expired separately. Only node contact releases table commands; receipts may push while contact just received. COMMAND_ACK records USB only. STATUS_APPLIED validates latest desired correlation+revision+LED. Staff prototype delivery is browser snapshot observation, not acceptance.

## Exact implementation steps (≤3 files per step)
1. docs/requirements-source.txt,spec.md,assumptions.md: supplied requirements + US/FR/SC.
2. docs/architecture.md,state-machine.md,tasks.md: contract + traceability.
3. .specify/feature.json,memory/constitution.md,docs/checklists/requirements.md: metadata/quality.
4. .gitignore,backend/requirements.txt,backend/app/db/store.py: schema/runtime.
5. backend/app/domain/models.py,service.py: transitions/outbox.
6. backend/app/adapters/serial_gateway.py,simulator.py,staff.py: boundaries/faults.
7. backend/app/config.py,main.py: HTTP/SSE/worker/static serving.
8. backend/tests/test_domain.py,test_adapters.py,test_api.py: verify critical behavior.
9. frontend/package.json,tsconfig.json,vite.config.ts: tooling. Lockfile generated install.
10. frontend/index.html,src/api.ts,src/main.tsx: transport/types + React entry.
11. frontend/src/App.tsx,styles.css: manager/staff/simulator UI.
12. tools/serial_emulator.py,demo.py,backup.py: run/serial/backup.
13. docs/protocol.md,hardware-integration.md,verification.md: evidence/protocol.
14. README.md,.env.example,frontend/tests/e2e.spec.ts: reproduce/check.
Later fixes in bounded batches ≤3 files.

## UI pillars
Café/laptop fast scanning; touch targets≥40px; keyboard focus. 60% neutral warm white, 30% structured slate borders/panels,10% semantic red/green/amber. Typography 28/20/16/12px, spacing4/8px. Side nav, utility header, four counters, 6-column table grid + queue, side panel, history table; staff single column390px. Text with every status, overdue separate badge, LED applied separately. No ornamental charts, gradients or fake metrics.

## Verification
pytest fake clock/temp DB/fake serial, frontend tsc/eslint/build, Playwright desktop/mobile E2E. No hardware claims. Data model lives in versioned SQL; protocol.md is interface contract; README is quickstart; no separate research.md needed (stack prescribed). Constitution check: Concept C/offline/persistence/no web DONE all retained before/after design.

## Dependency choices (authorized by supplied MVP request)
Runtime: FastAPI/Pydantic/uvicorn, stdlib sqlite3, pyserial; React/react-dom and Zod for validating API responses as unknown data. Build/check only: Vite/react plugin, TypeScript, ESLint/typescript-eslint, Playwright, Prettier; pytest/httpx/Ruff for Python. Versions pinned through requirements.lock and package-lock.json. No CSS/UI framework, broker, external font/CDN, cloud persistence or system service added.

Final implementation keeps the prescribed offline/Concept C workflow. UI table grid adapts to available width (4 columns at1366,6 on larger screens,2 narrow); reading labels takes precedence over fitting all24 tables into one viewport. Device commands release only on CALL/DONE/POLL contact; COMMAND_ACK is not treated as RF node contact. Pending same-revision command reused to retain retry counter; state changes supersede stale desired commands.
