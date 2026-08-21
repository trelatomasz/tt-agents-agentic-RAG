# C4 Level 1: System Context

This document describes the **System Context (Level 1)** of the Personal Agentic RAG Platform, defining the system boundaries, human actors, autonomous agents, Keycloak identity management, and external cloud systems.

---

## 1. System Context Diagram

```plantuml
@startuml "01-system-context"
!include <C4/C4_Context>

LAYOUT_WITH_LEGEND()

title System Context Diagram - Personal Agentic RAG Platform (Level 1)

Person(owner, "Knowledge Researcher / Owner", "Primary user querying multi-source knowledge, configuring sources, and reviewing grounded answers.")
Person(dev, "Platform Engineer / Developer", "Maintains infrastructure, runs evaluations, manages active index pointer and model tuning.")
Person_Ext(agent, "Autonomous AI Agent", "IDE or conversational agent (Antigravity, Claude Code, Gemini CLI) querying verified evidence via MCP.")
System_Ext(ci, "GitHub Actions CI/CD", "Continuous integration runners pushing changed documentation and code from project repositories.")

System_Boundary(rag_boundary, "Personal RAG Platform (GCP)") {
    System(gateway, "API Gateway & Edge WAF", "Google Cloud Application Load Balancer with Cloud Armor. Enforces rate limits, DDoS mitigation, SSL termination, and path routing.")
    System(personal_rag, "Personal RAG Platform", "Indexes multi-source documents, creates versioned embeddings, executes hybrid retrieval, and provides policy-filtered, grounded answers with citations.")
    System(gpc_pilot, "GPC Parts RAG Pilot", "Compatibility slice providing deterministic vehicle part compatibility searches and answers.")
}

System_Ext(keycloak, "Keycloak IAM (Shared Platform IdP)", "External Centralized Identity Provider for multi-tenant/multi-repo mesh. (Out of scope of this repository).")
System_Ext(vertex, "Google Cloud Vertex AI", "Provides text embeddings, fine-tuned LoRA models (Gemma 2 / Llama 3 on vLLM), and Gemini 2.5 Flash grounded completion.")
SystemDb_Ext(tt_info, "<GIT REPO>/info Git Tree", "Canonical reference knowledge base containing architectural standards, notes, and schemas.")
SystemDb_Ext(ebook_fs, "Local Ebook Storage", "Local filesystem containing EPUB and PDF books and reference papers.")
System_Ext(web_hosts, "Approved Web Hosts", "External public technical documentation and articles allowlisted for ingestion.")

Rel(owner, gateway, "Submits queries & reviews evidence (MVP: Bearer Token / Target: OIDC SSO)", "HTTPS / Bearer Auth")
Rel(agent, gateway, "Invokes read-only MCP tools", "HTTPS / SSE / Bearer Auth")
Rel(dev, personal_rag, "Deploys infra, runs evaluation gates, manages index & tuning", "OpenTofu / gcloud / CLI")
Rel(ci, personal_rag, "Publishes changed files and deletion tombstones on commit", "HTTPS / WIF / rag-index")

Rel(gateway, personal_rag, "Routes /v1/* & /mcp/* with Bearer credentials", "Internal HTTPS")

Rel_Back_Neighbor(personal_rag, keycloak, "Target: Validates RS256 JWT signatures & extracts acl_labels", "HTTPS / JWKS (Decoupled)")
Rel(personal_rag, vertex, "Generates dense embeddings & queries tuned/foundation models", "gRPC / HTTPS (GCP IAM)")
Rel(personal_rag, tt_info, "Reads Markdown/YAML notes with Git commit SHA tracking", "Read-Only Git / FS")
Rel(personal_rag, ebook_fs, "Extracts text, hierarchy and page locators from PDF/EPUB", "Local CLI / Filesystem")
Rel(personal_rag, web_hosts, "Fetches canonical HTML articles with SSRF and robots.txt checks", "HTTPS (Strict Allowlist)")

Rel(owner, gpc_pilot, "Searches vehicle parts fitment", "HTTPS / API")
Rel(gpc_pilot, vertex, "Generates fitment answers", "HTTPS")

@enduml
```

---

## 2. Actors & Personas

| Actor | Role & Responsibilities | Interaction Channels | Security Context |
|---|---|---|---|
| **Knowledge Researcher / Owner** | Single human owner. Formulates complex multi-source research queries, approves source descriptors, and inspects citations down to source locators. | Web UI, CLI (`personal_rag.query`), HTTPS API | **MVP**: Pre-shared Bearer Token from Secret Manager.<br/>**Target**: Keycloak OIDC SSO (`realm-admin`). |
| **Platform Engineer / Developer** | Operates OpenTofu infrastructure, verifies eval benchmarks, monitors ingestion lag, trains/tunes LoRA models, and manages candidate index activations. | Windows PowerShell, WSL Linux (`tofu`, `gcloud`, `make`) | Authenticated GCP Operator (`roles/run.admin`, `roles/aiplatform.admin`). |
| **Autonomous AI Agent** | External agent (e.g., Google Antigravity, Claude Code, Cursor) needing factual grounding to write code, design architectures, or verify policies. | Model Context Protocol (MCP) over HTTPS | **MVP**: Scoped Bearer Token.<br/>**Target**: Keycloak Client Credentials JWT. |
| **Project CI/CD Runner** | Automated workflow executing in project repositories on push/merge to publish updated documentation and code into the index. | `rag-index` CLI via GitHub Actions | Keyless Workload Identity Federation (WIF) mapped to `roles/run.invoker`. |

---

## 3. External & Core Supporting Systems

### 3.1 Cloud Edge API Gateway & Cloud Armor WAF
- **Role**: Unified ingress entry point for all external client traffic.
- **Key Responsibilities**:
  - Global SSL/TLS termination using automated Google-managed certificates on custom domains.
  - DDoS protection and Layer-7 rate limiting (e.g., 120 req/min for query APIs).
  - Path-based routing: `/v1/*` $\rightarrow$ Query API, `/mcp/*` $\rightarrow$ Read-Only MCP Server, `/health` $\rightarrow$ Status.

### 3.2 Keycloak Identity & Access Management (Shared Platform - Out of Scope)
- **Role**: Independent, organization-wide Identity Provider deployed in a separate shared infrastructure cluster/repository.
- **Relationship to this Project**:
  - **Decoupled Architecture**: This repository does NOT provision, host, or manage Keycloak.
  - **Resource Server Integration (Phase 2)**: FastAPI Query API operates purely as an OAuth2 Resource Server, validating incoming JWTs against Keycloak's public JWKS endpoint (`/protocol/openid-connect/certs`).
  - **MVP Mode (Phase 1)**: Keycloak is bypassed in favor of a single-user pre-shared Bearer Token stored in GCP Secret Manager, allowing immediate deployment with zero overhead.

### 3.3 Google Cloud Vertex AI & Hosted Models
- **Role**: Foundational AI, custom fine-tuning, and model serving platform.
- **Capabilities**:
  - **Text Embeddings**: `text-embedding-004` and domain-adapted contrastive embedding models.
  - **GCP Hosted & Tuned LLMs**: Google Gemma 2 (9B/27B) and Llama 3 (8B/70B) fine-tuned with PEFT/LoRA and DPO on Vertex AI Custom Training, deployed on `vLLM` high-throughput prediction endpoints.
  - **Frontier LLM**: Gemini 2.5 Flash for high-capacity multi-hop reasoning.

### 3.4 Canonical Knowledge Base & Sources
- **`tt-root/info` Knowledge Base**: Canonical personal knowledge tree containing foundational engineering standards, AI lifecycle documents, and domain notes via read-only Git filesystem.
- **Local Windows Ebook Storage**: PDF/EPUB technical books parsed with page/chapter locator provenance.
- **Approved Web Hosts**: Outbound HTTPS fetching with strict SSRF defenses, DNS pinning, and `robots.txt` compliance.

---

## 4. Trust Boundaries & Security Envelopes

```plantuml
@startuml "01-trust-boundaries"
skinparam componentStyle rectangle
skinparam roundCorner 10

title Trust Boundaries & Security Envelopes

package "External Untrusted Domain" {
    [Public Web Hosts] as WEB
    [Agent Runtime (Antigravity/Claude)] as AGENT_RUNTIME
    [Human Researcher Browser / CLI] as USER_CLIENT
}

package "Shared Organization Services (External)" {
    [Centralized Keycloak IAM (Future Multi-Tenant IdP)] as SHARED_KEYCLOAK
}

package "GCP Security Envelope (Personal RAG Platform)" {
    package "Edge Ingress DMZ" {
        [Cloud Armor WAF\n(Rate Limiting & DDoS Shield)] as WAF
        [Cloud Application Load Balancer\n(Edge SSL & Path Routing)] as ALB
    }

    package "Ingestion Boundary (Write & Index)" {
        [Cloud Run Ingestion / CLI] as INGEST
        database "Cloud Storage\n(Immutable Buckets)" as RAW_STORAGE
    }

    package "Query Boundary (Read-Only & Policy Gated)" {
        [Cloud Run Query Service (FastAPI)\nBearer Validator (MVP) / JWKS (Target)] as QUERY_API
        [Read-Only MCP Server (Cloud Run)] as MCP_SERVER
        database "Cloud SQL PostgreSQL\n(pgvector + ACL Row-Level Filter)" as SQL_DB
        [GCP Secret Manager\n(RAG_API_BEARER_TOKEN)] as SECRETS
    }

    package "AI Services (Managed & Hosted Endpoints)" {
        [Vertex AI Training Pipelines\n(SFT / LoRA / DPO)] as VERTEX_TRAIN
        [vLLM Hosted Prediction Endpoints] as VERTEX_SERVE
        [Vertex AI Gemini & Embeddings] as VERTEX_GEMINI
    }
}

USER_CLIENT --> WAF : HTTPS (Bearer Auth)
AGENT_RUNTIME --> WAF : HTTPS (Bearer Auth)
WAF --> ALB : Forward Sanitized Traffic

ALB --> MCP_SERVER : Route /mcp/* (Bearer Auth)
ALB --> QUERY_API : Route /v1/* (Bearer Auth)

MCP_SERVER --> QUERY_API : Forward Verified Request (Bearer Auth)
QUERY_API --> SECRETS : Validate Token (MVP Single-User)
QUERY_API ..> SHARED_KEYCLOAK : Validate JWT via JWKS (Target Multi-Tenant)

QUERY_API --> SQL_DB : Pre-Filtered SQL Query (WHERE acl_labels && :user_labels)
QUERY_API --> VERTEX_SERVE : Prompt Grounded Model
QUERY_API --> VERTEX_GEMINI : Fallback Frontier LLM

INGEST --> RAW_STORAGE : Write Artifacts
INGEST --> SQL_DB : Write Chunks & Vectors
INGEST --> VERTEX_TRAIN : Trigger Fine-Tuning Pipeline

@enduml
```
