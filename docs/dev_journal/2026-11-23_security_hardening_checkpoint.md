# Security Hardening Checkpoint

Engineering checkpoint: 2026-11-23.

## Current boundary

BOL's architecture audit comes before further possession freshness and renewal
work. The current focus is storage-path security hardening, isolated primitives
and bounded verification. Storage-path remediation remains incomplete. This
checkpoint does not establish production readiness, integration with BOL's
storage services, API activation or deployment.

Storage-path security hardening is incomplete. Don't expose this prototype to
untrusted users or use it with sensitive data.

## Proposed storage architecture

The proposed architecture uses opaque BOL-generated identifiers for storage
objects. Customer filenames remain display metadata rather than storage
identities. This is proposed architecture, not deployed remediation.

Isolated checks do not establish that the proposed protections work throughout
BOL's storage services.

## Bounded reconstruction

The proposed controlled-prototype scope allows at most four reconstruction
inputs, each at most 16 MiB. Each complete input must pass integrity verification
before its bytes are written to the output.

These limits do not establish compatibility with existing data, safe total
memory use, filesystem capacity or end-to-end reconstruction correctness.
Oversized or otherwise rejected inputs cannot be treated as successful partial
reconstruction. This work remains separate from BOL's storage-service workflows.

## Verification evidence

Focused synthetic tests cover isolated reconstruction, cooperative locking and
resource lifetimes, and metadata-only file admission. Synthetic results are
distinct from real-kernel evidence and do not certify production behavior.

A real-kernel test of BOL's metadata-only file admission check recorded **11/11 PASS on Linux 6.8**. The preserved evidence includes
observed kernel rejections reported as `EXDEV` and `ELOOP`, verified closure of
the file descriptors owned by the check, return to the baseline descriptor set
and verified removal of the disposable test fixtures and their enclosure.

That result applies only to the exercised metadata-only admission check. It
excludes mount crossings, special links provided by the process filesystem,
production ownership and locking guarantees, opening files to read their data,
complete control of storage writers, verification of the intended source object
during file publication, and independent agreement between storage objects and
BOL's metadata records. The observed `EXDEV` rejection is not evidence that
mount crossings were tested.

The evidence was preserved from manually copied terminal scrollback; its
byte-for-byte fidelity to the original terminal stream was not independently
established. The descriptor observations cannot detect a descriptor closed and
reopened with the same number and object identity.

The bounded PASS does not certify storage-path remediation or the complete
proposed architecture.

## Preservation and remaining work

The private engineering checkpoint was preserved using an off-server,
hash-verified Git bundle. Its hash was independently checked against the server
copy. This establishes matching checkpoint preservation, not production
certification.

Remaining work includes safe file publication, ownership and locking guarantees, integration with BOL's storage services, compatibility with existing data, and adversarial review before any deployment.
