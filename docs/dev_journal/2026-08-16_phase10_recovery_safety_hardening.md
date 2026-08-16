# Bol Development Journal — August 16, 2026

## Phase 10 — Recovery Safety, Runtime Hardening, and the Day a Routine Restart Became an Architectural Investigation

**Project:** Bol  
**Development Stage:** Controlled Private Prototype  
**Phase:** 10 — Recovery Safety Hardening  
**Status at End of Session:** Active development; not yet frozen  
**Previous Frozen Checkpoint:** Phase 9 — Authenticated Qualification Identity Boundary

---

August 16 began with what appeared to be one of the least dramatic tasks in the recent history of Bol: inspect the server after several days of development, deal with pending operating-system maintenance, and prepare the runtime for the next phase.

It did not remain a routine maintenance session for very long.

By the end of the day, the work had turned into a forensic investigation of Bol's autonomous recovery system. We reconstructed hundreds of recovery operations, built an isolated clone of the PostgreSQL database, rehearsed reversal of a recovery cascade without touching the live database, identified an architectural weakness in the distinction between persisted node state and actual node liveness, strengthened the rules governing which machines may receive recovered data, and finally tested whether an entire health scan behaves as one atomic database operation.

This was not the Phase 10 session originally expected.

It became a much more important one.

The central lesson of the day can be summarized simply:

> A distributed system must not confuse what it remembers about a machine with what it can prove about that machine right now.

That distinction became the foundation of today's work.

---

## Beginning Phase 10 from a Frozen Trust Boundary

Development began from the frozen Phase 9 private checkpoint.

Phase 9 had established an important identity rule inside Bol: a node submitting qualification evidence cannot authoritatively declare which node it is. The server authenticates the node-specific credential, derives the authenticated node identity, and then requires qualification evidence to agree with that identity before qualification state may be changed.

That checkpoint remained intact at the beginning of Phase 10.

The private development branch pointed to the Phase 9 commit, the corresponding annotated tag resolved to the same commit, and the worktree was clean. Before any Phase 10 development began, the existing application compiled successfully.

The server itself, however, had accumulated operating-system maintenance.

The machine had been running for approximately seventy-five days. PostgreSQL was active, no systemd units were failed, disk and memory utilization were healthy, and the existing Bol API process had been running continuously since August 13. The API was listening only on the local interface at port 8000.

The audit also revealed something important about runtime provenance. The existing API process was running as `root`, its working directory was the private Bol repository, and its database and API configuration had been injected through environment variables. The protected `.env` file was mode `600`, but there was no dedicated Bol operating-system service account and no permanent Bol API systemd service.

That is architectural debt, and it was deliberately recorded rather than casually repaired during an unrelated phase.

The conservative decision was to separate concerns.

Phase 10 would not begin by simultaneously changing the operating-system user model, application service management, directory ownership, scheduler behavior, database state, and recovery policy. Each of those changes has a different blast radius and deserves independent validation.

Before touching the application, the server itself would first be brought to a known-good maintenance state.

---

## Server Maintenance Before Application Development

The host was still running Linux kernel `6.8.0-124-generic` while a newer `6.8.0-137-generic` kernel was already installed. Ubuntu explicitly reported that a restart was required.

Rather than immediately rebooting, the runtime was inspected first.

The running Bol process, its working directory, executable, parent process, environment-variable names, PostgreSQL status, listening ports, virtual environments, and existing systemd components were recorded. The API's current behavior was also checked before shutdown: an unauthenticated request returned HTTP 401, confirming that the existing global API authentication boundary was still active.

Only after the current state was understood was maintenance allowed to proceed.

Following the reboot, the server returned on kernel `6.8.0-137-generic`. The reboot-required marker cleared, PostgreSQL returned active, no systemd units were failed, and port 8000 was intentionally left unused.

Bol was not automatically restarted.

That was deliberate.

The reboot had given us a rare clean operational boundary: PostgreSQL was healthy, the machine was patched, the API was stopped, and the health scheduler was not active. Instead of immediately restoring the previous runtime, we used the opportunity to inspect how Bol would actually return to service after a real host restart.

That inspection exposed the next layer of architectural debt.

---

## Runtime Provenance and the Missing Service Boundary

Bol currently had two Python virtual environments on the server. Both were inspected and found to use the same Python version and the same important application package versions, including FastAPI, Uvicorn, Psycopg2, and Pydantic.

The existing health scheduler already had a systemd oneshot service:

`bol-health-scan.service`

and an associated timer:

`bol-health-scan.timer`

The service loaded database configuration from the protected environment file and executed `health_scheduler.py`. Historical logs showed that the scheduler had previously run successfully and had performed node-health scans and automatic failover operations.

The timer, however, was disabled and inactive after the reboot.

That turned out to be fortunate.

Rather than enabling recurring automation immediately, the existing scheduler was tested exactly once.

This followed an operating principle that became increasingly important during today's work:

> Recurring automation should not be enabled until its one-shot behavior has been observed and understood in the current runtime state.

The one-shot health scan completed successfully from systemd's perspective.

Its output was:

- 21 nodes checked;
- 12 nodes newly marked offline;
- 12 failover operations initiated.

At first glance, this looked like the scheduler doing exactly what it had been designed to do.

But twelve automatic failovers immediately after a controlled reboot demanded investigation.

The timer remained disabled.

The API remained stopped.

Nothing else was allowed to run automatically.

---

## The Moment Phase 10 Changed Direction

A database snapshot was taken immediately after the one-shot scan.

The live PostgreSQL database was then inspected read-only.

All 21 nodes were now marked offline.

Many of them were recognizable development and validation nodes accumulated during previous phases: Phase 5 failover nodes, Phase 6 scheduler nodes, Phase 8 qualification nodes, and earlier USA-prefixed prototype nodes.

Their `last_seen` timestamps ranged from days to months in the past.

This explained why the health scanner considered them stale.

It did not yet explain what the recovery system had done with them.

The event tables told the more interesting story.

During the August 16 scan, the system had generated 553 recovery events in a fraction of a second.

Of those:

- 550 represented automatic primary failover;
- 3 represented automatic rereplication.

A particularly large recovery edge appeared from `USA002` to `USA004`, accounting for 547 primary promotions.

This was the point where the day's objective changed.

The immediate question was no longer:

"How do we restart the Bol API?"

It became:

"What exactly did the autonomous recovery engine believe about these nodes, and why?"

---

## Why the Scheduler Behaved This Way

The health policy was inspected directly in `NodeService`.

The rule was simple.

A node was considered stale if it had no `last_seen` value or if its most recent heartbeat was older than five minutes. If a stale node was not already marked offline, the scanner changed its status to offline and invoked automatic failover.

That behavior was reasonable by itself.

The deeper problem existed in recovery target selection.

Automatic failover searched for replicas whose nodes were persisted as:

`online`

and:

`qualified`

Likewise, automatic rereplication selected nodes persisted as online and qualified.

Those conditions were necessary, but they were not sufficient.

A node could still say `online` in PostgreSQL even though its last heartbeat occurred weeks earlier.

In other words, the database contained two different kinds of truth:

the node's persisted connectivity label, and the timestamp of the last actual communication from that node.

The recovery system was trusting the first while the health scanner was using the second.

That asymmetry created the possibility for a stale node to be considered failed in one part of the system while simultaneously being considered a valid recovery destination in another.

This was not merely a test-data cleanliness problem.

Historical test nodes made the behavior easy to expose, but the underlying rule would matter in a real distributed network as well. A machine may be marked online in persistent state and then disappear because of a network partition, power failure, crashed agent, host failure, or loss of connectivity.

Recovery placement cannot safely rely on a remembered `online` label alone.

It needs current evidence of liveness.

---

## Freezing Automation and Preserving Evidence

At this point no attempt was made to "clean up" the database.

That would have destroyed evidence before the behavior was understood.

Instead, the operational state was frozen:

the API remained stopped;

the health timer remained disabled and inactive;

the Phase 9 source checkpoint remained untouched;

and the post-scan PostgreSQL database was preserved in a protected dump.

The investigation then moved away from the live database.

The goal was to create an isolated forensic environment in which the exact post-scan topology could be examined and manipulated without risking the real Bol database.

The first attempt to create the forensic database failed.

The Bol application database role correctly did not have permission to create databases. The script continued farther than it should have and subsequently attempted to restore into a database that had never been created.

This was useful evidence in its own right.

The failure confirmed that the application database role did not possess unnecessary database-creation privileges, which is the correct security posture. It also exposed a weakness in the test script: a failed prerequisite must stop later steps from presenting misleading success messages.

No live state was affected.

A second precheck inspected the actual PostgreSQL privileges. The Bol database role had login permission but was not a superuser, could not create databases, and could not create roles. PostgreSQL administrative access was separately available through the operating-system `postgres` account.

The forensic database was therefore created through that administrative boundary and assigned to the existing Bol application role.

This time the restore succeeded.

The isolated database was named:

`bol_forensic_aug16`

Critical row counts between the live database and forensic clone matched exactly. The clone reproduced the known post-scan state: 21 nodes, 838 active primary records, and 553 August 16 recovery events.

From that point forward, destructive recovery analysis could occur inside the forensic database while the live Bol database remained untouched.

---

## Reconstructing the Recovery Cascade

The recovery window was reconstructed chronologically.

All 553 events occurred within approximately fifty milliseconds.

The event graph showed:

- 547 automatic failovers from `USA002` to `USA004`;
- 2 automatic failovers from `PHASE5-REPLICA` to `USA004`;
- 1 automatic failover from `PHASE5-REPLICA` to `USA002`;
- 3 automatic rereplications from `PHASE5-REPLICA` to `PHASE8C-E2E-APPLY`.

One detail was particularly revealing.

`USA002` appeared both as a promotion target and as a failed node during the same overall scan.

This demonstrated that recovery decisions were being made while the health scan itself was progressively changing the topology. A node selected earlier in the scan could later be classified stale when its own turn was reached.

The resulting database was internally more consistent than the raw event count initially suggested. There were no duplicate active-primary groups. Every one of the 550 failover recovery events could be matched to a corresponding newly created primary storage record. The recovery records were not phantom events; they represented actual topology mutations.

But the destinations were stale.

After the scan completed, every active primary in the database was located on a node whose current connectivity status was offline.

That was the real architectural finding.

The failover mechanism had executed its instructions correctly.

The instructions were not strong enough.

---

## A Prototype Can Pass Its Tests and Still Reveal a Better Rule

This distinction is important enough to preserve in the engineering history.

The Phase 5 and Phase 6 recovery work was not meaningless because today's investigation found a weakness. Those phases proved that Bol could detect failure, promote replicas, rebuild topology, schedule health scans, and perform autonomous recovery.

Today's work asked a harder question:

"Under what conditions should a node be trusted as a recovery destination?"

That question only became visible because the earlier machinery existed.

Engineering maturity does not mean earlier work never changes.

It means every new layer is allowed to challenge the assumptions of the layer beneath it.

Phase 10 had found such an assumption.

Persisted `online` state was not enough.

Recovery needed a stronger eligibility boundary.


---

## Reversing the Cascade Without Reversing the Live Database

Before changing the recovery algorithm, we wanted to know whether the August 16 cascade was actually reversible.

The forensic clone made that possible.

Each of the 550 automatic failover events was correlated with the primary storage record created during the recovery and with the historical primary record that had been marked failed. The analysis found complete pairing coverage: every failover event had both the newly created primary and the original primary needed to reconstruct the previous topology.

The three rereplication events could likewise be matched to the replica records created during the scan.

This gave us enough provenance to design a rollback algorithm.

But the algorithm was not immediately applied to the live database.

Instead, the entire rollback was rehearsed inside a PostgreSQL transaction against the forensic clone.

The rehearsal removed all 550 August 16-created primary records, restored all 550 original primary records, removed the three August 16-created rereplicas, restored the promoted replica statuses, and removed all 553 recovery events.

After this simulated reversal, the database still contained exactly 838 active primaries and zero duplicate active-primary groups.

Then the entire rehearsal transaction was rolled back.

The forensic database returned to the original post-scan state with all 553 recovery events present.

That sequence mattered.

We had demonstrated that we understood the cascade well enough to reverse it, while deliberately choosing not to make that reversal permanent.

The same rollback algorithm was then used transactionally to preview the topology that existed immediately before the August 16 scan.

That reconstructed topology showed 832 active primaries on `USA002`, three on `PHASE5-REPLICA`, two on `USA005`, and one on `USA004`.

All 838 active primaries were already associated with nodes that were currently offline.

This was another useful clarification.

The August 16 scan had not created the underlying prototype-data problem. It had exposed it.

The database had accumulated historical topology from months of development and testing. The scheduler simply encountered that history through the lens of a real autonomous policy.

That distinction prevented us from "fixing" the wrong problem.

Deleting old test data might make the immediate database look cleaner, but it would not strengthen the recovery rules that a future production network would depend upon.

So the focus remained on policy.

---

## From Node Status to Recovery Eligibility

The architectural correction introduced during Phase 10 was intentionally narrow.

Rather than redesigning the entire node lifecycle, a new recovery-eligibility boundary was added to the node service.

Its purpose was to answer one specific question:

"May this node receive recovery data right now?"

The answer would no longer be derived from `status = online` alone.

A recovery destination must now satisfy several independent conditions.

The node must exist. It must currently be marked online. It must be qualified. It must have a recorded heartbeat. That heartbeat must not be in the future. Most importantly, the heartbeat must still fall within the server-controlled freshness threshold.

The initial threshold remained five minutes, matching the existing health policy.

This created an important distinction in Bol's trust model.

Authentication answers:

"Which node is communicating?"

Qualification answers:

"Has this node demonstrated that it meets the requirements to participate?"

Connectivity state answers:

"What does Bol currently believe about the node's network state?"

Recovery eligibility now asks the stricter question:

"Do we have sufficiently fresh evidence, at the moment of this recovery decision, to trust this node with recovered data?"

Those concepts overlap, but they are not interchangeable.

A node can be authenticated yet unqualified.

A node can be qualified yet offline.

A node can be persisted as online while its heartbeat is stale.

Only a node satisfying the full recovery policy may become a recovery destination.

---

## The Freshness Decision Had to Be Live

The first implementation of the recovery-eligibility boundary introduced a subtle design question.

Should a health scan calculate one timestamp at the beginning of the recovery operation and use that frozen time for every eligibility decision, or should freshness be evaluated against the actual time of each decision?

The stricter interpretation won.

Freshness is meaningful at the moment trust is granted.

Bol therefore evaluates recovery eligibility using the current server time whenever a candidate is considered. A node that was fresh when a long recovery operation began should not automatically remain eligible merely because an earlier timestamp was retained.

For today's prototype-scale workloads, the difference is small.

At distributed-network scale, the distinction becomes much more important.

Long-running recovery, network congestion, large files, node churn, or slow control-plane operations can turn a once-fresh heartbeat into stale evidence.

The recovery boundary should reflect reality when the decision is made.

---

## Adversarially Testing the New Boundary

The new policy was not accepted merely because the source compiled.

A disposable node matrix was created inside the forensic database.

The test represented several possible recovery candidates:

a healthy node with a fresh heartbeat;

an online and qualified node with a stale heartbeat;

an online and qualified node with no heartbeat;

a node whose heartbeat timestamp was in the future;

an offline qualified node;

an online node whose qualification remained pending;

an online node whose qualification had been rejected;

and a node that did not exist at all.

The results matched the intended policy exactly.

The fresh node was eligible.

Every other case was rejected with a specific reason.

The five-minute threshold itself was also tested at the boundary. A heartbeat exactly five minutes old remained eligible, while invalid zero, negative, and non-numeric thresholds were rejected.

Then the test became more historically relevant.

`USA004`, one of the principal destinations involved in the August 16 cascade, was represented as `online` while retaining its real historical `last_seen` timestamp from July 30.

The result was rejection.

Even if persistent state claimed that `USA004` was online, its stale heartbeat prevented it from becoming recovery eligible.

That directly tested the architectural weakness discovered earlier in the day.

The new boundary closed it.

All disposable test data was rolled back after the test.

---

## Testing the Real Failover Path

A policy helper can pass unit-style tests while the real recovery path quietly bypasses it.

So the next test exercised `automatic_failover()` itself.

Inside the forensic database, a disposable failed-primary topology was created. The primary node was given an active primary chunk. A second node was marked online and qualified and was given a replica of that chunk.

Its heartbeat, however, was approximately thirty minutes old.

Under the old recovery rule, this node could appear to be a valid promotion candidate because its persisted state said online and qualified.

Under the new rule, it should be refused.

The eligibility boundary rejected it as stale.

Then actual automatic failover was executed.

The recovery engine found no eligible replica and returned `no_replica_available`.

The original primary storage metadata remained stored. No replacement primary was created. No recovery event was written. No rereplication occurred. The stale candidate itself was not mutated.

This was exactly the fail-closed behavior we wanted.

Bol preferred temporary unavailability over inventing confidence in a stale machine.

For infrastructure, that is the safer failure mode.

---

## When the Test Revealed Another Problem

The stale-replica failover test passed its recovery assertions.

Then its cleanup assertion failed.

The test transaction was rolled back, yet the disposable nodes and storage metadata were still present.

At first this looked like a failure of PostgreSQL rollback.

It was not.

The investigation uncovered another architectural behavior that had been hidden by the service abstraction.

`automatic_failover()` performed its own `self.conn.commit()`.

That meant the test's call into the service had committed not only the failover work but also the disposable topology created earlier on the same database connection.

By the time the outer test attempted rollback, those rows were already durable.

This explained why the supposedly disposable test state survived.

The discovery was important for a much larger reason than test cleanup.

`scan_node_health()` iterates through stale nodes and invokes `automatic_failover()` for each one.

If `automatic_failover()` commits independently, then a multi-node health scan is not one atomic operation.

Imagine three stale nodes.

Recovery of the first node succeeds and commits.

Recovery of the second succeeds and commits.

Recovery of the third throws an unexpected exception.

The scheduler can roll back its current transaction, but it cannot undo the commits already performed by the first two recoveries.

The network may therefore be left in a partially processed scan state.

This was not the failure we started the day looking for.

But once observed, it could not be ignored.

---

## Cleaning the Forensic Test State Carefully

Because the earlier test had unexpectedly committed its disposable data, cleanup was handled with the same caution used throughout the session.

First, the forensic database was backed up again.

Then the exact surviving rows were inspected.

There were two disposable nodes, one primary storage record, one replica record, and zero recovery events.

A guarded cleanup operation verified the database identity before deleting anything. It also verified the exact expected row counts before proceeding.

Only after those conditions matched was the disposable state removed.

A final check confirmed:

zero disposable nodes;

zero disposable storage records;

zero disposable replicas;

and zero disposable recovery events.

The live Bol database remained untouched.

This sequence turned an inconvenient test artifact into another useful engineering lesson:

> A service method's transaction ownership is part of its contract, even when that contract is not visible in the method name.

---

## Auditing Transaction Ownership

The next investigation mapped commit and rollback behavior across the active service layer.

Bol contains a number of service-level commits accumulated over the evolution of the prototype. Many are appropriate because the method represents a complete operation.

The health-scan path was different.

It is a coordinator.

It can perform multiple node-state transitions and multiple failover operations during one scan.

If the coordinator is expected to behave atomically, nested operations must not independently finalize the transaction.

The direct HTTP failover route complicated the situation slightly.

`automatic_failover()` is not called only by the health scanner. It is also exposed as a direct recovery operation.

That meant simply deleting the internal commit would silently change the behavior of existing callers.

The correction therefore preserved both use cases.

`automatic_failover()` gained an explicit transaction-control parameter.

By default, direct calls retain the existing behavior and commit their completed failover operation.

When invoked by `scan_node_health()`, however, it runs with internal commit disabled.

The health scanner then owns the transaction and performs the final commit after the entire scan completes successfully.

This was a small source-code change with a significant semantic effect.

The transaction boundary now follows the orchestration boundary.

---

## Proving the Failure Side of Atomicity

The new transaction contract was tested adversarially inside the forensic database.

Two disposable stale primary nodes were created with valid recovery replicas.

The test then instrumented the recovery path so the first failover could execute normally while the second deliberately raised an exception.

This created the exact situation the architectural change was intended to protect against:

one recovery has already happened inside the transaction;

another recovery fails before the health scan completes.

An independent PostgreSQL connection was then used as the observer.

That detail is critical.

Looking through the same connection would not prove whether mutations had been committed. The independent connection could see only durable database state.

Its observations were clear.

The first primary node was still visible as online.

The original primary storage record was still visible as stored.

The replica was still visible as replicated.

There were zero recovery events.

There was exactly one active primary for the test chunk.

In other words, the first recovery had executed inside the failing scan, but none of it had escaped the transaction.

The failed scan was rolled back.

All disposable state was then removed.

This proved the failure half of the new atomicity contract:

> A health scan that fails partway through recovery must expose none of its partial topology mutation as committed state.

---

## Proving the Success Side of Atomicity

Failure atomicity is only half the requirement.

A successful scan must also make the complete intended result durable.

A second forensic topology was therefore constructed with two stale primary nodes and two fresh, qualified replica nodes.

The real health scanner processed both stale primaries.

It reported two nodes newly marked offline and two failover operations.

This time the scan completed normally.

An independent PostgreSQL connection was again used to inspect durable state.

Both stale primary nodes were committed offline.

Each file had exactly one active primary.

Each recovered chunk had exactly one automatic-failover recovery event.

The active primary for each file had moved to its intended fresh replica node.

There were no duplicate active-primary groups in the test topology.

The complete recovery set was visible together after the scan commit.

All disposable forensic state was then removed.

This proved the success half of the contract:

> A successful health scan commits the complete recovery set as one coordinated operation.

Taken together, the two tests established something much stronger than a compile check or a happy-path demonstration.

A failed health scan produced zero partial committed recovery.

A successful health scan produced the complete committed recovery.

The scheduler's transaction boundary now matches the logical health-scan boundary.

---

## Phase 10 Had Become Recovery Safety Engineering

At the beginning of the day, Phase 10 did not have this shape.

The original intention was to prepare Bol's runtime for continued development after Phase 9.

But infrastructure work has a habit of revealing its real priorities only when systems are exercised as systems rather than as isolated functions.

Today's one-shot scheduler run connected several previously developed capabilities at once:

heartbeat freshness;

node connectivity state;

qualification;

automatic failover;

rereplication;

storage topology;

recovery-event history;

PostgreSQL transaction semantics;

and autonomous scheduling.

The interaction between those components exposed assumptions that individual feature tests had not.

That is exactly why integration testing matters.

The result is that Bol's recovery architecture is now being held to a stronger rule than it was yesterday:

A recovery target must not merely look healthy in persistent metadata.

Its eligibility must be demonstrated using current server-evaluated evidence.

And a health scan must not merely perform a sequence of individually successful mutations.

The scan itself must have a coherent transaction boundary.


---

## What Changed in Bol Today

The most important outcome of August 16 was not a new endpoint.

It was a refinement of what Bol means by trust.

The project has been moving progressively through several layers of trust. Earlier development established node registration, heartbeat, storage placement, replication, failure detection, automatic recovery, qualification, node-specific credentials, authenticated machine identity, and an authorization boundary between authenticated identity and reported qualification evidence.

Phase 10 began connecting those layers more tightly.

The recovery system can no longer treat qualification and a persisted connectivity label as sufficient evidence that a machine is safe to receive recovered data. Recovery now has its own eligibility decision, evaluated from current server-side evidence.

This creates a more useful conceptual model for the infrastructure.

Identity establishes who the machine is.

Qualification establishes whether the machine meets participation requirements.

Freshness establishes whether Bol has recent evidence that the machine is actually present.

Recovery eligibility combines those facts into a decision about whether the machine may participate in topology repair.

The distinction may appear small inside today's prototype.

At network scale it becomes fundamental.

A distributed infrastructure system will eventually encounter machines that disappear without warning, machines behind unstable networks, hosts that restart, nodes whose credentials remain valid after connectivity is lost, devices that become temporarily partitioned, and machines whose persistent state no longer represents physical reality.

The control plane must be able to distinguish those situations without guessing.

Today's work moved Bol closer to that model.

---

## Fail Closed Rather Than Recover Blindly

One principle became particularly clear during the stale-replica adversarial test.

If Bol cannot prove that a recovery destination is currently eligible, it should not move authoritative data there simply because doing so would preserve the appearance of availability.

The test deliberately presented the recovery engine with an attractive but stale candidate.

The node was known.

It was qualified.

Its persistent state said online.

It already held a replica.

But its heartbeat evidence was stale.

Bol refused to promote it.

That means the safer outcome may occasionally be:

`no_replica_available`

rather than an automatic promotion.

This is intentional.

Availability is important, but false confidence in a stale recovery destination can turn an availability problem into a data-integrity problem.

Bol should recover aggressively only when the evidence permits it.

When the evidence does not permit it, the system should fail closed, preserve topology evidence, surface the condition, and wait for a trustworthy recovery path.

That principle will become increasingly important as real Node Agents replace the current single-server simulation.

---

## The Beginning of a Stronger Node Lifecycle

Today's investigation also suggested that Bol's eventual node lifecycle will need to become richer than a simple online/offline flag.

That redesign was deliberately not forced into today's patch.

A future production control plane may need to distinguish states such as healthy participation, suspected connectivity loss, confirmed failure, administrative maintenance, quarantine, recovery eligibility, draining, decommissioning, or other operational conditions.

Those states should not be invented casually.

They need to emerge from concrete control-plane requirements and be tested against real node behavior.

For now, Phase 10 introduces the smaller and more defensible boundary: recovery placement independently verifies fresh heartbeat evidence before trusting a node.

The broader lifecycle remains an architectural question for subsequent work.

This is an important development discipline for Bol.

Discovering a future abstraction does not mean immediately implementing the largest possible version of it.

The current problem should be solved correctly while leaving room for the architecture to mature.

---

## Recovery Policy and Compliance-Aware Infrastructure

Another architectural direction became more relevant during this work.

Bol is being designed with compliance-aware infrastructure as a formal long-term requirement.

That does not mean the current prototype is SOC 2 certified, GDPR compliant, or HIPAA compliant, and no such claim should be made at this stage.

It means those requirements should influence architecture before production rather than being bolted onto the system afterward.

The recovery work performed today intersects directly with that goal.

A future compliant distributed infrastructure cannot treat every qualified node as interchangeable.

Placement and recovery decisions may eventually need to consider node trust class, geographic jurisdiction, customer policy, data residency, workload sensitivity, encryption and key boundaries, retention requirements, administrative state, audit requirements, and the compliance capabilities of the destination infrastructure.

The recovery-eligibility boundary introduced today gives Bol a natural place for those policies to evolve.

Today's rule asks whether the node is online, qualified, and fresh.

A future policy engine may ask considerably more.

For example, a recovery destination might be technically healthy but legally or contractually ineligible to receive a particular customer's data because it resides in the wrong jurisdiction or belongs to the wrong compliance class.

Likewise, recovery itself must eventually generate durable evidence explaining why a placement decision occurred.

The work already present in Bol around recovery events, integrity events, authenticated node identity, qualification assessments, and controlled server-side decisions begins forming the foundation for that future auditability.

Compliance is therefore not being treated as a badge to add later.

It is becoming a constraint on how the infrastructure is designed.

---

## What We Deliberately Did Not Do

Several tempting actions were intentionally avoided today.

The live database was not casually rolled back simply because the August 16 cascade looked alarming.

The health timer was not re-enabled after the new policy passed its first tests.

The API was not restarted merely because server maintenance had completed.

The Phase 10 source was not committed just because individual steps passed.

The operating-system service model was not redesigned while recovery semantics were still under investigation.

Historical test topology was not mass-deleted to make the database appear cleaner.

And Phase 10 was not declared complete.

Each of those actions would have created the appearance of progress.

Instead, the session prioritized understanding.

The live database remained preserved.

The post-scan state remained recoverable from backup.

The forensic clone provided a controlled environment for destructive analysis.

The private Phase 9 checkpoint remained available beneath the uncommitted Phase 10 work.

The scheduler remained disabled.

The API remained stopped.

This leaves the project in a deliberately conservative state at the end of the session.

---

## Where Phase 10 Stands Tonight

Phase 10 is active and unfinished.

The current private source contains uncommitted recovery-safety work built on top of the frozen Phase 9 checkpoint.

The work completed today has established and adversarially tested two important properties.

First, stale persistent connectivity state is no longer sufficient to make a node a recovery destination. Recovery eligibility independently requires fresh server-evaluated heartbeat evidence in addition to online and qualified state.

Second, a scheduler-driven health scan now has a coherent transaction boundary. Nested automatic failovers do not independently commit when participating in a health scan. A failed multi-node scan exposes zero partial recovery commit, while a successful multi-node scan makes the complete recovery set durable.

Those properties have been demonstrated against the isolated forensic PostgreSQL clone.

They have not yet been promoted into a frozen Phase 10 checkpoint.

Before the health timer is enabled again, the next work should examine the boundary between failure detection and authorization to mutate storage topology.

A stale heartbeat currently causes a node to transition toward recovery automatically.

That policy deserves the same scrutiny that recovery-target eligibility received today.

The question for the next session is no longer simply:

"Is this node stale?"

It is:

"When does evidence of node failure become sufficient authority for Bol to begin autonomous topology mutation?"

That distinction may lead toward a more explicit failure-state model, but the architecture will be inspected before such a model is introduced.

---

## Operational State at Session End

The host successfully completed operating-system maintenance and rebooted into the newer installed kernel.

PostgreSQL returned healthy.

The Bol API remained intentionally stopped.

The recurring health timer remained disabled and inactive.

The forensic database remained isolated from the live Bol database.

Disposable Phase 10 test topology was removed after testing.

The private development work remained based on the frozen Phase 9 checkpoint with the Phase 10 recovery-safety changes intentionally uncommitted.

The public repository received no private implementation code during the engineering work described here.

Only this sanitized development journal is intended for publication.

That separation remains important.

Bol's public repository exists to communicate the architecture, development progress, engineering reasoning, and long-term direction of the project.

Private implementation details, credentials, environment configuration, database contents, backups, internal runtime information, and sensitive operational material remain outside the public development history.

---

## Closing Notes

August 16 began with a server asking for a reboot.

It ended with a stronger definition of autonomous trust.

The most valuable moment of the session was not when a test printed `PASS`.

It was when a system that appeared to be behaving correctly forced us to ask whether the rule it was following was actually the rule we wanted.

The health scanner correctly identified stale nodes.

The failover engine correctly followed its candidate-selection logic.

PostgreSQL correctly committed the transactions it was instructed to commit.

Each component could therefore appear correct in isolation while their interaction still produced a result that was wrong for the larger system.

That is one of the central difficulties of distributed infrastructure engineering.

Correct components do not automatically produce a correct system.

The boundaries between them matter.

Today Bol strengthened two of those boundaries.

Recovery placement now requires current evidence of node eligibility.

Scheduler-driven recovery now respects the transaction boundary of the scan that coordinates it.

Neither change makes Bol finished.

Both make its assumptions more explicit.

And that is how this project continues to move forward: not by pretending that each phase permanently solved a problem, but by allowing every new layer of the system to challenge what the previous layer assumed.

The prototype is becoming more demanding of itself.

That is a good sign.

---

**Bol**  
**Building the Future of Internet**

