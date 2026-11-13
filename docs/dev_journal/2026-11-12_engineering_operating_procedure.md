# BOL Engineering Operating Procedure

Engineering checkpoint: 2026-11-12.

## Purpose

BOL now has a permanent engineering operating procedure governing how substantial
engineering sessions begin, progress, preserve evidence, close checkpoints, and
synchronize sanitized public progress.

The procedure was created after repeated engineering work showed that technical
correctness alone is not enough: repository identity, handoff continuity,
promotion gates, live-operation authority, preservation, and publication must
remain deterministic across sessions and execution environments.

## Core operating rule

**Established BOL procedure outranks new improvisation.**

When remembered procedure, repository state, and observed evidence disagree,
engineering stops and reconciles the accepted handoff and authoritative
checkpoint before continuing.

A failed or unavailable checkout, tool, workspace, authentication route, or
execution path does not invalidate the established procedure. The execution path
is recovered rather than replacing the workflow for convenience.

## Session start

Substantial BOL engineering sessions now begin by recovering the most recent
accepted handoff and establishing the authoritative repository/worktree,
execution environment, branch or detached state, full Git checkpoint, working
state, Git metadata/object location, applicable preservation evidence, intended
engineering boundary, and authorization limits.

Memory alone is not sufficient to fill missing checkpoint information.

## Engineering progression

The operating procedure formalizes the established progression from bounded
design and implementation through focused testing, adversarial review,
correction, full regression, exact candidate identity, disposable reproduction,
authoritative promotion, post-commit verification, complete-history preservation,
and independent transfer verification.

A blocker returns work to correction and re-review. Focused tests do not replace
full promotion regression, and pre-commit results do not replace required
post-commit evidence.

## Live-operation discipline

Live work remains separately controlled.

Historical approval does not authorize a new live operation. Mutation authority
and verification authority remain distinct. Authorized operations remain bounded,
with explicit stop conditions, complete outcome framing, no automatic retry or
repair, and separate verification where the architecture requires it.

A successful mutation receipt is not automatically independent verification.

## Failure and uncertainty

The procedure preserves explicit distinctions between unknown, absent, mismatch,
and failure states. Missing output or interrupted execution is not interpreted as
success.

Partial evidence is preserved rather than rewritten to create an artificial
continuous success history.

## Private and public closeout

Engineering completion alone no longer means a BOL checkpoint is fully closed.

The established closeout progression is:

**engineering checkpoint → private handoff/closeout → README current-state update
where appropriate → existing public progress journal → sanitized public
documentation branch from verified public base → outgoing-history/privacy review
→ pull request → merge → verification of public main**

README represents current public state. The existing development journal
preserves chronological engineering history.

Public documentation branches must originate from the verified public base and
must not inherit private-development history.

## Tool authority

Codex, Context7, and Serena are advisory productivity tools.

Context7 supports current external library/API documentation. Serena supports
semantic navigation of BOL source symbols, definitions, and references. Neither
tool establishes BOL runtime truth.

Git remains authoritative for committed engineering history. BOL-derived
deterministic evidence remains authoritative for BOL runtime state within the
scope it demonstrates.

## What this checkpoint changes

This checkpoint changes BOL engineering process and documentation only.

It does not change BOL runtime behavior, deployment state, credential state,
database state, durability conclusions, or production readiness.

The goal is procedural continuity: future engineering sessions should be able to
recover where BOL is, why it is there, what evidence supports that state, and
what exact boundary comes next without reconstructing the workflow from memory.

## Current state

The operating procedure has been accepted into the authoritative private
engineering line and preserved through the established complete-history custody
process.

Public synchronization of this process milestone is the remaining closeout step.

## November 13 private closeout

The engineering operating procedure documentation closeout was committed to the
authoritative private engineering branch, `private-development`.

- Private closeout commit: `6f48648675cf5904bf5e1711cd097209cff58f5c`
- Parent: `66743c5c0cffeea19b1079a420ddc56c78cfa6f4`
- Focused file: `docs/engineering-operating-procedure-closeout.md`
- Working tree: clean at the reported closeout checkpoint

This was a documentation closeout only. It did not authorize or establish new
runtime behavior, live operations, credential handling, database changes,
durability conclusions or production readiness.

Public synchronization remains subject to sanitized documentation review,
outgoing-history/privacy review, pull-request merge and verification of
GitHub `main`. Private engineering history is not transferred to the public
documentation branch.
