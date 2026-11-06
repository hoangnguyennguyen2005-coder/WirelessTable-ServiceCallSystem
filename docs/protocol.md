# Protocol v1 — proposed firmware integration contract
**PC adapter implemented; RF/firmware proposal, not hardware-verified.** Concept C only. RF transport ACK ≠ database commit ≠ manager ACK ≠ applied LED.

## USB PC ↔ ESP32-C3
115200 baud,8N1 proposed default; PBL_SERIAL_PORT/PBL_SERIAL_BAUD configurable. UTF-8 newline-delimited JSON; max4096 bytes before LF, buffer bounded. Fragmented/multiple frames supported; invalid UTF8/JSON/schema/type/length discarded, parser error counter/log increments. Oversize line discarded through LF, next good frame recovers. Node disabled/unknown rejected. No raw secret logging. Reconnect1→2→4→8→16s; one worker process.

Events validated by backend/app/domain/models.py, generated OpenAPI for HTTP equivalent:
```json
{"protocol_version":1,"message_type":"CALL","event_id":"1.123.7.1.CALL","node_id":1,"boot_id":123,"call_token":7,"request_id":null,"command_id":null,"payload":{}}
```
Required core: protocol_version1,message_type,event_id(1..100 safe chars),node_id1..65535,boot_id/call_token uint32. request_id UUID string (optional on first CALL); command_id for COMMAND_ACK. payload only led OFF/RED/GREEN,revision positive integer,battery_mv0..10000 as applicable. Unknown fields rejected. Device timestamps never authoritative.

Types:
- CALL: stable call_token for the whole physical call/retries; gateway assigns deterministic event_id from node+boot+token+sequence+type. Received valid CALL maps session to backend UUID. Duplicate active CALL returns same request without resetting received_at.
- STATUS_POLL: while active only. Uses same correlation; releases current desired status. No heartbeat for sleeping idle tables.
- DONE: same session/token, optionally backend UUID; allowed ACKNOWLEDGED/ASSIGNED/ACCEPTED. COMPLETED duplicate regenerates DONE_RECEIPT. Unknown correlation/WAITING_ACK rejected/logged. Never lookup DONE by table alone.
- STATUS_APPLIED: payload led+revision must equal current desired state for that exact request. Only this proves LED applied (not an RF measurement). Stale status rejected.
- DEVICE_STATUS: optional battery_mv observation; cannot prove applied LED.
- COMMAND_ACK: command_id+node; USB gateway received only, never manager ACK or completion.

Commands contain protocol_version,message_type,command_id(UUID),node_id,request_id(UUID),boot_id,call_token,payload{led,revision}. Types CALL_RECEIPT,SET_REQUEST_STATUS,DONE_RECEIPT. ERROR is direct negative response {protocol_version:1,message_type:ERROR,event_id,node_id,payload:{reason}}. Invalid unparseable lines cannot be correlated so only counted/logged.
- DB commit finishes before CALL_RECEIPT/DONE_RECEIPT transport write.
- Outbox stores desired state; pending→gateway_received→applied. failed(max5),expired(120s),superseded retained for audit. Attempts backoff1,2,4,8,16s, at most4 frames/contact. Radio release only when node contacts gateway, not background blasts to sleepers.
- Poll may supersede old desired-state command with current revision; completed supersedes pending green commands. Node rejects lower revision or foreign correlation. Retries after expiry/current poll regenerate current command, never stale desired state.
- Gateway retains short contact opportunity to reply; if unavailable, node retries CALL/DONE or polls. USB delivery counter alone never marks node applied.
- PC reconnect reloads outbox from SQLite; node retries reconcile. Lost DONE_RECEIPT handled by DONE retry after request already closed, including after PC restart.

## Full transcript (IDs abbreviated for readability)
1. Node holds5s; gateway → CALL event E1 boot123/token7, no request_id. RF ACK alone has no effect.
2. PC transaction inserts R1 WAITING_ACK, correlation(1,123,7),event,outbox C1 then commits. PC → CALL_RECEIPT C1 R1 RED/rev1. Gateway may COMMAND_ACK C1; node applies RED then STATUS_APPLIED R1 RED/rev1.
3. If C1 lost: node repeats E1 with identical fields; PC returns R1 and a receipt; no second request/time reset. If event_id reused with different payload reject collision.
4. Manager POST ack expected_version1,keyK1: transaction R1 ACKNOWLEDGED/rev2 + GREEN outbox. UI: manager confirmed, waiting for table.
5. Active node → STATUS_POLL boot123/token7,R1. PC → SET_REQUEST_STATUS C2 GREEN/rev2. Node applies and emits STATUS_APPLIED GREEN/rev2; only now UI has applied evidence.
6. Manager assign staff1 expected_version2 → ASSIGNED/version3,assignment_revision1. StaffDeviceAdapter inbox marks prototype delivery separately. Correct staff accept(version3,revision1) → ACCEPTED/version4; LED remains green. Wrong staff/revision conflict.
7. Two hidden presses: node → DONE E9 boot123/token7,R1. PC commits COMPLETED/version5,closed_from ACCEPTED,supersedes green; PC → DONE_RECEIPT C9 OFF/rev5. Node turns OFF/sleeps after receipt and may confirm applied.
8. If receipt lost, node keeps green and retries E9; PC resends OFF receipt, does not close anything again. New CALL(token8) creates R2; late E9 still maps R1 and can never close R2. Node on token8 must ignore all token7 commands.
9. Malformed line then reconnect: parser discards through LF; valid E9 after reconnect recovers via persistent correlation/dedup/outbox.

## RF gateway ↔ Pro Mini: 28-byte proposal
Not the USB JSON string: nRF24L01+ maximum payload32bytes. All multi-byte integers little-endian. Node id/config/pins/channel/address/speed/CRC radio settings require firmware owner approval; none invented here.
| Offset | Bytes | Type | Meaning |
|---|---:|---|---|
|0|1|u8|protocol version1|
|1|1|u8|kind:1CALL,2POLL,3DONE,4APPLIED,5STATUS,16CALL_RECEIPT,17SET_STATUS,18DONE_RECEIPT,255ERROR|
|2|2|u16|node_id|
|4|4|u32|boot/session id persisted, non-reused|
|8|4|u32|call_token stable through CALL→DONE retries|
|12|2|u16|event sequence; retry identical event keeps sequence|
|14|4|u32|backend request version;0 before first receipt|
|18|1|u8|LED0OFF/1RED/2GREEN; not business ACK|
|19|1|u8|flags:bit0 battery valid;other bits0|
|20|2|u16|battery_mV when valid,else0|
|22|4|u32|gateway command tag,0 for unsolicited event|
|26|2|u16|proposed app CRC16-CCITT-FALSE of bytes0..25 (poly0x1021/init0xffff); verify with firmware|
Total28 ≤32. CRC proposal is additional to radio hardware CRC, not a measured requirement.

Mapping: gateway maintains tag↔command_id and (node,boot,token)↔request UUID from PC receipt. Table node never needs UUID on RF. If gateway restarts, tuple on next POLL resolves at backend even without request_id; command creates fresh tag map. Backend event_id derived tuple+sequence+kind; gateway must not include unstable transport metadata in retry. COMMAND_ACK carries UUID on USB, separate from RF event sequence. Sequence uint16 must not wrap within same call: firmware renews session safely before exhaustion, never reuses tuple. Version32 wrap must be prevented by maintenance rather than truncation. Persistent boot/token allocation and wear/power-loss strategy still require firmware validation. If node loses correlation mid-call, it must seek reconciliation/operator recovery; never issue DONE with invented current correlation.

## Staff boundary
PrototypeStaffAdapter implements StaffDeviceAdapter.inbox/accept; assignment delivery timestamp distinct from human acceptance. Hardware endpoint requires X-Staff-Token mapped server-side to PBL_STAFF_ID; simulation selector has no security claim. Future physical adapter must present verified staff identity and current assignment revision to same service. No complete action exists in staff protocol.
