# BOL Development Journal — September 18, 2026

## Phase 12 — Node Agent Replica Transfer Protocol

Phase 12 advances BOL from replica assignment trust into a controlled Node Agent storage protocol.

Phase 11 established a foundational distinction:

> A replica assignment represents intent. It is not proof that a node possesses the replica.

Phase 12 builds on that boundary by defining how an authenticated destination node receives an assignment, accepts it, stores replica bytes safely, and reports transfer completion back to the BOL control plane.

The architectural rule remains:

> Nodes report observations. BOL derives authoritative state.

A Node Agent may perform storage work and report what it observed, but it does not decide whether a replica is authoritative or verified.

---

## Phase 12A — Authenticated Replica Assignment Delivery

The first Phase 12 milestone established the control-plane-to-agent assignment delivery contract.

Replica assignments are delivered only to the authenticated destination node.

The assignment contract contains the information required for replica transfer, including:

- assignment identity
- physical chunk identity
- replica ordinal
- expected byte size
- expected checksum
- current assignment lifecycle state
- assignment timing information

The protocol intentionally does not provide an arbitrary destination filesystem path.

Filesystem ownership belongs to the Node Agent within its configured BOL storage boundary.

### Trust boundary

Node identity is derived from authentication.

A node cannot request assignments belonging to another node by supplying a different node identifier.

Assignment retrieval is read-only and does not itself advance lifecycle state.

---

## Phase 12B — Authenticated Assignment Acceptance

Phase 12B introduced explicit destination acceptance.

An authenticated Node Agent may accept an assignment addressed to it, allowing BOL to advance the assignment from:

```text
assigned
    ↓
transfer_pending
The Node Agent does not submit a target state.

Instead, it expresses a narrow operation — acceptance — and the BOL control plane determines the legal lifecycle transition.

Expiry protection

Assignment expiry is evaluated using BOL-controlled server time.

Once assignment authority has expired, successful lifecycle advancement is blocked.

This prevents late or replayed Node Agent activity from reviving expired work.

Idempotent acceptance

Repeated acceptance of an already accepted assignment is handled safely.

This supports distributed systems where a request may succeed but the response may be lost or retried.

Phase 12C — Durable Node Agent Replica Storage

Phase 12C established the first dedicated Node Agent replica-storage boundary.

The storage layer is intentionally separated from control-plane lifecycle and trust decisions.

Its responsibilities are filesystem-specific:

derive safe replica locations
keep paths inside the configured storage root
write temporary objects
flush and synchronize data
verify locally stored bytes
atomically promote valid objects
safely handle retries
isolate unexpected finalized content
Node-owned path derivation

Replica paths are derived locally from protocol identifiers.

The control plane does not send arbitrary filesystem paths to the Node Agent.

Path validation prevents traversal and containment escapes, including unsafe path fragments and symlink-based escape attempts.

Partial writes

Replica data is first written as a non-authoritative partial object.

A partial object is never considered a completed replica.

The storage process follows a durability-oriented sequence:

derive safe path
        ↓
write partial object
        ↓
flush
        ↓
fsync
        ↓
read stored bytes
        ↓
measure size + checksum
        ↓
compare with assignment expectations
        ↓
atomic promotion
        ↓
final replica object
Local integrity measurement

Integrity is measured from bytes read back from local storage rather than assumed from the incoming payload.

The storage engine compares:

observed byte size
observed checksum

against the expected properties of the assignment.

Incorrect data is never promoted to the canonical final replica path.

Retry semantics

Replica storage is idempotent.

If the correct final object already exists, a retry recognizes the existing object instead of rewriting it.

If the final path contains unexpected content, BOL does not silently overwrite it.

Corruption quarantine

A fault-injection path was also tested for the narrow case where an object becomes inconsistent after promotion.

Known-bad content is removed from the canonical replica name and preserved separately as non-authoritative forensic material.

This prevents corrupted content from remaining under a name that could be mistaken for a valid replica while retaining evidence useful for investigation.

Phase 12D — Assignment-Bound Storage Authority

Phase 12D connected BOL's authoritative replica assignment state to the Node Agent storage engine.

This created a strict boundary between caller-supplied data and BOL-controlled storage expectations.

The Node Agent may provide:

authenticated identity
assignment identity
candidate replica bytes

The Node Agent does not provide authoritative values for:

destination identity
physical chunk identity
expected size
expected checksum
filesystem path
lifecycle state

Those values are loaded from BOL's authoritative assignment state.

Storage authorization

Only an assignment currently authorized for transfer may initiate storage.

BOL verifies:

authenticated destination
        ↓
assignment exists
        ↓
destination ownership matches
        ↓
state is transfer_pending
        ↓
assignment has not expired
        ↓
authoritative size/checksum loaded
        ↓
durable Node Agent storage

Successful storage does not automatically change the control-plane assignment to transferred.

That separation is deliberate.

Filesystem success is an observation about local storage behavior. Lifecycle authority remains with the control plane.

Phase 12E — Authenticated Transfer Completion

Phase 12E introduced the transfer-completion protocol.

After durable storage, the authenticated destination may submit a completion observation containing:

assignment identity
observed byte size
observed checksum
observation timestamp
agent version

The completion report cannot select destination identity, lifecycle state, verification result, or authoritative replica status.

Completion validation

Before accepting transfer completion, BOL independently checks:

authenticated destination ownership
current assignment lifecycle
assignment expiry using BOL server time
observation timestamp sanity
observed size against the assignment
observed checksum against the assignment

Only after these checks succeed may the authoritative lifecycle advance:

transfer_pending
        ↓
transferred
Server-time authority

Node-reported timestamps are treated as observation metadata.

BOL server time remains authoritative for assignment expiry.

This prevents a node from reviving expired assignment authority by backdating a completion report.

Completion observations are required to carry timezone-aware timestamps, and unreasonable future timestamps are rejected.

Idempotent completion acknowledgement

Transfer completion is retry-safe.

A valid first completion advances the assignment to transferred.

A valid replay of that completion is accepted without changing state again.

Importantly, idempotency does not bypass validation.

A replay from the wrong authenticated node or with incorrect integrity observations is still rejected.

transferred Is Not verified

Phase 12 deliberately preserves a critical trust distinction.

assigned
    ↓
transfer_pending
    ↓
transferred
    ↓
verification_pending
    ↓
verified

transferred means the authenticated destination submitted a completion observation consistent with the BOL assignment contract and BOL accepted the transfer-stage transition.

It does not mean BOL has established verified replica possession.

Verified possession remains a separate evidence-backed control-plane decision.

This separation prevents transport success, persisted metadata, or node assertions from becoming substitutes for independent trust evaluation.

Validation and Failure Testing

Phase 12A–12E was developed with adversarial and rollback-oriented testing.

Validated behaviors include:

authenticated destination isolation
assignment ownership enforcement
expired-assignment rejection
illegal lifecycle rejection
idempotent acceptance
path traversal rejection
storage-root containment
symlink escape rejection
partial-write handling
local size verification
local checksum verification
atomic finalization
stale partial recovery
conflicting final-object protection
zero-byte object handling
post-promotion corruption quarantine
assignment-bound storage expectations
prevention of caller-controlled integrity expectations
server-time expiry enforcement
timezone-aware completion observations
future timestamp sanity checks
completion integrity enforcement
idempotent completion acknowledgement
invalid replay rejection

Testing also verifies that rejected operations do not silently advance authoritative assignment state.

Architecture Principle Reinforced

Phase 12 strengthens one of BOL's central control-plane principles:

Nodes report evidence and observations; BOL derives authoritative state.

The Node Agent is responsible for performing local work and reporting what it observes.

The control plane remains responsible for:

identity
assignment authority
lifecycle transitions
placement eligibility
integrity expectations
evidence evaluation
verified replica state

This separation is intended to make BOL's distributed storage layer safer to reason about as the network evolves beyond a single-host prototype.

Current Milestone

With Phase 12A–12E, BOL now has the core protocol boundaries for:

assignment delivery
        ↓
authenticated acceptance
        ↓
durable destination storage
        ↓
assignment-bound integrity expectations
        ↓
authenticated transfer completion
        ↓
transferred

The next development work connects this transfer lifecycle more deeply with the existing replica evidence and deterministic verification architecture while preserving the distinction between reported completion and verified possession.

BOL — Future of AI Infrastructure

Building toward a consumer-owned distributed infrastructure network for storage, delivery, compute, and future AI workloads.
