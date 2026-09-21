# Phase 14 — Authoritative Durability & Renewable Possession Assurance

Phase 14 strengthens how BOL distinguishes intended redundancy from copies it can actually substantiate. The governing principle remains:

> Nodes report evidence; BOL derives authoritative state.

AI may advise, but it does not mutate authoritative BOL state.

## A reproducible control-plane foundation

The first milestone reconciled control-plane source assumptions with a canonical schema and established an ordered database bootstrap. An empty database can now be constructed reproducibly, with migration bookkeeping recording actual execution. Runtime startup verifies the required schema and fails closed when it is incomplete; it no longer creates or silently repairs schema.

This separates deployment preparation from application behavior and makes repeatable certification possible. Compatibility structures still needed by existing consumers remain explicit technical debt rather than implicit authority.

## Desired durability and provable durability

Durability assessment separates the number of copies required by policy from the qualifying copies supported by authoritative evidence. A legacy replica status, a placement record or primary metadata alone is not proof that bytes are possessed.

Assessment respects the distinction between a logical chunk, a physical realization and a copy associated with a node. Multiple records on one node do not establish independent copies. Conclusions explain the policy, counted copies, exclusions and proof deficits. Insufficient proof does not by itself establish that data has been lost.

Durability assessment remains read-only. It can identify an advisory need for repair; it does not move bytes, create assignments or authorize deletion of surplus copies.

## Renewable possession assurance

BOL can issue authenticated, server-controlled, single-use read-back challenges for enrolled physical copies. It measures returned byte count and computes SHA-256 itself rather than accepting a node's checksum claim as proof. Returned contents are handled as a bounded stream and are excluded from logs, audit records and result payloads.

Copy identity is independent of its primary or replica role. Enrollment establishes identity and authority, not possession. Primary and replica copies use equivalent proof semantics: neither receives a metadata-only shortcut.

The proof claim is deliberately limited: a successful challenge establishes that the authenticated endpoint supplied the expected bytes within a bounded challenge window. It does not prove local-disk residency, continuous storage, independent hardware, operator or geography, or that the endpoint could not retrieve bytes elsewhere.

## History, contradictions and reconciliation

Observations and decisions preserve an immutable history. Retransmission cannot turn an old success into new proof, and conflicting observations cannot silently overwrite earlier facts. Contradictions establish an explicit reconciliation boundary; earlier proof cannot erase them. Resolution requires qualifying subsequent challenge evidence.

Credential authority is established before a response can create assurance consequences. Credential rotation is not treated as physical-copy disappearance. Authentication eligibility and possession history remain separate concerns.

## Transaction and storage boundaries

Atomic service operations now own their database transactions explicitly. Participating helpers cannot prematurely commit another operation's work.

Database authority and active filesystem access have different lifetimes. Storage protections now remain in place through protected I/O completion, including cancellation and session-loss cases. Enrolled physical objects cannot bypass the assurance model through legacy byte mutation or standalone legacy integrity verification. Historical integrity records remain audit history rather than becoming possession evidence automatically.

These changes were certified using actual database transactions, processes and filesystem operations, alongside deterministic regression tests. The focus was on preserving authority under interruption and concurrency without adding filesystem rollback or distributed locking.

## Certification and current limits

The completed checkpoint passed 226 tests, including 126 PostgreSQL integration tests, and compilation of 87 Python modules. Certification covered independent empty-database builds, migration replay and upgrade, startup verification, trust boundaries, adversarial responses, reconciliation, credential behavior, concurrency, cancellation and privacy checks.

Possession-proof freshness policy remains unconfigured. Successful challenges are historical proof and currently contribute zero sufficiently fresh qualifying copies to durability assessment. They are not treated as indefinitely valid assurance.

Automated renewal scheduling remains under development. This milestone introduces no automatic repair, re-replication, surplus deletion or authoritative file-level durability. It makes no broader failure-domain or advanced cryptographic proof-of-storage claims.

## Next: measurement before freshness policy

The next starting point is **Phase 14C — Possession Renewal Measurement & Freshness Policy**. Work must begin with measurement and capacity analysis: scheduling and delivery delays, read and transfer duration, verification time, failures, timeouts and object-size distribution.

Those measurements will inform an explicitly reviewed renewal interval and maximum uncertainty bound. No arbitrary proof lifetime has been selected. The next phase has not started.
