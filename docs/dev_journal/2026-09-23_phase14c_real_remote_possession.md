# September 23, 2026 — First real remote possession challenge

BOL completed its first successful real remote Node Agent possession challenge over certificate- and hostname-verified HTTPS in a controlled development experiment.

> Nodes report evidence. BOL derives authoritative state.

This journal uses the project's America/New_York development date; the successful response was recorded shortly after midnight UTC on September 24.

## What was established

A database-free, authenticated remote Node Agent read a synthetic 1-KiB object through its independent Node Agent storage boundary. The agent had no database or control-plane administrative authority. BOL issued the challenge and independently measured **1,024 returned bytes** and computed **SHA-256**, matching the authoritative expected size and checksum.

The canonical record contains one delivery, one response start, one possession observation and one accepted decision for the successful attempt. Acceptance occurred within the server-issued challenge window. Historical possession assurance was established.

The earlier attempt missed its deadline before a response was submitted. It remains preserved in the audit history; existing control-plane logic subsequently recorded its missed-deadline decision. The successful attempt used an explicitly authorized, coordinated operator workflow rather than requiring manual terminal switching during the response window. There is no automatic retry.

Read-only reconciliation confirmed the accepted outcome, authenticated identity bindings and retained observation history. The worker and controller terminated, their resource ownership ended, and the campaign listener stopped. This was a real remote experiment, rather than the earlier simulated transport certification.

## Evidence is not current durability

The successful result remains **historical possession assurance**:

- `proof_lifetime` remains **NULL/unconfigured**.
- Current qualifying durability remains **zero**, and durability remains **unproven**.
- Node qualification remains pending; a successful response does not grant qualification or refresh heartbeat.
- Automated re-verification and renewal remain future work.
- Automated repair and re-replication remain future work; no automatic repair occurred.

The proof establishes that an authenticated endpoint supplied the expected bytes within the bounded challenge window. It does **not** prove continuous storage, local-disk residency, independent devices or operators, or inability to retrieve bytes from another source.

One synthetic object and one successful remote response do not establish fleet capacity, availability guarantees or a numeric freshness policy. Further controlled measurements and policy review must precede freshness activation.

## Direction from here

**Storage → verified possession → freshness/durability → automated recovery → vendor-neutral/cloud-agnostic interoperability → CDN → compute → AI infrastructure**

The completed milestone advances verified possession. Freshness and qualifying durability remain the next evidence-and-policy boundary; automated recovery follows separate design and certification.

BOL's interoperability direction spans **AWS, Azure, GCP, on-premises and BOL-native infrastructure**. S3 compatibility is one planned interoperability interface, not BOL's platform identity or a claim of delivered integration. CDN, compute and AI infrastructure remain longer-term goals. AI remains non-authoritative.

See the [Phase 14 foundation journal](2026-09-20_phase14_durability_possession_assurance.md), [current development and roadmap](../../README.md#current-development), and [architecture](../architecture.md).
