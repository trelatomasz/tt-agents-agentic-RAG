# Architecture and decisions

The proposed personal multi-source platform is specified in
[`personal-rag-spec.md`](specs/personal-rag-spec.md). This document remains the GPC pilot
architecture and compatibility boundary.

```plantuml
@startuml "architecture-overview"
!include <C4/C4_Container>

LAYOUT_WITH_LEGEND()

title GPC Parts RAG Pilot - Container Boundary

Person(user, "Authenticated internal user", "Queries vehicle parts and reviews grounded fitment answers.")
Container(run, "Private Cloud Run FastAPI", "FastAPI / Python 3.13", "Stateless serving container with fitment search and Gemini grounding.")
ContainerDb(bucket, "Versioned Cloud Storage catalog", "Google Cloud Storage", "Stores immutable parts catalog versions.")
Container_Ext(vertex, "Vertex AI Gemini", "Gemini 2.5 Flash", "Grounded generation at temperature 0.0.")
Container(logs, "Cloud Logging and Monitoring", "Cloud Operations", "Audit trails and latency metrics.")
System_Ext(tofu, "OpenTofu", "Provisions Cloud Run, GCS buckets, and IAM roles.")

Rel(user, run, "Sends fitment queries", "HTTPS / API")
Rel(run, bucket, "Reads catalog slices", "HTTPS / GCS API")
Rel(run, vertex, "Prompts grounded generation", "HTTPS / Vertex SDK")
Rel(run, logs, "Emits audit logs", "Cloud Logging")

Rel(tofu, run, "Provisions")
Rel(tofu, bucket, "Provisions")

@enduml
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
