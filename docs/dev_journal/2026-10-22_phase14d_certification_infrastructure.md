# Phase 14D: Certification Infrastructure

Engineering checkpoint: 2026-10-22.

## Purpose

Record the certification-support boundary reached during Phase 14D. The work
separates reviewed environment expectations, private authentication material,
identity observation, directory provenance and activation authorization.
Accepted source capability and operator-observed deployment metadata are distinct
evidence. Neither alone authorizes credential access or database certification.

## Certification boundary progression

1. **Private configuration parsing.** A strict bytes parser accepts only the
   reviewed format version, mode-bound role and password. It rejects duplicate
   or unexpected fields, malformed encoding and invalid values. Authentication
   material cannot redefine the trusted database, transport or environment.
   Returned values are immutable and redact secrets in ordinary representation.
2. **Descriptor-safe credential loading.** An internal loader consumes an
   already-open directory FD, validates its required metadata, and opens only
   the fixed mode-bound target relative to it. File type, ownership, permissions,
   link count and size are checked. Bounded descriptor reads and pre/post-read
   metadata checks precede parser delegation. The loader owns its file FD and
   preserves the caller-owned directory FD. Synthetic tests do not establish
   real credential provenance.
3. **Account facts and policy.** Immutable `AccountFacts` and `AccountPolicy`
   values express account/process consistency requirements. Supplied values
   remain forgeable observations, not proof of live OS identity or authority.
4. **Directory traversal.** Descriptor-relative traversal validates each opened
   directory against reviewed system/private rules. No-follow opening rejects
   symlink components. The caller owns the anchor; traversal owns child FDs and
   exposes the final FD only during its context.
5. **Error and cleanup hardening.** Pathological caller-supplied anchor-FD
   conversion failures receive fixed sanitized errors. Traversal setup errors
   are separated lexically from caller-body execution. Cleanup attempts each
   owned FD once in reverse order, without retry; cleanup failure has explicit
   outward precedence. Body exceptions propagate unchanged when cleanup succeeds.
6. **Live identity observation.** An unused explicit-call primitive captures
   process identities and performs forward/reverse OS/NSS account lookups.
   Exact types, nonroot identity, process/account agreement and fixed account/home
   policy are required. Reverse UID agreement is checked before fact construction.
   Lookup failure remains fail closed. Import performs no identity observation.
7. **Identity and fixed-policy composition.** A private composition layer
   independently validates an initial identity snapshot, constructs the fixed
   traversal policy, traverses from a caller-owned anchor, validates a second
   snapshot and requires full equality before exposing the final FD. Invalid
   snapshots retain validation errors; only valid unequal snapshots produce
   `identity_changed`. Tests use synthetic anchors and test-only ownership
   observations; support policy has no ownership override.
8. **Adoption guards.** Static AST regressions constrain exact approved support
   dependencies and prohibit production consumers. Import provenance is retained
   across binding reuse; aliases, repository-relative imports and package
   attributes are covered. Comments and ordinary strings are not dependencies.
   These guards do not claim hostile dynamic-import or runtime scope analysis.
9. **Fixed root anchor capability.** A separate unused opener adds the narrowly
   bounded source capability described below, without composing credential access.

## Identity and path authority

The reviewed account/home policy is fixed internally; numeric account identities
come from validated OS records rather than deployment-specific source constants.
Real/effective process identities and forward/reverse account observations must
agree. Full immutable snapshot equality supports the later identity recheck.

Identity consistency is not credential eligibility, possession, recovery authority
or permission to mutate application state. Directory provenance checks similarly
do not establish protection against hostile same-user control, privileged mount
changes or compromised NSS. Synthetic ownership observations certify test logic,
not deployment ownership.

## Fixed root anchor capability

The private opener has no caller arguments and opens only literal `/`, using
exactly `O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`. Required constants must
be available and satisfy exact integer validation; no weaker fallback exists.
A returned FD is accepted only as an exact nonnegative integer and then owned
for one close attempt. Failed opening creates no cleanup obligation.

Opening errors and cleanup errors use fixed sanitized reasons. Caller-body
exceptions remain outside opening-error normalization. Close failure takes
outward precedence without retry. The opener performs no provenance inspection;
`O_DIRECTORY` is an opening constraint, not ownership or filesystem proof.

This capability was mock-tested only. Anchor tests substitute opening and closing
boundaries and use synthetic FD values. The BOL opener has not been activated as
runtime certification, and BOL live-root traversal has not been activated.

## Regression boundary

The committed certification-support regression boundary is **114 PASS, 0 FAIL**:

| Suite | Passing tests |
| --- | ---: |
| Fixed root anchor | 13 |
| Identity/root composition and adoption scanner | 15 |
| Live identity observation | 10 |
| Private-root traversal | 20 |
| Private credential loader | 14 |
| Private configuration parser | 13 |
| Certification manifest | 15 |
| Certification identity/emptiness contract | 14 |
| **Total** | **114** |

These are mock, synthetic-filesystem and pure-contract results. They do not imply
real root provenance, credential access or PostgreSQL concurrency certification.

## Deployment receipt

A separate fresh, read-only operator receipt was reported for this checkpoint.
It confirmed the source checkpoint, deployment identity agreement with reviewed
account assumptions, and reviewed ownership/mode conditions for root/home
ancestors. The home filesystem was observed as expected native Linux/ext4 storage.

The optional `.config` directory was absent. The intended certification root was
therefore not provisioned or reachable through that parent. This was operator
metadata evidence, not successful BOL descriptor traversal or certification-root
verification. No credential contents were inspected.

The final operational decision was:

`STOP_NO_INVOCATION_PROVISIONING_DESIGN`

## What this milestone proves

Reviewed and mock-tested code can open fixed `/` using required fail-closed flags
and deterministic FD lifecycle. Accepted synthetic composition tests exercise
identity validation/recheck, fixed policy and descriptor ownership together.
Static regressions constrain current adoption to reviewed certification support
and focused tests.

Separately, the operator receipt recorded deployment assumptions and hierarchy
absence at observation time. It does not turn mock-tested capability into live
runtime certification or guarantee that deployment metadata remains unchanged.

## What this milestone does not prove

- Real BOL root-opener or live-root traversal activation.
- Verification or provisioning of the certification credential root.
- Existence, generation or safety of deployment credentials.
- Absolute filesystem, mount-namespace, NSS or hostile-process security.
- PostgreSQL identity observation, database creation or database certification.
- Production admission, policy activation or authorization for the next operation.

No credential directories were created, no credentials were generated, and no
credential contents were read in this boundary. No real BOL opener or live-root
traversal activation occurred. No PostgreSQL work occurred.

## Current stop condition

Hierarchy absence makes provisioning design the next boundary. Invoking BOL
traversal merely to reproduce known absence is not required progression evidence.
Source acceptance does not authorize live invocation, directory creation,
credential handling or database work.

## Next slice

**Credential-root provisioning design**, not provisioning execution. Review must
address ownership and restrictive modes, existing-path refusal, symlink resistance,
creation ordering, umask, atomicity and rollback. Credential generation/storage
and later credential-loader composition require their own reviewed boundaries.
Any subsequent live operation requires explicit authorization and current evidence.

## End-of-day checkpoint

- Date: 2026-10-22
- Branch: `private-development`
- HEAD: `2b9919ca912a8287446ac04bb9c3ee6cd67fad41`
- Certification regression: **114 PASS, 0 FAIL**
- Working tree at checkpoint: **clean** (reported authoritative state, before this
  documentation candidate)
- Next slice: **credential-root provisioning design**
- Activation: **not authorized**
