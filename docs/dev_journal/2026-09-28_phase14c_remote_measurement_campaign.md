# September 28, 2026 — Phase 14C: Bounded Remote Possession Measurement

BOL completed a bounded, manually authorized three-attempt real remote possession measurement campaign over verified HTTPS. All three challenges produced accepted historical possession results.

For each successful response, the authenticated, database-free Node Agent read a synthetic 1-KiB object through its independent storage boundary. BOL independently measured **1,024 returned bytes**, computed SHA-256 and verified it against the authoritative expectation before accepting the response within the server-issued challenge window.

## Possession truth and measurement quality

The first attempt exposed an export-procedure/configuration defect: the reviewed destination was incompatible with the export persistence guard. Possession verification remained correct. The accepted result was retained, the attempt was not repeated, and its missing measurement export was not reconstructed.

The correction moved future exports to an appropriate private location and added destination preflight checks without weakening the persistence guard or changing possession authority. A fresh deterministic certification run passed all **505 tests**, including **265 PostgreSQL-backed cases**; focused export checks, verifier cases, bootstrap and startup certification also passed.

The next two attempts produced bounded sanitized measurement exports. Both retained partial coverage by design, with zero known dropped records and no detected worker sequence gaps. Successful export persistence does not turn partial measurement coverage into complete instrumentation.

## What we measured

The usable exports captured local operation durations and server chronology for issuance, authenticated polling, protected object read/close, submission and cleanup, hashing, verification and the overall coordinated attempt.

Some intervals overlap and must not be added together. One-way network latency, isolated network-transfer time and isolated decision/commit duration remain unavailable. We do not subtract clocks across machines to infer network delay.

Two usable timing samples are not a latency distribution. This campaign demonstrates repeatable controlled measurement, **not production reliability, capacity or availability**. It does not establish continuous storage or local-disk residency.

## Authority remains unchanged

**Nodes report evidence. BOL derives authoritative state.**

- `proof_lifetime` remains **NULL/unconfigured**.
- Historical possession assurance is established; current qualifying copies remain **zero** and durability remains **unproven**.
- No numeric proof lifetime or freshness policy has been selected.
- No automatic renewal, scheduler, repair or re-replication is enabled.
- Telemetry observes authoritative outcomes; telemetry failure cannot change possession truth or justify another challenge.

The campaign had a finite allowance and required explicit operator authorization for each attempt. It did not automatically advance after a failure or uncertain result.

## Next evidence, before policy

Any further measurement needs separate review and authorization. Useful next conditions include repeated measurements across idle periods, controlled restarts and disconnects, bounded failure cases, and staged larger synthetic objects within existing limits.

Completion latency and possession lifetime remain different questions. Faster responses alone cannot establish how long possession should be trusted.

The broader direction remains storage, verified possession, freshness/durability, automated recovery, vendor-neutral interoperability, CDN, compute and AI infrastructure. These are staged goals, not additional capabilities delivered by this campaign.

[Previous milestone: first real remote possession challenge](2026-09-23_phase14c_real_remote_possession.md) · [Project overview](../../README.md)
