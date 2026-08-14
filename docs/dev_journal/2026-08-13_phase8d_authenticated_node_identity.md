# BOL Development Journal — August 13, 2026

## Phase 8D — Authenticated Node Identity and Heartbeat Trust Boundary

**Project:** BOL  
**Development stage:** Controlled Private Prototype  
**Phase:** 8D  
**Status:** Completed and privately checkpointed

---

## Session Objective

Today's engineering session focused on establishing a fundamental security
boundary for the BOL node network:

**A node must not be able to declare its own identity and have the network
implicitly trust that declaration.**

Earlier prototype behavior relied on node identifiers supplied as part of
requests. That was sufficient while validating basic distributed-storage
behavior, but it is not an acceptable trust model for a network containing
independently operated nodes.

Phase 8D therefore introduced the foundation for authenticated node identity.

The central architectural rule established today is:

> A node does not tell BOL who it is. BOL determines who the node is from
> authenticated credentials.

This principle now forms the foundation for authenticated communication between
future BOL Node Agents and the BOL control plane.

---

# 1. Starting Architecture

Development began from the previously validated trusted-device qualification
pipeline.

The existing system already contained mechanisms for:

- node registration;
- node heartbeat tracking;
- node health monitoring;
- storage allocation;
- distributed chunk placement;
- replica management;
- automatic failover and recovery;
- integrity verification;
- storage reconciliation;
- device qualification assessments;
- qualification evidence processing;
- qualification state transitions.

Before modifying authentication behavior, the current database, schema,
qualification services, node services, HTTP boundaries, and credential-related
structures were audited.

This was intentionally performed as a read-only investigation before introducing
new authentication logic.

---

# 2. Database and Schema Audit

The active database/schema structure was inspected to determine whether an
existing credential foundation could safely support Phase 8D.

The node credential structure was confirmed to contain metadata for:

- credential identity;
- associated node identity;
- credential hash;
- credential status;
- creation timestamp;
- last-use timestamp;
- revocation timestamp.

The credential-to-node relationship was also verified.

The architecture therefore already supported the concept that a credential
belongs to a specific node.

The credential table contained no active operational records at the beginning
of the controlled test sequence, allowing the new lifecycle to be validated
without interfering with existing node state.

---

# 3. Credential Architecture Decision

A dedicated node credential service was introduced rather than embedding
credential handling directly inside the broader node service.

This preserves separation of responsibilities.

The credential layer owns:

- credential generation;
- credential identifiers;
- credential hashing;
- credential verification;
- credential persistence;
- active credential lookup;
- credential lifecycle metadata.

The node service continues to own broader node behavior.

This separation is intentional because authentication is a security boundary,
not simply another node property.

---

# 4. Credential Security Model

Several security invariants were established.

## Raw credential handling

A raw node credential exists only when initially generated.

The raw credential is returned to the caller during credential issuance but is
not stored as plaintext.

The persistent representation is a cryptographic hash.

Raw credentials are intentionally excluded from diagnostic output and normal
service responses.

## Credential verification

Presented credentials are verified against stored hashes rather than compared
against stored plaintext credentials.

Credential comparison uses a constant-time verification path.

This reduces exposure to timing-based comparison behavior.

## Credential lifecycle

Credentials have explicit lifecycle state.

The current model distinguishes active and revoked credentials and records
credential usage metadata.

A revoked credential is no longer eligible to establish node identity.

---

# 5. Credential Persistence

Credential persistence was added and tested against the active database
boundary.

Controlled testing verified that:

- a credential can be generated;
- a credential identifier is generated;
- the credential is associated with the intended node;
- the database stores the credential hash;
- the raw credential is not stored;
- the credential begins in active state;
- active credential metadata can be retrieved;
- credential hashes are not exposed by metadata lookup;
- raw credentials are not exposed by metadata lookup.

The credential lifecycle test also verified that exactly the expected active
credential existed for the disposable test node.

Test records were removed after validation.

---

# 6. Implementation Defects Found During Testing

The credential work was deliberately tested incrementally rather than committed
immediately.

That process exposed several defects.

## Service initialization mismatch

An early controlled test instantiated the credential service without the
database connection/cursor boundary required by its constructor.

The test was corrected to initialize the service through the proper database
boundary.

## Hash method mismatch

The credential persistence path initially referenced a hashing method name that
did not match the actual established service API.

Inspection showed that the credential service exposed the existing secret
hashing primitive under a different method name.

The implementation was corrected to use the established hashing method rather
than introducing a duplicate hashing implementation.

## Active credential invocation mismatch

A later lifecycle test passed an incorrect number of arguments to the active
credential lookup method.

Rather than changing the service blindly, the public method signatures were
inspected and the test invocation was corrected to match the actual service
contract.

After these corrections, the complete credential lifecycle passed.

These failures were useful because they validated the service boundary before
HTTP integration began.

---

# 7. Credential Lifecycle Validation

The corrected lifecycle test verified:

- credential creation;
- credential ID generation;
- raw credential returned only to the caller;
- raw credential intentionally omitted from logs;
- hashed persistence;
- association with the correct node;
- active credential status;
- successful verification of the correct credential;
- rejection of an incorrect credential;
- active credential metadata retrieval;
- non-exposure of the credential hash;
- non-exposure of the raw credential.

After testing, disposable credential and node records were removed.

The database returned to its clean pre-test state.

---

# 8. Authentication Trust-Boundary Audit

With credential persistence working, the next question was more important:

**What actually determines node identity?**

The existing node-facing paths were inspected for caller-supplied `node_id`
trust points.

This audit included qualification processing, heartbeat handling, node
operations, service methods, request models, and existing HTTP routes.

The audit confirmed that prototype-era request flows still allowed node
identifiers supplied by the caller to participate directly in node operations.

That behavior needed to change before node credentials would provide meaningful
security.

---

# 9. Core Phase 8D Security Invariant

The following invariant was adopted:

**Caller-supplied node identity is not authenticated identity.**

A credential belonging to NODE-A must never allow a caller to operate as
NODE-B.

The credential itself must determine which node is authenticated.

Conceptually:

Node Agent  
→ presents node-specific credential  
→ BOL authenticates credential  
→ BOL derives authenticated node identity  
→ authenticated identity enters trusted service boundary

The client does not choose `authenticated_node_id`.

The server derives it.

---

# 10. Separation from Control-Plane Authentication

BOL already uses a separate API authentication mechanism for protected
control-plane endpoints.

That mechanism was intentionally preserved.

Phase 8D does **not** treat the global/control-plane API authentication mechanism
as node identity.

These are separate trust boundaries:

**Control-plane authentication**
determines whether a caller may access protected BOL API functionality.

**Node authentication**
determines which specific node is communicating with BOL.

Keeping these boundaries separate prevents a shared administrative/API
credential from becoming equivalent to node identity.

---

# 11. Node Authentication Service

A dedicated authentication service was introduced.

Its responsibility is to establish authenticated node identity from a presented
node credential.

The authentication flow performs the following conceptual sequence:

1. Receive a presented node credential.
2. Reject a missing credential.
3. Locate eligible active credential records.
4. Verify the presented credential against stored hashes.
5. Reject invalid credentials.
6. Reject revoked credentials.
7. Resolve the credential to its associated node.
8. Produce a server-derived authenticated node identity.
9. Record credential usage metadata.

Authentication responses expose identity metadata needed by the trusted service
boundary without exposing credential hashes.

---

# 12. Adversarial Node Authentication Test

A controlled adversarial test was performed using two disposable nodes.

The purpose was not simply to prove that valid authentication worked.

The test was designed to prove **identity isolation**.

Two nodes were created:

- NODE-A
- NODE-B

Each received its own node-specific credential.

The following conditions were validated:

- Credential A authenticates successfully.
- Credential A resolves to NODE-A.
- Credential B authenticates successfully.
- Credential B resolves to NODE-B.
- Credential A cannot establish NODE-B identity.
- Credential B cannot establish NODE-A identity.
- An invalid credential is rejected.
- A missing credential is rejected.
- A revoked credential is rejected.
- Revoking NODE-A's credential does not invalidate NODE-B.
- Successful credential usage records last-use metadata.

The result was:

**NODE AUTHENTICATION TRUST BOUNDARY VALIDATED**

The authenticated identity was confirmed to be server-derived.

All disposable test data was then removed.

---

# 13. Heartbeat Trust Audit

Once node authentication was working, the heartbeat path became the next
critical boundary.

Heartbeat is important because it influences whether BOL believes a node is
online and healthy.

The existing heartbeat request model still contained a caller-supplied node
identifier.

The service then used that value when updating node state.

That meant a client could conceptually claim:

"I am node X."

That behavior contradicted the new authentication model.

---

# 14. Authenticated Heartbeat Architecture

The heartbeat architecture was changed so that node identity no longer comes
from the heartbeat payload.

The heartbeat request model was reduced to operational heartbeat information.

Node identity is now derived through the authentication layer.

Conceptually the new path is:

Node Agent  
→ node-specific credential  
→ Node Authentication Service  
→ server-derived authenticated node identity  
→ heartbeat service  
→ update only authenticated node

The service boundary now receives authenticated identity separately from the
heartbeat payload.

The heartbeat payload therefore cannot select which node receives the update.

---

# 15. Heartbeat Request Model Change

The caller-controlled node identifier was removed from the heartbeat request
model.

The model now contains heartbeat state rather than identity authority.

This is a small code change with significant architectural impact.

It prevents request-body manipulation from becoming an identity mechanism.

---

# 16. Heartbeat Service Change

The node heartbeat service was updated to accept an already-authenticated node
identity.

Database updates now target the server-derived authenticated node rather than a
node identifier supplied by the heartbeat payload.

Returned heartbeat metadata similarly reflects the authenticated identity.

This pushes the identity decision upward into the authentication boundary where
it belongs.

---

# 17. Authenticated Heartbeat HTTP Boundary

The heartbeat HTTP route now requires a node-specific credential.

The route:

1. receives the node credential;
2. invokes the node authentication service;
3. rejects failed authentication;
4. obtains the server-derived authenticated node identity;
5. passes that identity into the heartbeat service;
6. performs the heartbeat mutation only after successful authentication.

A failed authentication therefore does not reach the trusted heartbeat mutation
path.

---

# 18. Adversarial Heartbeat Testing

A second adversarial test validated the complete authenticated heartbeat trust
boundary.

Again, two disposable nodes and independent credentials were used.

The test confirmed:

- the heartbeat payload contains no node identity selector;
- the caller cannot select heartbeat identity;
- Credential A updates NODE-A;
- NODE-B remains untouched by NODE-A's heartbeat;
- Credential B updates NODE-B;
- Credential A cannot establish NODE-B identity;
- Credential B cannot establish NODE-A identity;
- invalid credentials are rejected;
- missing credentials are rejected;
- revoked credentials are rejected;
- failed authentication causes no heartbeat mutation;
- credential use remains auditable through last-use metadata;
- revoking NODE-A does not affect NODE-B.

The result was:

**AUTHENTICATED HEARTBEAT TRUST BOUNDARY VALIDATED**

The disposable test records were removed afterward.

---

# 19. Regression Discovered During Final Validation

During final regression testing, application import unexpectedly stalled.

Rather than assuming the new authentication code caused the failure, the import
was run under a timeout with diagnostic traceback behavior.

The diagnostic showed application initialization waiting during database-related
startup work.

Database activity was then inspected.

Multiple stale/competing BOL database sessions were found, including sessions
performing schema-related initialization activity.

This created lock contention during application import.

---

# 20. Database Lock Investigation and Recovery

The stale BOL sessions were deliberately identified and terminated.

After the competing sessions were cleared:

- database session state was rechecked;
- application import was rerun with a timeout;
- the application imported successfully;
- the import process exited normally.

This confirmed that the apparent startup regression was caused by stale
database session/lock contention rather than the authenticated-node changes.

This was an important operational finding.

As BOL evolves toward a continuously running distributed infrastructure system,
database session management and startup-time schema behavior will require
continued hardening.

---

# 21. Final Regression Gate

After the database contention issue was cleared, the Phase 8D regression gate
was rerun.

Validation included:

- Python compilation;
- application import;
- credential lifecycle behavior;
- authentication behavior;
- cross-node identity isolation;
- credential revocation;
- credential usage tracking;
- heartbeat authentication;
- heartbeat identity isolation;
- failed-authentication mutation protection;
- database cleanliness;
- inspection for remaining caller-controlled heartbeat identity references;
- verification that control-plane authentication remained separate.

The stack compiled successfully.

Application import completed successfully.

Controlled test records were cleaned from the database.

No active heartbeat path remained where the request payload itself selected node
identity.

---

# 22. Security Architecture Established Today

Phase 8D establishes several important BOL security principles.

### Identity is credential-derived

A node identifier is metadata.

A valid credential establishes identity.

### Authentication precedes trusted mutation

Node state should not be mutated until node identity has been authenticated.

### Cross-node impersonation is prohibited

A credential associated with one node cannot establish another node's identity.

### Raw credentials are ephemeral

Raw credentials are returned during issuance but are not persisted as plaintext.

### Stored authentication material is not exposed

Credential hashes remain inside the authentication boundary.

### Credential use is auditable

Successful credential use updates usage metadata.

### Revocation is isolated

Revoking one node's credential does not invalidate unrelated nodes.

### Control-plane and node identity remain separate

Administrative/API access and node identity represent different security
questions and remain separate trust boundaries.

---

# 23. Architectural Relationship to Device Qualification

The previous qualification phase answered:

**Should BOL trust this device enough to participate?**

Phase 8D answers a different question:

**Which device is actually speaking to BOL right now?**

Those questions must remain distinct.

Qualification establishes whether a node satisfies participation requirements.

Authentication establishes the identity of the communicating node.

Together they form the beginnings of a stronger device trust architecture:

Device evidence  
→ qualification decision  
→ node credential  
→ authenticated identity  
→ trusted node operation

Future node operations can now progressively move behind this authenticated
identity boundary.

---

# 24. Private Engineering Checkpoint

After final validation, Phase 8D was frozen in the private engineering
repository.

Private checkpoint:

`76ff288`

Private phase tag:

`phase8d-authenticated-node-identity`

The private implementation remains separate from the sanitized public
development history.

No private source code, credentials, database secrets, environment
configuration, infrastructure details, or raw authentication material are
included in this public journal.

---

# 25. Phase 8D Result

Phase 8D successfully established:

**Authenticated Node Identity + Authenticated Heartbeat Trust Boundary**

The most important invariant coming out of today's work is:

> A node does not tell BOL who it is. BOL determines who the node is from
> authenticated credentials.

This changes the BOL node model from prototype-style caller-declared identity
toward an authenticated distributed infrastructure trust model.

---

# 26. Next Engineering Direction

The authenticated identity boundary created in Phase 8D can now be extended to
additional node-originated operations.

Future work should continue moving node actions away from caller-supplied
identity and toward authenticated, server-derived identity.

Likely areas include:

- qualification evidence submission;
- node-agent communication;
- storage-related node operations;
- health reporting;
- authenticated operational telemetry;
- credential issuance and rotation;
- stronger credential revocation workflows;
- eventual device-bound identity mechanisms.

Each integration should preserve the same invariant established today:

**authentication determines identity before trusted state mutation occurs.**

---

## BOL

**Building the Future of Internet**
