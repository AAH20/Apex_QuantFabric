# Frozen signal-to-reservation contract, version 0.1

The profile JSON is the normative bounds/identity record. This prose freezes semantic precedence. Changes require a new version and new qualification; Tick's existing profile is not modified.

## Interchange and time

Every JSONL event has exactly the fourteen fields named in the profile. Integers are actual JSON integers (not booleans/floats), bounded to 0..2,147,483,647. Session is positive, instrument is 0..7, prediction ID is 1..256 and quantity is 1..16. Unused fields are zero. MARKET has a positive sequence and integral positive price in `score`. PREDICTION may use string `nan`, `inf` or `-inf` solely to exercise explicit rejection; nonstandard JSON constants are rejected.

The adapter validates JSONL and writes fourteen TSV fields for the native parser. The native parser independently checks bounds and unused fields. Malformed input or regressed time exits nonzero and is inconclusive, not a successfully rejected financial request. Every well-formed event produces exactly one trace row. A physical transport would need a separately qualified framing/error contract.

Logical arrival time is nondecreasing. Prediction completion order may differ from prediction identity and source sequence. The Python completion queue has at most eight entries; overflow returns a DROPPED event, and delayed completion receives the actual logical drain time. This is a logical test adapter, not an asynchronous wall-clock scheduling guarantee.

## State and event precedence

Initial session is 1. Each instrument has current contiguous sequence, price and a feed-blocked flag. A 256-bit per-session identity bitmap includes accepted and rejected well-formed prediction deliveries. Sixteen reservation slots contain prediction identity, instrument, quantity and uncertainty. Admission is a single serialized transition, not a distributed or concurrent atomicity proof.

1. RESET requires a strictly newer session and no live reservations. It clears instrument state, blocked flags and seen identities. It cannot erase outstanding exposure. Logical time is not reset.
2. All other wrong-session events are rejected without changing authoritative state.
3. ADVANCE changes no financial state.
4. MARKET requires the next contiguous sequence. Duplicate/old messages leave state unchanged. A forward gap freezes that instrument until an allowed reset; a later missing message does not silently heal it.
5. UNCERTAIN retains a known reservation and sets its uncertainty flag. RELEASE removes a known reservation. Unknown/duplicate terminal messages do not change state. RELEASE represents a confirmed synthetic terminal outcome, not a cancel request or partial fill.
6. PREDICTION and DROPPED check the identity bitmap before other prediction rules. First delivery consumes identity even if rejected. A DROPPED result then records QUEUE_DROPPED without a reservation.
7. A prediction checks frozen model/policy/configuration, feed-blocked flag, exact nonzero watermark, expiry (`time <= expiry`), finite numerical score within absolute `1e-6` of the toy predictor, then the decision threshold.
8. A valid score below 0.5 is NO_SIGNAL. An actionable score must fit sixteen units for its instrument and an available global slot. A successful action identity is `(session, prediction_id)`; the emitted action column stores the ID alongside the session column.

The trace contains authoritative session, all eight watermarks/prices, blocked mask, seen bitmap and canonical sorted live reservations after every event. Full-state equality and exact decisions are required even when score values are numerically close. The permitted candidate score tolerance does not permit a different threshold decision.

## Accounting and limitations

Valid signals include numerically acceptable, fresh NO_SIGNAL and capacity-rejected signals. Admitted actions are a distinct denominator. Duplicate deliveries, wrong-session deliveries, model errors, missing results represented by DROPPED, and final live obligations remain visible. Terminal release and actual trading fills are not interchangeable.

This profile excludes production protocol decoding, partial fill/cancel/replace, distributed fencing, durable recovery, hardware offload, live market access and strategy profitability. Deliberately faulty native variants exist only to challenge the checker. They must never be used for operational execution.
