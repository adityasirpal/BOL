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
