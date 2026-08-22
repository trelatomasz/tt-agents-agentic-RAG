# Architecture Overview: Personal Agentic RAG Platform

> **Platform**: Personal Agentic Retrieval-Augmented Generation (RAG) Platform & GPC Pilot  
> **Status**: Living Architectural Baseline  
> **Scope**: High-level platform architecture, subsystem boundaries, data lifecycle, and documentation atlas.

---

## 1. Executive Summary & Purpose

The **Personal Agentic RAG Platform** is a production-grade, multi-source, privacy-first Retrieval-Augmented Generation (RAG) platform deployed on Google Cloud Platform (GCP). It transforms heterogeneous, unstructured, and semi-structured knowledge into versioned, grounded, and policy-filtered retrieval artifacts.

The platform serves two primary user personas:
1. **Human Researchers & Operators**: Interacting via HTTPS APIs, Web UIs, or CLI tools for multi-source research queries with verifiable citations.
2. **Autonomous AI Agents** (e.g., Antigravity, Claude Code, Cursor): Accessing verified knowledge strictly via a read-only **Model Context Protocol (MCP)** interface without write or mutation permissions.

```plantuml
@startuml "architecture-high-level-context"
!include <C4/C4_Context>

LAYOUT_WITH_LEGEND()

title Personal Agentic RAG Platform - System Context

Person(user, "Human Researcher / Owner", "Submits research queries and reviews grounded answers with exact source citations.")
Person_Ext(agent, "Autonomous AI Agent", "Queries verified knowledge via read-only Model Context Protocol (MCP).")
System_Ext(ci, "GitHub Actions CI/CD", "Publishes repository commit diffs and documentation via Workload Identity Federation.")

System_Boundary(rag_platform, "Personal RAG Platform (GCP)") {
    System(gateway, "API Gateway & Edge WAF", "Cloud ALB + Cloud Armor: Rate limiting, SSL termination, and path routing.")
    System(personal_rag, "Personal RAG Engine", "Multi-source ingestion, hybrid search (pgvector + FTS), grounding, and citations.")
    System(gpc_pilot, "GPC Parts RAG Pilot", "Compatibility slice: Deterministic vehicle parts compatibility search and answers.")
}

System_Ext(vertex, "Vertex AI & Hosted Models", "Text embeddings (text-embedding-004), fine-tuned vLLM models, and Gemini Flash.")
SystemDb_Ext(sources, "Knowledge Sources", "Local Ebooks (PDF/EPUB), Git repos (tt-root/info), Web articles, CI diffs.")

Rel(user, gateway, "Queries knowledge (HTTPS / Bearer Auth)", "HTTPS")
Rel(agent, gateway, "Invokes read-only MCP tools", "HTTPS / SSE")
Rel(ci, personal_rag, "Publishes changed files (rag-index)", "HTTPS / WIF")

Rel(gateway, personal_rag, "Routes /v1/* and /mcp/*", "Internal HTTPS")
Rel(personal_rag, sources, "Ingests and normalizes", "FS / HTTPS / Git")
Rel(personal_rag, vertex, "Embeddings and grounded synthesis", "gRPC / HTTPS")
Rel(user, gpc_pilot, "Queries vehicle parts fitment", "HTTPS")

@enduml
```

---

## 2. Architectural Evolution: Pilot to Multi-Source Platform

The repository implements a staged architectural model:

```mermaid
graph LR
    subgraph S1["1. Bounded Pilot (GPC Parts RAG)"]
        A1["Structured Parts Catalog"] --> B1["Fitment-Aware Lexical Search"]
        B1 --> C1["Gemini 2.5 Flash Grounding"]
        C1 --> D1["GPC API (/v1/answers)"]
    end
    
    subgraph S2["2. Personal Multi-Source RAG Platform"]
        A2["Multi-Source Adapters\n(PDF/EPUB, Web, Git, CI)"] --> B2["Structure-Aware Chunking\n& Versioned Embeddings"]
        B2 --> C2["PostgreSQL Hybrid Search\n(pgvector + tsvector)"]
        C2 --> D2["Reciprocal Rank Fusion (RRF)\n+ SQL-Level ACL Pushdown"]
        D2 --> E2["Strict Abstention Gate\n& Citation Validator"]
        E2 --> F2["FastAPI Serving\n(/v1/search, /v1/answer)"]
        E2 --> G2["Read-Only FastMCP Server\n(/mcp/* for AI Agents)"]
    end

    S1 -.->|"Preserves compatibility while generalizing into"| S2
```

1. **GPC Parts RAG Pilot**: The initial, deployable vertical slice focusing on vehicle parts fitment, strict lexical matching, and closed-loop grounding.
2. **Personal Multi-Source Platform**: The generalized platform introducing pluggable source adapters, hybrid vector retrieval, SQL-level ACL filtering, offline candidate index gates, and agent boundaries.

---

## 3. High-Level Container Architecture

The system is deployed on GCP serverless and managed infrastructure to maintain a **scale-to-zero** cost profile when idle while delivering sub-second hybrid retrieval.

```plantuml
@startuml "architecture-containers"
!include <C4/C4_Container>

LAYOUT_WITH_LEGEND()

title Personal Agentic RAG Platform - Container Boundary

Container(gateway, "Edge API Gateway", "Cloud ALB + Cloud Armor", "Global TLS termination, WAF protection, rate limiting (120 rpm).")
Container(api, "Query Service API", "Cloud Run (FastAPI / Python 3.13)", "Hybrid retrieval, RRF ranking, grounding validation, and answer generation.")
Container(mcp, "Read-Only MCP Server", "Cloud Run (FastMCP / Python 3.13)", "Model Context Protocol streaming gateway for autonomous AI agents.")
Container(job, "Batch Ingestion Job", "Cloud Run Job (Python 3.13)", "Offline document parsing, chunking, embedding generation, and candidate index evaluation.")

ContainerDb(sql, "Metadata & Vector Store", "Cloud SQL PostgreSQL 16 + pgvector", "Stores chunks, embeddings (768-dim), tsvector indexes, and ACL labels.")
ContainerDb(gcs, "Artifact Storage", "Google Cloud Storage (Versioned)", "Immutable raw source documents, normalized Markdown snapshots, and evaluation sets.")

Container(sm, "Secret Manager", "GCP Secret Manager", "Secures database connection credentials, Vertex tokens, and API tokens.")
Container_Ext(vertex, "Vertex AI & Model Garden", "text-embedding-004 & Gemini 2.5 Flash", "Dense vector embeddings and frontier grounded completion.")

Rel(gateway, api, "Routes /v1/*", "HTTPS")
Rel(gateway, mcp, "Routes /mcp/*", "HTTPS / SSE")
Rel(mcp, api, "Forwards tool queries with Bearer token", "Internal HTTPS")

Rel(api, sql, "Executes hybrid search (WHERE acl_labels && user_labels)", "PostgreSQL / TLS")
Rel(api, vertex, "Query embeddings & grounded synthesis", "HTTPS")
Rel(api, sm, "Fetches runtime secrets", "GCP IAM")

Rel(job, gcs, "Persists immutable snapshots", "HTTPS / GCS API")
Rel(job, vertex, "Batch embedding generation", "gRPC / HTTPS")
Rel(job, sql, "Stages candidate index runs & atomic swap", "PostgreSQL / TLS")

@enduml
```

---

## 4. Core Subsystems & Operational Flow

### 4.1 Ingestion & Processing Pipeline
- **Source Adapters**: Uniform [`SourceAdapter`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/src/personal_rag/sources/base.py) protocol ingesting Local Filesystem (`PDF`, `EPUB`, `MD`), Git repositories (`tt-root/info`), Approved Web pages (with SSRF guard and DNS pinning), and CI/CD repository diffs.
- **Normalization & Structure-Aware Chunking**: Markdown-aware and code-aware chunkers splitting on natural section headings and symbol boundaries (target 400–800 tokens, 10–15% overlap) without cross-heading merging.
- **Deduplication & Idempotency**: SHA-256 content hashing at document and chunk levels prevents redundant embeddings or writes.
- **Candidate Indexing & Atomic Swap**: Ingestion builds an isolated candidate run (`CANDIDATE`). Once golden retrieval evaluation gates pass, an atomic pointer swap promotes the run to `ACTIVE`.

### 4.2 Query Engine & Retrieval Pipeline
- **Authentication**: Pluggable authentication supporting single-user Bearer token validation (MVP via Secret Manager) and decoupled multi-tenant Keycloak JWKS verification (Target).
- **Hybrid Retrieval**: Parallel PostgreSQL full-text search (`tsvector` with `ts_rank`) and dense vector similarity (`pgvector` cosine distance).
- **SQL-Level Policy Pushdown**: User ACL labels (`user_labels`) are evaluated directly in SQL (`WHERE acl_labels && :user_labels`) before distance ranking, preventing unauthorized evidence from reaching the LLM context.
- **Reciprocal Rank Fusion (RRF)**: Merges sparse and dense ranked candidate lists ($k=60$) into a single unified ranking.
- **Strict Abstention & Citation Verification**: Fails closed when evidence confidence is below threshold ($< 0.35$). Synthesized answers must cite valid retrieved chunk IDs (`[chunk_id]`) or generation is rejected.

### 4.3 Agent Interface Boundary
- **Read-Only MCP Protocol**: AI agents query the system exclusively via FastMCP tools (`rag_search`, `rag_answer`, `rag_sources`, `rag_ingestion_status`).
- **Zero Agent Mutation**: Agents possess zero direct database access, zero write credentials, and zero tools capable of triggering ingestion or altering ACLs.

---

## 5. Architectural Principles

| Principle | Architectural Implementation |
|---|---|
| **Sources are Adapters** | All connectors emit standardized `DocumentVersion` and `Chunk` records. |
| **Deterministic Precedence** | High-precision hybrid search and strict grounding take precedence over unconstrained agent loops. |
| **Security at the Data Layer** | Access control labels are filtered at SQL execution time, never inside the LLM prompt. |
| **Evidence is Untrusted Payload** | Retrieved text is delimited as data; it cannot trigger tools or override safety rules. |
| **Scale-to-Zero Serverless** | Cloud Run services and jobs scale to zero instances when idle with no baseline compute cost. |
| **Rebuildable & Rollbackable** | Index runs are versioned and immutable; rollback to prior index takes $< 5$ seconds. |
| **Zero Credential / Identity Leaks** | Generic infrastructure templates, keyless WIF, Secret Manager, and decoupled authentication. |

---

## 6. Documentation Atlas & Deep Dives

```
docs/
├── architecture.md                     # High-level project overview (This document)
├── overview.md                         # GPC pilot architecture and autonomy boundary
├── dashboard.md                        # GCP console coordinates, logs, and telemetry links
├── bootstrap.md                        # Step-by-step GCP project bootstrap and OpenTofu provisioning
├── release.md                          # Release, evaluation gates, and rollback procedures
├── slo-runbook.md                      # Service Level Objectives, capacity, and incident runbooks
├── threat-model.md                     # STRIDE threat matrix and security enforcement points
├── specs/
│   └── personal-rag-spec.md            # Living platform specification and progress register
├── c4/                                 # Formal C4 Architectural Model
│   ├── README.md                       # C4 specification index and document map
│   ├── 01-system-context.md            # Level 1: System Context & Boundaries
│   ├── 02-containers.md                # Level 2: Containers & Datastores
│   ├── 03-components-ingestion.md      # Level 3: Ingestion Pipeline & Adapters
│   ├── 04-components-query.md          # Level 3: Query Engine, Auth & MCP
│   ├── 05-dynamic-flows.md             # Sequence diagrams for 8 core flows
│   ├── 06-data-and-code.md             # Level 4: PostgreSQL ERD, Schemas & State Machines
│   ├── 07-deployment.md                # Deployment view: Local Workstation vs GCP Cloud
│   ├── 08-requirements-assumptions.md  # Functional Requirements, NFRs & Security Controls
│   ├── 09-rag-and-agent-evaluations.md # RAG Triad, Retrieval Metrics & LLM-as-a-Judge
│   ├── 10-model-optimization-and-tuning.md # LoRA/PEFT, SFT, DPO & vLLM serving
│   └── 11-monitoring-and-observability.md  # OpenTelemetry, Metrics & PSI Drift Detection
├── adr/                                # Architecture Decision Records
│   ├── 0001-rejected-technologies.md   # Rejected alternatives and trade-off analysis
│   ├── 0002-api-gateway-and-ingress-architecture.md # Edge ALB and Cloud Armor gateway
│   └── 0003-public-repository-hygiene-and-identity-sanitization.md # Generic identity and hygiene rules
└── knowledge-evidence/                # Evaluation and interview evidence maps
    ├── README.md                       # Problem-to-solution evidence map
    ├── question-evidence.md            # Architecture & interview verification matrix
    ├── portfolio-evidence.md           # Product and behavioral evidence
    └── rag-problem-evidence.md         # RAG failure modes and control verification
```
