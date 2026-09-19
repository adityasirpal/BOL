# BOL Development Journal — September 19, 2026

## Phase 12F — Replica Possession Evidence and Verification

Phase 12F completes the trust path that follows authenticated replica transfer.

Earlier Phase 12 work established how a destination node receives an assignment, accepts it, stores replica bytes durably, and reports transfer completion.

Phase 12F addresses the next question:

> How does BOL move from a completed transfer to an independently verified replica state without allowing the node to declare its own success?

The architectural rule remains:

> Nodes report evidence. BOL derives authoritative state.

---

## Possession Evidence

A transferred replica is not automatically treated as verified possession.

After transfer completion, the authenticated destination node may submit a possession observation containing:

- assignment identity
- observed byte size
- observed checksum
- observation timestamp
- agent version

The Node Agent cannot submit:

- reporting node identity independently
- destination identity
- assignment lifecycle state
- target state
- verification result
- verified status
- filesystem path

Node identity is derived from authentication.

Evidence remains an observation until BOL evaluates it.

---

## Evidence to Verification Boundary

Phase 12F introduced an orchestration boundary connecting replica evidence to the verification lifecycle.

The lifecycle advances from transferred to verification_pending only after authenticated destination evidence has been recorded.

Evidence recording remains separate from lifecycle mutation.

This preserves a clean distinction between recording evidence, verifying evidence, and changing authoritative assignment state.

---

## Transaction Isolation and Savepoints

Failure testing exposed an important transaction-boundary requirement.

A composed operation using commit=False must not roll back unrelated work owned by its caller.

Phase 12F therefore introduced savepoint-based transaction isolation for the evidence-to-verification bridge.

The bridge creates a local savepoint before recording evidence and requesting the verification_pending transition.

If both operations succeed, the savepoint is released.

If the lifecycle transition fails, only work performed after that savepoint is rolled back.

This allows the bridge to undo its own partial work while preserving the caller's surrounding transaction.

The behavior was explicitly tested, including preservation of earlier caller-owned transaction work.

---

## Deterministic Evidence Verification

Evidence verification remains BOL-controlled.

The verifier evaluates authoritative assignment expectations against reported observations.

Verification checks include:

- reporting node matches the assigned destination
- observed size matches the expected size
- observed checksum matches the expected checksum

A valid observation becomes verified evidence.

An invalid observation becomes rejected evidence.

Rejected evidence is preserved for audit and analysis rather than discarded.

---

## Rejected Evidence Does Not Advance Assignment State

Rejected evidence does not authorize assignment verification.

The assignment remains in verification_pending so that additional observations may be evaluated later.

This distinction preserves an important rule:

Evidence correctness and assignment lifecycle state are related, but they are not the same thing.

---

## Multiple-Evidence Recovery

The architecture intentionally permits multiple evidence records for an assignment.

Phase 12F validated a sequence where an initial observation is rejected and a later observation is correct.

The first rejection remains preserved.

The later valid observation can be independently verified and may satisfy the requirement for the assignment to advance.

This supports both auditability and future repeated possession checks.

---

## Verified Finalization

Evidence verification and assignment lifecycle mutation remain separate responsibilities.

When destination evidence becomes verified, BOL may request the legal transition from verification_pending to verified.

ReplicaAssignmentStateManager remains the authoritative assignment lifecycle boundary.

The verifier itself does not directly write assignment state.

---

## Atomic Verified Finalization

Verified evidence and assignment finalization are coordinated transactionally.

If evidence becomes verified but the assignment transition unexpectedly fails, the evidence change is rolled back to the operation savepoint.

This prevents the orchestration path from leaving a partially finalized trust state.

---

## Idempotent Finalization

Successful evidence verification and assignment finalization are replay-safe.

A repeated finalization operation against already-verified evidence and an already-verified assignment succeeds without mutating either record again.

---

## Node Agent Possession Evidence Protocol

Phase 12F introduced a dedicated possession-evidence protocol for authenticated Node Agents.

The contract accepts observation data while explicitly excluding caller-controlled authority fields.

The Node Agent may report assignment identity, observed size, observed checksum, observation time, and agent version.

The Node Agent cannot select its authenticated identity, destination identity, lifecycle state, target state, verification result, verified status, or filesystem path.

Observation timestamps must be timezone-aware and the protocol rejects unexpected fields.

---

## Authenticated Possession Evidence Endpoint

The Node Agent may submit possession evidence through an authenticated endpoint.

Both the global API boundary and Node Agent credential boundary are enforced.

Cross-node submissions are rejected.

Unknown assignments are rejected.

Assignments that have not reached transferred state are rejected.

Successful submission creates pending evidence and advances the legal lifecycle to verification_pending.

---

## Observation Does Not Equal Verification

The Node Agent-facing endpoint deliberately does not decide whether reported size or checksum observations are correct.

Even an incorrect observation may enter the system as pending evidence.

That behavior is intentional.

The node reports what it observed.

BOL determines whether the observation is correct.

---

## Node Agent Cannot Self-Verify

Phase 12 closure testing explicitly confirmed that no Node Agent verification or finalization endpoint exists.

The Node Agent may participate in these lifecycle advances:

- assigned to transfer_pending
- transfer_pending to transferred
- transferred to verification_pending

The transition from verification_pending to verified remains BOL-controlled.

The deterministic verification and finalization operation remains internal to the BOL control plane.

---

## Complete Phase 12 Lifecycle

With Phase 12A through Phase 12F complete, the replica lifecycle is:

assigned → transfer_pending → transferred → verification_pending → verified

Each state has a distinct meaning.

### assigned

BOL has created replica-placement intent.

### transfer_pending

The authenticated destination has accepted the assignment.

### transferred

The destination reported transfer completion consistent with the assignment contract.

### verification_pending

Authenticated possession evidence exists and is awaiting BOL evaluation.

### verified

BOL has deterministically accepted evidence and completed the legal lifecycle transition.

---

## Phase 12 Closure Audit

A final read-only closure audit confirmed:

- the authoritative lifecycle map contains the intended legal transitions
- the Node Agent exposes no verification or finalization endpoint
- the internal finalizer is not exposed through Node Agent HTTP
- ReplicaAssignmentStateManager is the sole normal assignment-state writer in the active Phase 12 path
- trust-table constraints match the lifecycle model
- no Phase 12 TODO, FIXME, or temporary implementation markers remain
- certification transactions leave no synthetic trust records behind

Phase 12 therefore closes with its central control-plane principle intact:

> Nodes report evidence. BOL derives authoritative state.

---

## Phase 12 Complete

Phase 12 now provides the protocol, storage, evidence, and trust boundaries required to move from replica assignment intent to BOL-verified replica state.

The next phase moves from individually certified components to end-to-end integration across the complete replica lifecycle.

Phase 13 will validate the sequence as one system:

assignment → authenticated acceptance → durable storage → transfer completion → possession evidence → BOL verification → verified replica

This becomes the foundation for future durability accounting, recovery-source trust, multi-node failure testing, and deployment-facing integration.

---

**BOL — Future of AI Infrastructure**

Building toward a consumer-owned distributed infrastructure network for storage, delivery, compute, and future AI workloads.
