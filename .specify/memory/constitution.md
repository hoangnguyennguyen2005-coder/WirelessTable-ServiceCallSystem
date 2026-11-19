# PBL4 principles
Draft 0.2.0, 2026-11-17; source of truth is the team's ECE411 logbook (33 ERs, C-01..C-09, Step 6 test plan).
1. Concept C, offline venue-PC authority; firmware pins/radio settings are not invented here.
2. Nothing is confirmed to a device before a durable commit; silence never means success.
3. Transport ACK, manager acknowledgement, state shown at the table, dispatch delivery and staff acceptance are distinct facts.
4. Only the manager turns a table green; only the recessed double press at the table completes a request.
5. Request lifecycle and staff dispatch are independent; dispatch never changes the table LED.
6. PROPOSED logbook values stay configurable until user trials and bench tests settle them.
7. Verify software with real checks; never claim unmeasured hardware behaviour. Simulation and hardware data are isolated.
User instructions govern changes; keep docs/traceability.md current.
