# Transition table
All accepted changes+log+outbox atomic. Backend timestamp, correlation required for device events. Manager actions expected_version; action key bound to payload. Assignment revision monotonic.
| Before | Event | Guard | After | Saved | Device command | Rejection |
|---|---|---|---|---|---|---|
| idle | CALL | enabled known node,new boot/token | WAITING_ACK | received_at/version1+correlation | CALL_RECEIPT RED | unknown/disabled |
| any active | CALL | same table | unchanged | map additional retry token | CALL_RECEIPT current status | token reuse mismatch |
| WAITING_ACK | ACK | version matches | ACKNOWLEDGED | acknowledged_at/version+1 | SET_REQUEST_STATUS GREEN | stale version |
| ACKNOWLEDGED/ASSIGNED/ACCEPTED | ACK repeat | semantic idempotent | unchanged | log | unchanged | wrong request |
| ACKNOWLEDGED/ASSIGNED/ACCEPTED | ASSIGN | available staff,version matches,explicit reassign accepted | ASSIGNED | revoke old,revision+1,version+1 | staff assignment via adapter | stale/unavailable/no confirmation |
| ASSIGNED | ACCEPT | assigned staff+revision+version | ACCEPTED | accepted_at/history/version+1 | none | wrong owner/revision |
| ACCEPTED | ACCEPT repeat | same owner/revision | unchanged | log | none | stale assignment |
| ACKNOWLEDGED/ASSIGNED/ACCEPTED | DONE | boot/token maps exact request | COMPLETED | completed_at/closed_from/version+1 | supersede old; DONE_RECEIPT OFF | unknown/stale correlation |
| COMPLETED | DONE retry | same exact correlation | unchanged | log/dedup | resend DONE_RECEIPT OFF | never touch new request |
| WAITING_ACK/idle | DONE | never valid | unchanged | rejection log | ERROR | done_before_ack/no_request |
| active | timer | now-received_at>300,reminded_at NULL | unchanged | reminded_at/event once | none | completed/exact300 excluded |
| active | STATUS_POLL | same correlation | unchanged | last_seen,contact | current desired revision/status | mismatch |
| any | COMMAND_ACK | command_id+node match | unchanged | gateway_received only | none | unknown command |
| any | STATUS_APPLIED | latest request version+LED+correlation | unchanged | observed LED/applied revision | none | stale revision/status |
No RF transport ACK mutates lifecycle. Device observations and overdue never replace business state. Complete stores closed_from for audit.
