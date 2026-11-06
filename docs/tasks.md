# MVP tasks — execution 2026-11-06
Sequential implementation authorized by supplied request; artifacts docs/ per explicit destination. Check only with evidence in verification.md.
## A — specification
- [x] T001 Inspect repo and preserve source request in docs/requirements-source.txt; no logbook exists.
- [x] T002 Specify US1–US5/FR001–010 in docs/spec.md, architecture.md,state-machine.md,assumptions.md; cross-check against source.
## B — domain (depends A)
- [x] T003 [US1] backend/app/db/store.py schema/version/index/seed; FR001/004/008, restart+concurrency checks.
- [x] T004 [US1–3] backend/app/domain/models.py,service.py lifecycle/idempotency/outbox; FR001–004, transition tests.
- [x] T005 [US1–5] backend/app/main.py,config.py API/SSE/security/worker; FR005/009, API checks.
## C — UI (depends B)
- [x] T006 [US2] frontend/src/App.tsx,api.ts,styles.css manager/staff/pending/reconnect; FR005, desktop/mobile checks.
## D — transports (depends B,C)
- [x] T007 [US1,3,5] backend/app/adapters/simulator.py,serial_gateway.py,staff.py polling/hold/double press/retries; FR003/006/007, adapter tests.
- [x] T008 [US5] tools/serial_emulator.py,docs/protocol.md,hardware-integration.md; FR007, PTY/emulator checks.
## E — completion (depends B–D)
- [x] T009 [US4] History/config/CSV/stats + tools/backup.py; FR008, API/export checks.
- [x] T010 [US1–5] backend/tests/*,frontend/tests/e2e.spec.ts; FR010/SC001–004 test/typecheck/lint/build.
- [x] T011 README.md,tools/demo.py,.env.example,docs/verification.md run/demo/limits; SC001–004.
- [x] T012 Convergence compare all source requirements against actual code, append remediations if needed.

Execution evidence 2026-11-06: docs/verification.md. T003–T011 implementation pass executed over this task set; pytest20, Chromium E2E3, typecheck/lint/format/build passed. Hardware checks explicitly excluded from PC software completion and listed in docs/hardware-integration.md.

Convergence review (read-only) completed 2026-11-06 against current sources, source requirements and verification evidence: no additional software remediation task identified. Returned to implementation bookkeeping to record T012 completion. All firmware/physical measurements remain handover validation items, not claimed passed.
