# Phase 14C — Remote Possession Measurement

Phase 14C has moved from measurement design into controlled remote validation.

The governing rules remain:

> Nodes report evidence; BOL derives authoritative state.

> AI may advise, but it does not mutate authoritative BOL state.

## Independent remote possession measurement

BOL completed a controlled possession challenge against an independently operated development node.

The control plane issued a bounded, single-use challenge for an enrolled physical copy. The authenticated Node Agent returned the requested object through the reviewed read-back protocol. BOL independently measured the returned byte count, computed the checksum, and accepted the result.

The important distinction is that the node did not declare possession. It supplied evidence; BOL evaluated that evidence and recorded the authoritative outcome.

The retained measurement showed:

- the expected object size was returned;
- BOL's independently computed checksum matched;
- the possession challenge was accepted;
- no measurement sequence gaps or known diagnostic drops were observed;
- the coordinator completed bounded shutdown and retained a sanitized measurement export.

The measurement export deliberately remains partial for timing dimensions that cannot be isolated reliably with the current instrumentation. BOL does not convert missing telemetry into invented precision.

## Historical proof is not current assurance

The accepted challenge now establishes historical possession evidence for the tested copy.

It does **not** automatically become current qualifying durability evidence.

Possession freshness policy remains deliberately unconfigured. No arbitrary proof lifetime was introduced simply because a challenge succeeded. Until a reviewed freshness policy exists, BOL continues to distinguish:

- an accepted historical possession proof;
- current qualifying possession assurance;
- and durability conclusions derived from qualifying copies.

This is intentional fail-closed behavior.

## Explicit reconciliation and acknowledgment

Campaign measurement state is finite and operator-gated.

After the accepted result, the exact challenge was reconciled against canonical state, independently reviewed, explicitly acknowledged, and cleanly closed. The completed slot cannot be silently replayed to manufacture newer evidence.

Later measurement slots remain separate approval boundaries.

## Quiet-period evidence

The next experiment requires an undisturbed observation interval before subsequent measurements.

A previously certified observer was reviewed against the stricter evidence claim required for this experiment. That review identified remaining visibility gaps around short-lived processes and sockets, pre-existing descriptors or mappings, namespace scope, and access mechanisms not completely covered by sampled process/network inspection plus inotify.

BOL therefore did not weaken the claim merely to continue the experiment.

The quiet interval has not started. The next engineering task is to strengthen and separately certify the observer before it is deployed.

## What this milestone establishes

This checkpoint demonstrates an end-to-end development path in which:

**authorized copy → bounded challenge → authenticated remote read-back → independent byte/checksum verification → authoritative accepted evidence → explicit reconciliation**

It does not establish production durability, continuous possession, automated renewal, repair, or a final freshness interval.

Those remain separate engineering milestones.

## Next

Phase 14C continues with:

1. strengthened quiet-period observation and certification;
2. a controlled undisturbed measurement interval;
3. later separately approved possession measurements;
4. measurement analysis across timing, failures and uncertainty;
5. only then, an explicitly reviewed possession-freshness policy.

No proof lifetime is selected by this checkpoint.
