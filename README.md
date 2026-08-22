# Personal Agentic RAG Platform & GPC Pilot

Production-grade, privacy-first Retrieval-Augmented Generation (RAG) platform deployed on Google Cloud Platform (GCP). It transforms multi-source knowledge (local ebooks, web documentation, canonical Git notes, and repository diffs) into versioned, grounded, and policy-filtered retrieval artifacts with verifiable citations.

---

## 1. Overview

The platform operates as two decoupled subsystems:
1. **Ingestion Pipeline**: Discovers and normalizes heterogeneous sources, performs structure-aware chunking, generates dense embeddings, and publishes versioned candidate indexes evaluated against automated release gates.
2. **Query & Agent Boundary**: Executes authenticated hybrid retrieval (sparse full-text search fused with dense `pgvector` similarity via Reciprocal Rank Fusion), applies SQL-level ACL filtering, and synthesizes grounded answers with strict citation validation and fail-closed abstention.

```
[Sources: PDF/EPUB, Web, Git, CI] ──> [Ingestion Pipeline] ──> [Cloud SQL (pgvector + FTS)]
                                                                      │
[User / Researcher] ──> [FastAPI Query API]  <────────────────────────┘
[AI Agent (MCP)]    ──> [Read-Only FastMCP]  ──> [Grounded Synthesis (Vertex AI / vLLM)]
```

For the complete architectural design and C4 diagrams, see [**`docs/architecture.md`**](docs/architecture.md) and [**`docs/c4/`**](docs/c4/README.md).

---

## 2. Dashboard & Coordinates

Centralized links to live Google Cloud Console resources, log streams, and monitoring metrics for deployed environments:

- **Cloud Run Services**: [Query API Service (`dev-tt-rag-parts`)](docs/dashboard.md#1-cloud-run-services--ingestion-jobs) | [Batch Ingestion Job (`dev-personal-rag-ingest`)](docs/dashboard.md#1-cloud-run-services--ingestion-jobs)
- **Database & Storage**: [Cloud SQL PostgreSQL (`pgvector`)](docs/dashboard.md#2-cloud-sql-postgresql-instance-pgvector) | [Catalog & Artifacts Buckets](docs/dashboard.md#3-cloud-storage-gcs-buckets)
- **Security & IAM**: [Secret Manager](docs/dashboard.md#4-container-registries--security) | [Workload Identity Pools](docs/dashboard.md#4-container-registries--security)
- **Observability**: [Logs Explorer](docs/dashboard.md#5-observability-tracing--operations) | [Cloud Trace](docs/dashboard.md#5-observability-tracing--operations) | [Cloud Monitoring](docs/dashboard.md#5-observability-tracing--operations)

Detailed coordinates and operational commands are documented in [**`docs/dashboard.md`**](docs/dashboard.md).

---

## 3. Bootstrap & Release

### Initial GCP Bootstrap
Infrastructure is provisioned via OpenTofu in [`deployment/gcp/`](deployment/gcp/):

```bash
# 1. Authenticate local gcloud CLI
gcloud auth login && gcloud auth application-default login

# 2. Provision GCP infrastructure
cd deployment/gcp
tofu init
tofu apply
```

### Release & Rollback Policy
- **Hermetic CI Gates**: Every pull request runs linting, unit tests, and the golden evaluation benchmark before building an immutable image digest.
- **Keyless Deployment**: GitHub Actions authenticates via Workload Identity Federation (WIF) — zero static service account keys.
- **Atomic Index Swaps & Rollback**: Ingestion runs stage a candidate index; an atomic pointer swap promotes it upon passing gates. Reverting to a prior stable index takes $< 5$ seconds.

Step-by-step bootstrap procedures: [**`docs/bootstrap.md`**](docs/bootstrap.md)  
Release and rollback mechanisms: [**`docs/release.md`**](docs/release.md)

---

## 4. Usage & Integration

The platform provides multiple integration interfaces:

### A. HTTP REST API
Query the authenticated service for hybrid search or grounded question answering:

```bash
# Grounded Q&A with verifiable chunk citations
curl -X POST "https://<SERVICE_URL>/v1/answer" \
  -H "Authorization: Bearer ${RAG_API_BEARER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the rules for idempotent ingestion?", "token_budget": 4000}'
```

### B. Python In-Process SDK
Embed the retrieval and query service directly into Python applications:

```python
from personal_rag.index.memory import MemoryIndex
from personal_rag.pipeline.embed import HashingEmbedder
from personal_rag.query.service import QueryService

index = MemoryIndex(embedder=HashingEmbedder())
service = QueryService(index=index)

result = service.search(query="idempotent ingestion", top_k=5)
for hit in result.hits:
    print(f"[{hit.chunk_id}] (Score: {hit.score:.3f}): {hit.text}")
```

### C. Model Context Protocol (MCP) for AI Agents
Autonomous AI agents (e.g., Antigravity, Claude Code, Cursor) connect to the read-only FastMCP server over Server-Sent Events (SSE) / HTTPS:

```json
{
  "mcpServers": {
    "personal-rag": {
      "url": "https://<SERVICE_URL>/mcp/sse",
      "headers": {
        "Authorization": "Bearer <RAG_API_BEARER_TOKEN>"
      }
    }
  }
}
```
*Exposed read-only tools*: `rag_search`, `rag_answer`, `rag_sources`, `rag_ingestion_status`.

### D. Ingestion CLI
Run batch or incremental ingestion from local workstations:

```powershell
# Index a local folder containing markdown/ebook files
python -m personal_rag.cli ingest --source-type filesystem --path "./data/personal/notes"
```

---

## 5. Service Level Objectives (SLO)

| Objective | Target | Operational Escalation |
|---|---:|---|
| **Query Service Availability** | 99.9% monthly | Page on fast error-budget burn |
| **Search Latency (p95)** | $< 800$ ms | Metric alert; check database index query plan |
| **Grounded Answer Latency (p95)** | $< 3.5$ s | Ticket unless fallback path also fails |
| **Citation Correctness** | $\ge 95\%$ | Page on grounding/entailment regression |
| **Unsafe / Hallucinated Claims** | 0 known | Immediate fail-closed abstention & page |
| **Catalog / Source Freshness** | $< 1$ hour | Disable generation; fallback to lexical search |

Capacity calculations, load modeling, and incident response procedures: [**`docs/slo-runbook.md`**](docs/slo-runbook.md)

---

## 6. Threat Model & Security

The platform enforces a zero-trust, privacy-first security posture:

- **Untrusted Evidence Boundary**: Ingested content (web articles, third-party code) is strictly delimited as untrusted data in XML tags. Retrieved text cannot execute tools, grant authorizations, or alter prompts.
- **SQL-Level Authorization Pushdown**: ACL labels (`WHERE acl_labels && :user_labels`) are evaluated in SQL before ranking, preventing unauthorized evidence from reaching the LLM context.
- **Zero Agent Mutation**: AI agents access the system exclusively via read-only MCP tools with no write or schema modification capabilities.
- **Zero-Leak Redaction**: Public repository hygiene strictly forbids hardcoded credentials, private emails, or real GCP project IDs.

Comprehensive threat vectors and STRIDE controls: [**`docs/threat-model.md`**](docs/threat-model.md) and [**`docs/c4/08-requirements-assumptions.md`**](docs/c4/08-requirements-assumptions.md).

---

## 7. Documentation Atlas

- [**High-Level Architecture**](docs/architecture.md): System overview, subsystems, and design principles.
- [**C4 Architectural Specification**](docs/c4/README.md): Level 1 System Context through Level 4 Data & Code models.
- [**Living Platform Specification**](docs/specs/personal-rag-spec.md): Progress register, vertical slices, and connector contracts.
- [**Architecture Decision Records (ADRs)**](docs/adr/):
  - [`ADR-001`: Rejected Technologies & Trade-Offs](docs/adr/0001-rejected-technologies.md)
  - [`ADR-002`: Edge API Gateway (Cloud ALB & Cloud Armor)](docs/adr/0002-api-gateway-and-ingress-architecture.md)
  - [`ADR-003`: Public Repository Hygiene & Identity Sanitization](docs/adr/0003-public-repository-hygiene-and-identity-sanitization.md)
- [**Evidence & Verification Maps**](docs/knowledge-evidence/): Problem-to-solution mapping and RAG failure-mode controls.
