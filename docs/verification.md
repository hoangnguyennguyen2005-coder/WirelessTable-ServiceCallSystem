# Verification — software MVP
Execution date: 2026-11-06. Checkout: /workspace/PBL4, branch work. No push/deploy/merge. Source requirements: requirements-source.txt. All evidence below is software-only.

## Commands actually run
| Command (repository root) | Result |
|---|---|
| `python -m venv .venv` + `.venv/bin/pip install -r backend/requirements.txt` | Installed in project venv, lock captured in backend/requirements.lock |
| `npm install --prefix frontend` + pinned Zod/Prettier additions; final `npm --prefix frontend ci` | Installed; lockfile clean install succeeded (192 packages) |
| `.venv/bin/python -m pytest -q` | 20 passed; includes real pyserial↔PTY↔shipped emulator subprocess and backup/restore |
| `.venv/bin/python -m ruff check backend tools` | All checks passed |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `git diff --check` | Passed for tracked changes |
| `npm --prefix frontend run typecheck` | Passed strict TypeScript, noEmit |
| `npm --prefix frontend run lint` | Passed ESLint |
| `npm --prefix frontend run format:check` | Passed Prettier source check |
| `npm --prefix frontend run build` | Passed; Vite production assets served by FastAPI |
| `npm --prefix frontend run test:e2e` | 3 passed in Chromium; launches built app with tools/demo.py and separate temp DB |

Python3.12.14, Node24.22.1/npm11.9.0 observed directly. Initial E2E failed due ambiguous accessible-name selectors (icons hidden from AT; header/cell duplicate); selectors corrected, full suite subsequently passed. Initial emulator test exposed stdin read-ahead/select stall; fixed with os.read/line buffering, PTY test then passed. These failures were not counted as successful checks.

Non-blocking warnings: Starlette TestClient's anyio BlockingPortal alias deprecated; Playwright child process FORCE_COLOR/NO_COLOR warning. No application traceback/pageerror in successful lifecycle E2E. npm reported ESLint9 version support deprecation at install; pinned tool still executes checks. Windows commands documented but not executed on Windows.

## Mandatory acceptance mapping (source §15)
| # | Evidence |
|---|---|
|1|test_hold_cancel_exact5_and_idle_no_polls: fake clock4.9 cancel,exact5 one CALL; browser keyboard hold/cancel and actual5.2s hold|
|2|test_call_retry_restart_and_concurrent: persisted same request/received_at after Store restart|
|3|Same test races8 distinct CALL tokens on initially idle node2, one resulting active request; transaction+partial unique index|
|4|test_ack_outbox_applied_and_no_transport_ack_business: ACK creates desired command, LED not falsely applied|
|5|Same test: USB COMMAND_ACK keeps WAITING_ACK; poll GREEN and STATUS_APPLIED; simulator test observes green|
|6|test_assign_accept_reassign_conflicts; test_old_accept_idempotency_key_rejected_after_reassign; wrong staff/revision refused|
|7|Accept remains ACCEPTED/no completed_at; API `/done` absent and E2E staff has no completion button|
|8|Parameterized DONE from ACKNOWLEDGED/ASSIGNED/ACCEPTED, repeat idempotent; lost receipt test LED stays green then OFF on retry|
|9|Old DONE after new CALL maps old UUID and cannot close new request; stale GREEN applied rejected|
|10|test_reminder_strict_threshold_restart_once_no_reset: exact300 excluded,300.01 once; completed excluded; browser demo advance301|
|11|Store/service restart preserves active/correlations/dedup/outbox/reminded_at; simulator rehydration; backup restores exact request/processed/outbox|
|12|FrameParser fragmentation/multiple lines/malformed/invalid UTF8/oversize; fake transport disconnect/reconnect; shipped emulator malformed+oversize+fragmented CALL over real PTY|
|13|Browser SSE disconnect/reconnect reloads snapshot; subscription count stays bounded and stable after recovery|
|14|DONE supersedes pending green; test_lost_call_and_done_receipt_duplicate_reconnect; disabled completed table still accepts DONE retry|
|15|Domain/API/local built assets make no external service calls. Lifecycle runs entirely loopback; no external network endpoint is needed. Idle simulator nodes have no polls; UI says sleeping/unknown. Internet outage is established by local dependency-free architecture, not a physical quán network outage test. Browser offline test temporarily loses local connection and recovers.|
|16|test_hardware_no_sim_isolation_and_staff_identity: same data dir uses distinct DB files; hardware starts empty, sim endpoints404, staff token bound ID|

## Additional verification
- Full browser CALL→ACK→ASSIGN→ACCEPT→DONE, history complete, desktop1366×768 and mobile390×844 with no horizontal overflow.
- Browser third test injects staff inbox503, retries via UI, receives assigned work successfully.
- CSV formula injection escaped, history filters, wrong Origin403, invalid Host403, explicit demo reset confirmation422/200.
- `test_shipped_emulator_real_pty`: actual OS PTY and pyserial, no RF hardware. CALL receipt→manager ACK→poll→applied GREEN→DONE→applied OFF.
- `test_online_backup_restore_roundtrip`: online SQLite backup API and restore into separate temp directory; exact request/outbox/dedup preserved.
- Screenshots generated by successful E2E: screenshots/dashboard.png, screenshots/staff.png; manually viewed for layout/readability. Browser UI snapshots show persisted backend data, not static arrays.

## Scope/risks left for handover
- No Pro Mini, nRF24L01+, ESP32-C3 or physical staff device connected. No firmware compatibility, RF range/latency/delivery-success/current/battery-life claims. See hardware-integration.md for physical checks.
- RF28byte frame, baud/poll/double-press are proposed integration defaults; pinout/radio configuration remains firmware owner's task.
- Loopback only; LAN intentionally denied until authentication/session design exists. Hardware staff web prototype uses token+bound staffID; simulation selector is labelled demo.
- One backend worker owns serial/simulation. SQLite prototype is not a multi-process service architecture.
- Simulator rehydrates active requests on PC restart; node-emulator state is software. Physical node persistence across power loss must be validated with firmware as protocol.md specifies.

## Final reconciliation
FR001–004 covered by Store/Service/domain tests; FR005 by App/api hook/browser tests; FR006 by Simulator/browser and fake clock tests; FR007 by SerialGateway/FrameParser/PTY emulator/protocol; FR008 by history/config/export/backup tests; FR009 by local boundary and hardware identity tests; FR010 by the executed commands above. SC001–004 have software evidence; hardware measurements remain explicitly outside acceptance of PC software. No implementation TODO was used as a substitute for an in-scope function.
