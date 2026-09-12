# BOL Development Journal — September 11, 2026

## Phase 11 — Replica Trust Architecture

Phase 11 focused on a deceptively simple question:

**When BOL says that a replica exists, what exactly proves that statement is true?**

Earlier generations of the prototype could persist replica metadata describing where a copy was expected to exist and what state that replica was believed to be in. That was useful while validating distributed storage mechanics, but the model was no longer strong enough for the next stage of BOL.

A database row that says a replica exists is not proof that an independent copy is actually present on a node.

Phase 11 therefore rebuilt the replica trust boundary around a stricter rule:

**assignment intent is not possession evidence.**

The work established a control-plane model in which BOL separately represents what the system asked a node to do, what the node later observed, how BOL judged that observation, and when authoritative assignment state is allowed to change.

This phase was intentionally completed before beginning the Node Agent storage protocol. The goal was to define truth first, then build transport on top of that truth model.

## Separating Assignment Intent From Possession Evidence

The first architectural change was to split replica responsibility into two distinct concepts.

A **replica assignment** represents control-plane intent. It records that BOL expects a particular physical chunk to be copied to a particular destination node, together with authoritative expectations and lifecycle information.

A **replica evidence record** represents an observation reported after storage activity. It records which authenticated node reported the observation, the byte size it observed, the checksum it calculated, when the observation was collected, and the eventual BOL verification result.

These records deliberately answer different questions.

An assignment answers:

**What did BOL instruct the system to create?**

Evidence answers:

**What did an authenticated node report observing?**

Neither statement by itself proves that a trustworthy independent copy exists.

That proof only emerges after BOL evaluates the evidence against authoritative expectations.

## Building the Replica Trust Schema

Phase 11 introduced an explicit database migration for the new trust model.

The assignment schema contains server-controlled expectations and lifecycle state. Active assignments are protected against conflicting destination and replica-ordinal combinations, while relationships keep assignments anchored to known physical chunks and registered nodes.

The evidence schema keeps observations separate from assignment metadata. Evidence begins in a `pending` state and may later become `verified` or `rejected` only through deterministic BOL logic.

Database constraints enforce important invariants around sizes, checksums, verification timestamps, rejection reasons, lifecycle states, and relationships between trust records.

The migration was designed to be explicit and version-controlled rather than silently executed during application startup.

Infrastructure schema changes should be reviewable, reproducible, and recoverable independently from application boot behavior.

## Assignment Creation Is a Control-Plane Operation

A dedicated replica trust service was introduced for assignment creation.

The caller may identify the physical chunk, proposed destination, and replica ordinal, but it does not establish authoritative expectations about the data.

Expected byte size and checksum come from BOL's own physical-chunk metadata.

Before creating an assignment, BOL validates the source metadata and ensures that the destination satisfies the appropriate placement boundary.

The destination cannot simply become trusted because a caller supplied a node identifier.

This preserves the broader principle established during earlier control-plane hardening:

**trust gates placement; placement does not create trust.**

Adversarial testing exercised invalid assignments, unusable source metadata, inappropriate destinations, conflicting active assignments, and placement-ineligible nodes.

Valid assignment testing also confirmed that BOL derives its expectations from authoritative metadata rather than caller-provided claims.

## Evidence Submission Records Observation, Not Judgment

The next boundary was evidence submission.

A Node Agent will eventually report what it observed after writing replica data. Phase 11 established that this submission path may carry observations, but it may not declare infrastructure truth.

The reporting node identity is derived from authenticated node identity rather than independently selected by the payload.

Every newly submitted observation enters the system as `pending`.

The submission path cannot declare its evidence verified, manufacture a verification timestamp, choose its own rejection reason, or change assignment lifecycle state.

This boundary was deliberately tested with incorrect observations.

Evidence from an unexpected authenticated node was preserved as the observation that actually occurred, but remained pending.

Evidence containing an incorrect checksum also remained pending.

This is intentional:

**submission records what was observed; submission does not decide whether the observation is true.**

That distinction strengthens both trust and auditability.

## Introducing an Explicit Assignment State Machine

Before implementing evidence verification, Phase 11 introduced a dedicated assignment state manager.

The goal was to prevent future code from directly writing arbitrary lifecycle states and quietly bypassing control-plane rules.

The normal lifecycle is represented explicitly:

`assigned` → `transfer_pending` → `transferred` → `verification_pending` → `verified`

Failure, expiry, and revocation paths are modeled separately.

Terminal assignments cannot be resurrected. Replaying a transition to the state an assignment already occupies is idempotent. Expiration is based on BOL-controlled time and assignment policy.

Row locking protects transitions so concurrent workers cannot independently make incompatible lifecycle decisions against the same assignment.

Additional evidence gates protect sensitive transitions.

Entering `verification_pending` requires an observation from the intended destination.

Entering `verified` requires BOL-verified evidence from that destination.

The state manager itself does not create evidence and does not perform evidence verification. It only determines whether an authoritative state transition is legal.

This preserves a critical separation:

**observation, judgment, and state mutation are different authorities.**

## Deterministic Evidence Verification

With lifecycle authority defined, Phase 11 added deterministic evidence verification.

Only pending evidence associated with an assignment at the appropriate verification stage may be judged.

If the lifecycle has not reached that stage, the evidence remains pending. A potentially valid observation should not be rejected merely because the control plane is not yet ready to evaluate it.

When verification proceeds, BOL compares the observation against authoritative assignment expectations.

The verifier evaluates destination identity, observed byte size, and observed checksum.

Mismatches produce deterministic rejection reasons.

If the required checks succeed, the evidence becomes `verified` and receives a BOL-controlled verification timestamp.

Verification is final and idempotent. Re-running verification against finalized evidence returns the existing judgment rather than rewriting history.

Most importantly:

**successful evidence verification still does not change assignment state.**

After evidence becomes verified, the assignment remains at the verification stage until the assignment state manager separately authorizes the final lifecycle transition.

That separation was explicitly tested.

## Adversarial Validation

Phase 11 was not accepted simply because the new services compiled.

The trust boundaries were exercised against adversarial conditions including invalid assignments, conflicting active assignments, inappropriate destinations, incorrect reporting identities, incorrect observed sizes, incorrect checksums, illegal lifecycle jumps, premature expiration, terminal-state resurrection attempts, and repeated operations.

Idempotent behavior was tested where retry safety is required.

The validation also confirmed that evidence submission cannot manufacture verification and that evidence verification cannot silently mutate authoritative assignment state.

Temporary test state was isolated and rolled back after certification.

## End-to-End Trust Certification

The complete Phase 11 trust chain was then exercised as one end-to-end transaction.

A replica assignment was created from authoritative physical-chunk metadata.

The assignment progressed through its pre-verification lifecycle.

The destination submitted a pending observation containing locally observed size and checksum information.

The state manager authorized entry into the verification stage because destination evidence existed.

BOL then deterministically verified the evidence.

At that moment, the evidence was verified while the assignment deliberately remained at the verification stage.

Only a separate control-plane transition changed the assignment to `verified`.

The resulting invariant is now explicit in both architecture and implementation:

**assignment intent ≠ node observation ≠ BOL verification ≠ authoritative state transition.**

## Why This Matters

Phase 11 changes what replication will mean inside BOL.

A future durability engine will not need to trust a historical status field simply because it claims that a replica exists.

It will be able to reason from a stronger chain:

BOL created an assignment.

An authenticated destination reported an observation.

BOL independently evaluated that observation against authoritative expectations.

The control plane explicitly accepted the verified result into the replica lifecycle.

That creates a stronger foundation for durability, recovery, auditability, customer reporting, compliance controls, and future BOL Intelligence.

It also establishes a reusable architectural pattern for the broader platform:

**external actors report evidence; BOL derives authoritative state.**

## Phase 11 Status

Phase 11 is complete after adversarial and end-to-end validation.

The validated internal milestone is represented by:

`phase11-replica-trust-validated`

Historical replica metadata was not automatically reinterpreted as verified possession.

The new trust layer becomes meaningful through authenticated storage behavior and evidence generated by the Node Agent protocol.

## Next — Phase 12: Node Agent Storage Protocol

The next phase moves from trust semantics to real storage behavior.

Phase 12 will define the Node Agent storage protocol rather than treating transfer as a simple file copy.

The protocol will address assignment acceptance, destination path ownership, transfer identity, partial-write handling, write-completion semantics, local checksum computation, retry and idempotency behavior, interruption and failure semantics, and authenticated evidence produced after a destination independently stores replica bytes.

Phase 11 now gives that protocol a clear destination:

**transport may move bytes, but only evidence and deterministic control-plane validation can establish that BOL possesses a verified independent replica.**
