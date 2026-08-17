# Architecture and decisions

The proposed personal multi-source platform is specified in
[`personal-rag-spec.md`](personal-rag-spec.md). This document remains the GPC pilot
architecture and compatibility boundary.

```mermaid
flowchart LR
  user["Authenticated internal user"] --> run["Private Cloud Run FastAPI"]
  run --> bucket["Versioned Cloud Storage catalog"]
  run --> vertex["Vertex AI Gemini"]
  run --> logs["Cloud Logging and Monitoring"]
  tofu["OpenTofu"] --> run
  tofu --> bucket
  tofu --> iam["Least-privilege IAM"]
```

The API retrieves bounded, fitment-aware evidence, rejects low-confidence or unsupported
vehicle/year matches, invokes Gemini at temperature zero and returns source and
catalog-version citations. Generated answers must cite retrieved part identifiers before
they can leave the service. It fails closed to conventional search for stale catalogs,
absent evidence or failed grounding. React sees only versioned HTTP and Server-Sent Events
contracts.

## Autonomy boundary

Use deterministic retrieval plus bounded generation, not an agent: no dynamic tool choice
is required. Compare a bounded read-only agent only if variable product lookups become
necessary. Remove autonomy after any unauthorized or incorrect action, or when measured
completion gain does not justify latency, cost and operational risk.

## Decision experiment

Use 30–50 representative queries to compare deterministic RAG and a read-only agent for
one week on correctness, groundedness, latency, cost and unsafe tool attempts. The service
owner decides and records dissent; lack of consensus does not block the safer demo.
