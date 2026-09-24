# BOL Architecture

<p align="center">
  <img src="bol-overview.png" width="100%">
</p>

## Current Architecture

```text
                    Client
                       │
                 Upload File
                       │
              BOL Control Node
                       │
        ┌──────────────┼──────────────┐
        │              │              │
     Storage A      Storage B      Storage C
        │              │              │
    Chunk 1        Chunk 2        Chunk 3
        │              │              │
    Replica        Replica        Replica
```

---

## Possession milestone and roadmap

BOL has completed a controlled real remote possession challenge over verified HTTPS. The authenticated, database-free Node Agent supplied a synthetic 1-KiB object; BOL measured 1,024 bytes, computed SHA-256 and accepted the response within the server-issued window. This establishes historical assurance, not continuous storage or local-disk residency.

Proof lifetime remains NULL/unconfigured. Current qualifying durability remains zero and unproven; automated renewal and recovery remain future work. [Read the September 23 journal](dev_journal/2026-09-23_phase14c_real_remote_possession.md).

**Storage → verified possession → freshness/durability → automated recovery → vendor-neutral/cloud-agnostic interoperability → CDN → compute → AI infrastructure**

The future interoperability direction includes AWS, Azure, GCP, on-premises and BOL-native infrastructure. S3 compatibility is one planned interface, not the platform's identity. These are roadmap goals, not claims of delivered integrations. The vision diagrams below remain long-term context; they do not imply completed freshness, automatic recovery or authoritative AI control.

## Future Vision

```text
                Applications
                     │
                     ▼
              BOL Infrastructure
                     │
     ┌───────────────┼────────────────┐
     │               │                │
 Distributed      Edge CDN      Distributed Compute
   Storage                            │
                                      ▼
                               AI Infrastructure

```
                Client

                  │

          Upload File

                  │

         BOL Control Node

      ┌────────┼────────┐
      │        │        │
   Node A   Node B   Node C
      │        │        │
    Chunk1   Chunk2   Chunk3
      │        │        │
   Replica   Replica   Replica

```
	Storage
   	   │
   	   ▼
	  CDN
  	   │
   	   ▼
   Distributed Compute
   	   │
   	   ▼
    AI Infrastructure
```
BOL

        ┌─────────────────────────┐
        │ Public Open Source      │
        │-------------------------│
        │ Node Software           │
        │ SDK                     │
        │ CLI                     │
        │ Documentation           │
        │ Protocol                │
        └─────────────────────────┘

                 ▲

        Community Contributions

                 ▼

        ┌─────────────────────────┐
        │ BOL Private             │
        │-------------------------│
        │ Enterprise Platform     │
        │ AI Scheduling           │
        │ Internal Infrastructure │
        │ Operations              │
        │ Analytics               │
        └─────────────────────────┘
