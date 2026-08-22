# BOL Development Journal — August 22, 2026

## Phase 10 — Hardening the Control Plane Trust Boundary

Today marked the completion and formal freeze of one of the most consequential engineering phases in BOL so far.

Phase 10 began with what appeared to be a relatively focused problem: determining whether the recovery system could safely trust a node merely because its persisted database status said that it was online. As the investigation progressed, however, that question exposed a much larger architectural issue. Connectivity, liveness, qualification, placement eligibility, recovery eligibility, administrative authority, and historical node state were related concepts, but they were not yet separated strongly enough at the control-plane boundary.

Rather than applying a narrow fix to automatic failover, the work expanded into a systematic examination of who or what is allowed to establish truth inside BOL.

The central principle that emerged was simple:

**A node may report observations, but the BOL control plane must determine authoritative operational state.**

That principle ultimately affected registration, heartbeat processing, node health detection, storage placement, replica placement, recovery selection, administrative controls, transaction ownership, and operational reporting.

By the end of the phase, these areas were no longer relying on scattered interpretations of whether a node appeared usable. They were connected through explicit policy boundaries owned by the control plane.

This was not a refactoring exercise for cleanliness. It was a trust-model correction.

## Beginning With Recovery Safety

The initial focus was recovery eligibility.

A node participating in recovery cannot be considered safe merely because an old database record still says `online`. In a distributed system, persisted connectivity state can become stale. A machine may disappear from the network while its last recorded status remains unchanged.

Recovery therefore needed stronger evidence.

A dedicated recovery eligibility boundary was introduced so that a candidate must satisfy several independent conditions before receiving or being promoted to recovery data. The node must exist, must currently have the required operational state, must satisfy BOL qualification requirements, must possess actual heartbeat evidence, and that evidence must be recent enough to fall inside the server-controlled freshness threshold.

A timestamp from the future is rejected as invalid evidence. A missing heartbeat is not treated as proof of health. A stale heartbeat cannot be rescued by an `online` database value.

Most importantly, eligibility is evaluated at the time the recovery decision is made. Recovery does not freeze a single freshness observation and continue trusting it indefinitely while processing subsequent decisions.

This established an important distinction that would influence the rest of Phase 10:

**persisted state is historical information; eligibility is a current control-plane decision.**

## Proving the Recovery Boundary Under Adversarial Conditions

Once the recovery eligibility boundary existed, it was not accepted simply because the implementation compiled or appeared logically correct. Phase 10 deliberately tested the boundary against conditions that could fool a weaker distributed system.

A disposable forensic test matrix was created containing fresh nodes, stale nodes, nodes without heartbeat history, nodes carrying timestamps in the future, offline nodes, pending nodes, rejected nodes, and nonexistent identities.

The results established the intended policy behavior consistently. A fresh, qualified and online node with recent heartbeat evidence was eligible. Stale heartbeat evidence was rejected. Missing heartbeat evidence was rejected. Future timestamps were rejected. Offline nodes were rejected. Nodes outside the qualified state were rejected. Unknown nodes were rejected.

The exact freshness boundary was tested as well. A node exactly at the configured threshold remained eligible, while evidence beyond that threshold became stale.

One particularly important adversarial test used historical node state. The test deliberately represented a node as online even though its heartbeat evidence was old. The recovery boundary still rejected it.

That proved the property Phase 10 was designed to establish:

**changing persisted status cannot manufacture fresh liveness.**

The actual automatic failover path was then exercised against a stale-but-online replica. The replica looked acceptable under the older model because its status and qualification fields appeared valid. Under the new policy, however, its heartbeat age made it ineligible.

Automatic failover correctly refused to promote it.

No replacement primary was created, no recovery event falsely claimed success, and no re-replication occurred through the stale candidate. The topology remained intact rather than forcing recovery through an untrusted node.

This was an important shift in BOL's failure philosophy. When sufficient trustworthy infrastructure is unavailable, the system should fail safely rather than manufacture availability.

## Discovering a Transaction Ownership Problem

That adversarial failover test exposed another issue that was initially unrelated to freshness.

The test attempted to roll back its disposable database state after exercising automatic recovery. Some of that state unexpectedly survived.

The cause was not the recovery eligibility policy. The deeper issue was transaction ownership.

Automatic failover contained its own database commit. That behavior made sense when failover was invoked independently, but automatic failover could also be invoked from the broader node health scan.

This created a dangerous composition problem.

A health scan may evaluate several stale nodes as one logical operation. If each nested failover commits independently, then a later failure in the same scan can leave earlier recovery mutations permanently committed. The caller can no longer roll back the complete operation.

In other words, a single logical health scan could become partially committed.

For infrastructure recovery, that is an unacceptable ambiguity.

Phase 10 therefore introduced explicit transaction ownership. Automatic failover can still own its transaction when invoked independently, but when invoked as part of a health scan it suppresses its internal commit. The outer health scan becomes responsible for committing the complete recovery set.

This preserved both use cases without introducing a broad transaction refactor.

## Proving Atomic Recovery

The new transaction contract was tested in both failure and success directions.

First, an intentional failure was injected partway through a health scan involving multiple recovery operations. An independent database connection was then used to inspect what another observer could actually see.

It saw none of the partial recovery work.

The failed scan was rolled back, and no partial topology transition survived.

A second test exercised the successful case. Multiple stale nodes were processed in one health scan, their recovery operations completed, and the outer transaction committed.

An independent observer then saw the entire completed recovery set together: failed nodes transitioned offline, replacement primaries existed, recovery events were present, and each affected chunk had the expected active-primary topology.

These tests established a stronger transactional invariant for BOL:

**a health scan either exposes the complete successful recovery set or exposes none of its uncommitted intermediate recovery work.**

This was one of the most important discoveries of the phase because it moved recovery safety beyond individual SQL statements and into the behavior of the operation as a whole.

## Establishing Who Is Allowed to Say a Node Is Online

Recovery hardening led directly to a more fundamental question: where does BOL's belief that a node is online actually come from?

Historically, several paths could influence connectivity state. Registration accepted a status supplied by the caller. Heartbeats also carried a status value. Administrative recovery methods could mark a node online and simultaneously refresh its heartbeat timestamp.

Those behaviors were convenient during the early prototype, but they blurred an important security boundary.

A node should be allowed to communicate facts and observations about itself. It should not be allowed to determine the control plane's authoritative interpretation of those observations.

The heartbeat path was therefore hardened.

Node identity continues to come from the node-specific credential established in the authenticated identity work completed during earlier phases. Once that credential has been successfully authenticated, the receipt of that authenticated request itself becomes the evidence of contact.

The caller no longer supplies an authoritative heartbeat status.

Instead, BOL derives the operational state from what the server actually observed:

**an authenticated heartbeat means the control plane successfully communicated with that authenticated node at that moment.**

The server records the heartbeat time and derives the node's online state itself.

Adversarial testing then attempted to inject values such as `offline`, `failed`, `qualified`, `rejected`, and even meaningless status values through the old interface. Those attempts could no longer mutate node state because caller-supplied heartbeat status had been removed from the authoritative service contract.

This tightened the relationship between identity and liveness:

**credentials establish which node is communicating; successful authenticated communication establishes current liveness.**

## Registration Is Not Liveness

The same principle exposed another subtle problem in node registration.

Previously, registering a node could write an online status and populate `last_seen`. That effectively allowed registration to manufacture evidence that a node had been observed alive even though no authenticated heartbeat had occurred.

Phase 10 separated these concepts.

Registration now establishes the existence and descriptive metadata of a node. It does not establish current liveness.

A newly registered node begins offline and without heartbeat evidence. Re-registering an existing node may refresh appropriate descriptive metadata, but it does not overwrite the authoritative connectivity state or manufacture a new heartbeat timestamp.

The lifecycle was then tested from beginning to end.

A node attempted to register while claiming to be online. BOL still created it offline with no `last_seen` value.

The health scanner was then run against that never-observed node. This uncovered another important semantic distinction: missing heartbeat evidence is not the same thing as stale heartbeat evidence.

A node that has never successfully contacted BOL has not necessarily failed after previously being healthy. It simply has no liveness history yet.

The scanner therefore does not interpret a null heartbeat timestamp as proof of a failure event.

After the same node successfully sent an authenticated heartbeat, BOL changed its state to online and recorded the server-observed heartbeat timestamp. That real heartbeat evidence was then artificially aged during forensic testing. Once it exceeded the freshness threshold, the health scanner correctly identified the node as stale and transitioned it offline.

The resulting lifecycle became explicit:

**registration creates identity and metadata.**

**authenticated heartbeat creates liveness evidence.**

**fresh heartbeat evidence supports online participation.**

**observed heartbeat evidence that later becomes stale can support failure detection.**

**absence of any heartbeat history does not fabricate a failure event.**

This distinction gives the control plane a much cleaner understanding of what it actually knows about a node.

## Administrative Authority Has Limits

Phase 10 also examined what an administrator should be allowed to do to connectivity state.

The resulting policy intentionally became asymmetric.

An administrator may force a node offline.

This is necessary for incident response, maintenance, security intervention, suspected compromise, policy enforcement, or other situations where BOL needs to stop trusting a device immediately.

But an administrator cannot manufacture evidence that a machine is currently alive.

Manual online and recovery operations therefore no longer create authoritative online state or rewrite `last_seen` as though the node had contacted the control plane.

If an administrator attempts to return an offline node to service, BOL requires the node itself to re-establish authenticated contact.

The node must prove liveness by communicating again.

Testing confirmed that manual online and recovery attempts left both the offline state and the historical heartbeat timestamp unchanged. An authenticated heartbeat subsequently restored online state and created a new server-observed liveness timestamp.

Administrative offline operations were also changed to preserve the previous heartbeat evidence rather than rewriting history with the time an administrator happened to disable the node.

That preserves an important forensic distinction:

`last_seen` means when BOL last observed authenticated node contact.

It does not mean when an administrator changed a status field.

The resulting authority model is deliberately constrained:

**administrators may reduce trust, but they cannot manufacture evidence required to increase trust.**

This principle will remain important as BOL evolves toward stronger operator controls, compliance policies, automated security responses, and eventually a much larger global node population.

## From Recovery Eligibility to a Common Participation Policy

As the liveness model became clearer, another architectural pattern emerged.

Recovery was not the only operation that needed to know whether a node was trustworthy enough to participate. New storage placement, replica placement, and future infrastructure workloads all need to answer variations of the same underlying question.

Rather than allowing each subsystem to independently interpret `status`, qualification state, and heartbeat freshness, Phase 10 introduced a common node participation eligibility boundary.

This policy owns the shared trust requirements.

A participating node must exist, be in the required BOL-controlled operational state, satisfy qualification requirements, possess real heartbeat evidence, and have heartbeat evidence that is sufficiently fresh. Missing, stale, or future-dated heartbeat evidence causes the node to fail the boundary.

Recovery eligibility then became a domain-specific wrapper around this common policy.

A separate placement eligibility boundary was introduced in the same way.

Today, placement and recovery inherit the same fundamental participation requirements. Keeping them as separate domain boundaries is intentional, however. In the future, storage placement may require additional constraints such as available capacity, geography, compliance class, data-residency policy, hardware capability, customer policy, node reputation, or workload-specific requirements. Recovery may develop a different set of additional restrictions.

The architecture therefore became:

**common participation policy → domain-specific placement or recovery policy → deterministic infrastructure decision.**

This avoids duplicating trust logic while leaving room for the domains to evolve independently.

## Trust Must Gate Ranking

The first placement method migrated to the new boundary was best-node selection.

Previously, candidate selection relied primarily on persisted online and qualification state before ranking nodes according to storage capacity. Under the hardened model, ranking cannot make a node trustworthy.

Trust must be established first.

Only nodes passing authoritative placement eligibility are allowed into the population from which capacity ranking chooses a winner.

This distinction was tested adversarially by constructing nodes with very high available storage that were intentionally stale, pending qualification, or offline. Fresh qualified nodes were given less attractive capacity values.

The higher-capacity untrusted nodes were skipped.

Among the remaining eligible population, the existing ranking semantics were preserved. Available storage remained the primary preference, and the existing used-storage tie-breaking behavior remained intact.

This established a simple but important rule:

**trust gates optimization. Optimization never overrides trust.**

A stale machine does not become a valid storage target simply because it has more disk space.

## Replica Selection Follows the Same Rule

Replica selection was migrated next.

This required additional care because the selector accepts a requested replica count. Applying a database limit before evaluating eligibility could accidentally allow stale high-ranked candidates to consume the candidate window, preventing lower-ranked trustworthy nodes from being considered.

Phase 10 therefore changed the order of operations.

Candidates are considered in the existing deterministic capacity order. The primary node is excluded. Each remaining candidate independently passes through placement eligibility. Eligible nodes are accumulated until the requested replica count is satisfied.

If insufficient trusted capacity exists, the selector returns only the trustworthy nodes that actually qualify.

It does not weaken the policy merely to satisfy a requested replication factor.

Adversarial testing placed stale, pending, and offline nodes ahead of fresh nodes in the capacity ranking. The selector correctly skipped them and continued searching until lower-ranked eligible nodes filled the requested replica count.

The primary node was also confirmed to be excluded from its own replica population.

When only one eligible replica target existed, only one was returned even when more were requested. When none existed, the result was an empty trusted candidate set.

Again, availability was not fabricated.

**replica count is a goal; trust is a boundary.**

## Hardening Canonical Primary Distribution

The same eligibility boundary was then carried into BOL's canonical physical-chunk distribution path.

Before modifying that path, the actual database schema was inspected rather than relying on older table-creation code still present from earlier prototype generations. This revealed that the live physical-chunk model had evolved beyond some historical assumptions.

The test fixture was corrected to match the real schema before validation continued.

This was a useful reminder of an engineering rule that became increasingly important during Phase 10:

**the running architecture and validated database contract are authoritative; historical prototype code is evidence of evolution, not necessarily the current design.**

With a schema-correct fixture, physical chunk distribution was tested against an adversarial node population.

A stale node was deliberately placed early in deterministic node ordering. Pending and offline nodes were also present. Only two fresh qualified nodes were eligible.

Five physical chunks were then distributed.

The stale, pending, and offline nodes received no primary chunks. The two trustworthy nodes received the chunks using the exact existing round-robin behavior.

The resulting sequence alternated deterministically across the eligible population while preserving the original placement semantics.

An independent database connection confirmed that the topology returned by the service was the topology actually committed to storage metadata.

The test then removed all eligible candidates and repeated the operation. Distribution failed safely before writing any placement records.

This proved that the new trust boundary had been inserted without rewriting the distribution algorithm itself:

**eligibility determines who may participate; the existing placement policy determines how work is distributed among those trusted participants.**

## Hardening Canonical Replica Creation

The distributed replica creation path was then tested end-to-end.

A primary chunk was created together with an adversarial node population containing stale high-capacity nodes, unqualified high-capacity nodes, and fresh qualified nodes with lower capacity.

Replica creation delegated candidate selection to the hardened replica selector.

The stale and unqualified high-capacity nodes were rejected. The primary was excluded. Fresh eligible nodes were selected in the existing capacity-preference order.

An independent observer confirmed that the expected replica records were actually committed.

Storage accounting was also verified.

Only nodes that genuinely received replicas consumed storage capacity. Rejected candidates retained their original accounting values.

Finally, the eligible replica population was reduced to zero. No replica metadata was persisted.

The system reported that no replica target was available rather than silently selecting an untrusted machine.

By this point, both sides of new distributed storage placement were operating under the same control-plane trust model:

**new primary placement requires authoritative eligibility.**

**new replica placement requires authoritative eligibility.**

**recovery placement requires authoritative eligibility.**

The control plane was no longer applying freshness only after something failed. Freshness had become part of deciding where new responsibility could be assigned in the first place.

## Discovering BOL's Architectural Generations

Phase 10 also became an exercise in architectural archaeology.

As placement paths were audited, it became clear that the current codebase still contains several generations of BOL's evolution. Earlier abstractions had not necessarily been deleted when newer distributed models replaced them.

This was important because blindly applying the new eligibility policy everywhere would have mixed historical prototype paths with the canonical architecture and expanded the blast radius without improving the system that BOL actually depends on today.

The older placement path operates through the original `chunks` and `chunk_locations` model.

Database evidence showed that this model represents only a small historical population. Its activity belongs to an earlier stage of development, while the newer distributed storage model continued growing substantially afterward.

The old placement method was also reachable only through its dedicated endpoint. Modern distributed workflows did not internally depend on it.

The newer architecture instead follows the physical-chunk model into distributed storage metadata.

The evidence therefore supported a formal distinction:

**Legacy Placement V1 is preserved as historical prototype behavior.**

**Distributed physical-chunk placement is the canonical architecture being hardened going forward.**

This distinction prevented Phase 10 from becoming an unnecessary rewrite of every historical experiment that still exists in the repository.

## Replica Architecture Had Evolved the Same Way

The replica audit revealed a similar progression.

One early generation represented replicas at the whole-file level. Another generation used the older chunk-location model. The current architecture instead represents replicas at the distributed physical-chunk level.

The historical database populations reinforced this interpretation. Earlier replica tables contained relatively small populations associated with earlier development periods. The distributed replica model had become substantially more prominent and, more importantly, was the model consumed by current failover and recovery logic.

The resulting conceptual progression became:

**early file replicas → legacy chunk replication → canonical distributed chunk replicas.**

Rather than migrating every generation to the new placement policy, Phase 10 deliberately preserved the earlier systems unchanged.

The canonical distributed replica path received the hardening.

This was not technical debt being ignored. It was scope discipline.

Historical structures remain useful because they document how the architecture evolved and may still help during later cleanup or migration work. But they should not silently dictate the security model of the current system.

The rule adopted during this phase was therefore:

**preserve legacy behavior until it is intentionally retired; apply new architectural guarantees to the canonical path rather than accidentally redesigning history.**

## Finding a Reporting Error During Replica Validation

End-to-end testing of distributed replica creation uncovered another subtle issue.

The actual placement behavior was correct. When trusted replica nodes were available, replica records were created and storage accounting was updated appropriately. When no trusted replica nodes were available, no replica metadata was persisted.

However, the response contract contained a misleading count.

The method maintained a collection of placement outcomes. Successful replica records were added to that collection, but failed placement outcomes were added to the same collection as well.

The response then reported the size of that collection as `replicas_created`.

This meant a failed placement decision could increase a field whose name claimed that a replica had actually been created.

The database remained correct, but the reporting semantics did not accurately describe database reality.

That distinction matters.

Operational metrics eventually feed dashboards, alerts, capacity planning, customer reporting, audit evidence, automated analysis, and the future BOL Intelligence layer. A misleading count at the service boundary can propagate incorrect assumptions throughout every system built above it.

Phase 10 therefore corrected the result contract without changing the placement algorithm.

The response now separates three concepts.

`replica_count_requested` describes the desired replication policy.

`replicas_created` describes replicas that were actually created.

`placement_failures` describes placement decisions that could not produce a replica.

A separate outcome count describes the total number of placement outcomes represented in the response.

The existing detailed outcome records were preserved so callers can still inspect exactly what happened.

## Proving That Reporting Matches Reality

The corrected contract was then tested against both successful and zero-capacity conditions.

In the successful case, two replicas were requested and two trustworthy replica targets were available.

The service reported two replicas created, zero placement failures, and two total outcomes.

An independent database connection counted the persisted replica records.

The count was exactly two.

The test then removed all eligible replica capacity and repeated the operation.

The service still processed the placement decision successfully as an operation, but now correctly reported zero replicas created, one placement failure for the affected primary chunk, and one total outcome.

An independent database observer confirmed that zero replica records existed.

The accounting invariant was then explicitly validated:

**total replica outcomes = replicas actually created + failed placement outcomes.**

This may appear like a small reporting correction compared with the broader trust work in Phase 10, but it establishes an important principle for the system:

**BOL's control plane should report what actually happened, not merely what it attempted to do.**

That principle will become increasingly important as the network grows and as automated analytics begin reasoning over operational history.

## The Final Integration Audit

Before Phase 10 was allowed to become a permanent checkpoint, the complete change set was subjected to a final integration and authority-surface audit.

This was intentionally broader than another functional test.

The purpose was to answer a more important question:

**Had BOL developed one coherent trust model, or had Phase 10 merely fixed several individual functions?**

The audit began by verifying the historical baseline. Phase 10 remained a direct development delta from the frozen Phase 9 authenticated qualification identity boundary.

During this verification, an apparent discrepancy appeared between the Phase 9 tag identifier and the Phase 9 commit identifier.

Rather than modifying Git history, moving the tag, or assuming corruption, the tag itself was inspected.

The investigation confirmed that Phase 9 used an annotated Git tag. The tag object therefore had its own Git object identifier while correctly pointing to the expected Phase 9 commit.

The correct comparison was the commit obtained by peeling the annotated tag, not the tag object's own identifier.

Once this distinction was accounted for, the Phase 9 baseline matched exactly.

This was a small Git detail, but an important example of the discipline used throughout the phase: when evidence appears inconsistent, inspect the underlying mechanism before changing state.

## Reviewing the Complete Authority Surface

The final audit then classified every remaining place in active source where persisted online state was directly queried.

The remaining decision paths fell into two intentional categories.

Several belonged to preserved legacy allocation, placement, and replication generations. These were already classified as historical prototype paths and were deliberately left unchanged.

The remaining uses were reporting functions that count online and offline nodes for system summaries. These functions observe persisted state but do not grant storage responsibility, select recovery targets, establish liveness, or mutate topology.

No remaining canonical primary placement, replica placement, or recovery decision was found bypassing the authoritative eligibility boundaries.

The node mutation surface was reviewed separately.

Registration owns creation and descriptive metadata but does not manufacture liveness.

Authenticated heartbeat owns the normal transition to online state and the creation of server-observed heartbeat evidence.

Administrative operations may force a node offline but cannot manufacture online state or a fresh heartbeat.

Qualification processing modifies qualification state without owning connectivity.

The health scanner may transition a previously observed stale node offline.

Automatic failover may transition a failed node offline while performing recovery.

Startup compatibility logic remains limited to qualification-related schema and state migration rather than connectivity authority.

This gave Phase 10 a clear separation of responsibility between identity, qualification, liveness, administration, placement, recovery, and reporting.

## Final Database and Operational Safety Checks

The forensic environment was inspected one final time before the freeze.

Disposable Phase 10 test nodes had been completely removed.

Disposable distributed storage records were absent.

Disposable distributed replica records were absent.

Disposable storage-accounting records were absent.

No duplicate active-primary groups remained from the testing performed during the phase.

The preserved forensic evidence used during the investigation remained intact.

The operational environment was also deliberately kept frozen throughout the work. Automated health scanning remained disabled, and the live API was not restarted while the recovery and trust boundaries were being changed.

This allowed Phase 10 to be developed and validated without allowing partially tested logic to begin making autonomous infrastructure decisions.

## Freezing Phase 10

Once the authority audit, compile checks, diff hygiene, forensic cleanup, transaction tests, placement tests, recovery tests, and reporting tests had all passed, the phase was ready to become an immutable development milestone.

A final source backup was created immediately before the checkpoint.

Only the three files intentionally modified by Phase 10 were staged.

The staged diff was checked independently to ensure that no unrelated file had entered the milestone.

The complete Phase 10 delta consisted of changes to the application boundary, node control-plane service, and file/distributed-storage service.

The final private commit was created with the message:

**Phase 10: harden control-plane trust and recovery boundaries**

The commit was verified to descend directly from the frozen Phase 9 commit.

An annotated milestone tag was then created:

**`phase10-control-plane-trust-recovery-hardened`**

The tag was independently verified to resolve to the new Phase 10 commit.

The private development worktree was clean after the freeze.

No private Phase 10 source was published as part of this checkpoint.

## What Phase 10 Ultimately Became

Phase 10 began as an investigation into stale recovery candidates.

It ended as a much broader hardening of BOL's control-plane authority model.

The system now has a stronger answer to several fundamental questions.

Who determines whether a node is alive?

**The BOL control plane, based on authenticated contact.**

Can registration claim that a machine is online?

**No. Registration establishes a node record, not liveness.**

Can a stale database status make a node trustworthy?

**No. Current eligibility requires current evidence.**

Can an administrator manufacture liveness?

**No. Administrative authority can reduce trust by forcing a node offline, but authenticated node contact is required to restore authoritative online state.**

Can a high-capacity stale node win storage placement?

**No. Trust gates ranking.**

Can replication requirements override eligibility?

**No. Insufficient trustworthy capacity fails safe.**

Can recovery promote a stale replica merely because its persisted state appears valid?

**No. Recovery candidates independently pass the recovery eligibility boundary.**

Can one failed health scan leave half of a multi-node recovery operation committed?

**The health-scan recovery transaction is now owned atomically by the outer operation.**

Can operational reporting claim replicas were created when no corresponding replica exists?

**The distributed replica result contract now separates requested work, successful creation, failed placement outcomes, and total outcomes.**

These are not isolated endpoint behaviors. Together they form a control-plane philosophy.

## A Stronger Foundation for Future BOL Infrastructure

The significance of this work extends beyond today's storage prototype.

Future BOL infrastructure may contain nodes distributed across countries, networks, hardware classes, operators, compliance jurisdictions, and workload types. Storage placement may eventually consider data residency, node reputation, customer policy, encryption requirements, hardware capability, network quality, geographic diversity, cost, and regulatory restrictions.

Recovery may eventually operate across enormous numbers of chunks and nodes.

Compute and AI workloads may require even stronger participation requirements.

Those systems cannot safely be built on the assumption that a database row saying `online` is sufficient proof that infrastructure should receive responsibility.

Phase 10 established the beginning of a policy architecture capable of growing with those requirements.

The common participation boundary defines shared trust.

Placement and recovery wrap that common boundary so they can become independently stricter over time.

Deterministic infrastructure services execute the resulting decisions.

Historical architectures remain preserved until intentionally retired rather than being silently mixed with current policy.

And the intelligence layer planned for BOL will remain above these deterministic controls: it may analyze the resulting evidence, explain behavior, visualize topology, identify anomalies, forecast conditions, and recommend actions, but it will not bypass these boundaries or directly mutate infrastructure state.

The standing rule remains:

**AI can only advise and never mutate data.**

## Closing Phase 10

Phase 10 required considerably more investigation than originally expected.

Several of its most valuable improvements were not the changes initially being searched for. Transaction ownership emerged while testing rollback behavior. The distinction between never-observed and stale nodes emerged while examining registration. Administrative authority became clearer while tracing liveness writers. Legacy architecture generations became visible while auditing placement. Replica reporting semantics were corrected because adversarial testing compared service responses against independently observed database reality.

That is precisely why this phase was allowed to expand carefully rather than being rushed toward a predetermined endpoint.

The final result is not simply more code.

It is a clearer definition of what BOL believes, what evidence it trusts, which component is allowed to establish that truth, and what the system must do when trustworthy evidence is unavailable.

Phase 10 is now frozen.

The next development session will begin from this validated checkpoint rather than continuing immediately into another architectural change. Phase 11 will therefore start on top of a clean, tagged control-plane trust foundation, with the lessons and boundaries established here treated as part of BOL's architecture rather than temporary implementation details.

For a distributed infrastructure network, that distinction matters.

Before BOL can safely decide where the world's data should live, it must first be able to answer a more fundamental question:

**Which machines should it trust with that responsibility?**

Phase 10 made that answer substantially stronger.
