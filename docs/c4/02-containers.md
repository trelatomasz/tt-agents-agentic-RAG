# C4 Level 2: Containers

This document specifies the **Container Architecture (Level 2)** of the Personal Agentic RAG Platform, detailing the applications, batch jobs, datastores, Keycloak security server, and GCP hosted model endpoints.

---

## 1. Container Diagram

```plantuml
@startuml "02-containers"
!include <C4/C4_Container>

LAYOUT_WITH_LEGEND()

title Container Diagram - Personal Agentic RAG Platform (Level 2)

Person(owner, "Knowledge Researcher", "Submits research queries, reviews evidence, triggers batch ingestion.")
Person_Ext(agent, "Autonomous AI Agent", "Queries evidence and asks grounded questions via MCP.")
System_Ext(ci, "GitHub Actions CI", "Runs rag-index to publish diffs and tombstones.")

Container_Ext(keycloak_ext, "Central Keycloak IAM", "Shared Platform IdP", "Target centralized OIDC/OAuth2 authority for future multi-tenant mesh (Out of scope of this repo).")

System_Boundary(rag_platform, "Personal RAG Platform (GCP & Local)") {
    Container(gateway_lb, "Edge API Gateway & WAF", "Google Cloud ALB + Cloud Armor", "Global HTTPS termination, managed SSL, DDoS shield, rate limiting (120 rpm), and URL map routing.")
    
    Container(cli_ingest, "Ingestion CLI & rag-index", "Python 3.13 / Click / Typer", "CLI tool for local ebook parsing, web fetching, tt-root/info sync, and CI/CD repository indexing.")
    Container(job_ingest, "Batch Ingestion Job", "Cloud Run Job / Container", "Scalable batch worker executing chunking, embedding generation, candidate index creation, and eval gates.")
    
    Container(api_query, "Query Service API", "FastAPI / Python 3.13 / Uvicorn (Cloud Run)", "Stateless HTTPS API with Bearer token validation (MVP) / JWKS (Target), SQL-level ACL filtering, and grounded generation.")
    Container(mcp_server, "Read-Only MCP Server", "FastMCP / Python 3.13 / SSE / HTTPS", "Model Context Protocol adapter exposing read-only tools (rag_search, rag_answer, rag_sources) with Bearer auth propagation.")
    
    ContainerDb(sql_db, "Metadata & Vector Store", "Cloud SQL PostgreSQL 16 + pgvector", "Stores document versions, chunks, dense vector embeddings, tsvector indexes, and ACL labels (db: rag_db).")
    ContainerDb(gcs_buckets, "Artifact Storage", "Google Cloud Storage (Versioned)", "Stores immutable raw files, normalized markdown snapshots, parser manifests, and evaluation golden sets.")
    
    Container(secrets, "Secret Manager", "GCP Secret Manager", "Secures database passwords, Vertex API tokens, and RAG_API_BEARER_TOKEN (MVP auth).")
    Container(telemetry, "Cloud Logging & Monitoring", "GCP Cloud Operations / Phoenix", "Collects structured audit logs, p50/p95 latency metrics, ingestion lag, and OpenTelemetry traces.")
}

System_Boundary(ai_platform, "Google Cloud Vertex AI & Hosted Model Tier") {
    Container(vertex_emb, "Text Embeddings API", "text-embedding-004 / MRL", "Generates dense text embeddings with Matryoshka dimension reduction.")
    Container(vertex_vllm, "GCP Hosted Model Endpoint", "vLLM / Gemma 2 / Llama 3 on GPU", "Fine-Tuned LoRA/DPO model serving for fast, deterministic grounded synthesis.")
    Container(vertex_gemini, "Vertex AI Gemini 2.5 Flash", "Gemini Model API", "Frontier LLM for complex multi-hop synthesis.")
    Container(vertex_pipe, "Model Training Pipelines", "Vertex AI Pipelines / Kubeflow", "Orchestrates contrastive embedding training, SFT/LoRA fine-tuning, and DPO alignment.")
}

Rel(owner, gateway_lb, "Sends HTTPS queries with Bearer token (MVP)", "HTTPS / 443")
Rel(agent, gateway_lb, "Invokes MCP tools with Bearer token (MVP)", "HTTPS / SSE / 443")
Rel(ci, cli_ingest, "Invokes rag-index publish with commit diff", "CLI (GitHub Actions / WIF)")

Rel(gateway_lb, api_query, "Routes /v1/*", "Serverless NEG / HTTPS")
Rel(gateway_lb, mcp_server, "Routes /mcp/*", "Serverless NEG / HTTPS")

Rel(mcp_server, api_query, "Forwards tool requests with Bearer Auth", "Internal HTTPS")
Rel(api_query, secrets, "Validates Bearer token at startup (MVP)", "GCP IAM")
Rel_Back_Neighbor(api_query, keycloak_ext, "Target: Validates RS256 JWT signatures via JWKS", "HTTPS / JWKS (Decoupled)")

Rel(api_query, sql_db, "Executes pre-filtered hybrid search (tsvector + pgvector)", "PostgreSQL / TLS")
Rel(api_query, vertex_vllm, "Prompts fine-tuned grounded LLM", "HTTPS / REST")
Rel(api_query, vertex_gemini, "Fallback frontier reasoning", "HTTPS / Vertex SDK")
Rel(api_query, vertex_emb, "Generates query embedding", "HTTPS / Vertex SDK")

Rel(cli_ingest, job_ingest, "Submits batch job or posts manifest", "HTTPS (Cloud Run Jobs API)")
Rel(job_ingest, gcs_buckets, "Reads raw items, writes normalized artifacts", "HTTPS / GCS API")
Rel(job_ingest, vertex_emb, "Requests batch text embeddings", "gRPC / HTTPS")
Rel(job_ingest, sql_db, "Inserts chunks, vectors, candidate index runs", "PostgreSQL / pgvector (TLS)")
Rel(job_ingest, vertex_pipe, "Triggers model retraining on corpus updates", "HTTPS (Vertex AI API)")

Rel(api_query, secrets, "Fetches DB connection strings & config", "GCP IAM")
Rel(api_query, telemetry, "Emits audit trails and latency traces", "Cloud Logging / OpenTelemetry")

@enduml
```

---

## 2. Container Inventory & Specifications

### 2.1 Edge API Gateway & WAF (Cloud Application Load Balancer + Cloud Armor)
- **Role**: Edge ingress, TLS termination, WAF protection, rate limiting, and URL path dispatching.
- **Routing Rules**:
  - `api.<domain>/v1/*` $\rightarrow$ `rag-query-api` Cloud Run Service
  - `api.<domain>/mcp/*` $\rightarrow$ `rag-mcp-server` Cloud Run Service
  - `api.<domain>/health` $\rightarrow$ Query API healthcheck
- **Cloud Armor Security Policy**:
  - **Rate Limiting**: 120 req/min per IP on `/v1/*` APIs.
  - **Preconfigured WAF Rules**: SQLi (`sqli-canary`), XSS (`xss-canary`), and Protocol Attack mitigations.
  - **SSL Certificates**: Automated Google-managed multi-domain SSL certificates.

### 2.2 Query Service API (`dev-tt-rag-parts` / Cloud Run)
- **Role**: Core serving container handling authenticated search, grounded question answering, and catalog lookups.
- **Security & Authentication Architecture**:
  - **MVP Mode (Single-User)**: Intercepts `Authorization: Bearer <token>` and validates against `RAG_API_BEARER_TOKEN` stored in **GCP Secret Manager**. Binds static single-user context:
    ```python
    PrincipalContext(
        user_id="owner",
        username="tomasz",
        roles=["owner", "admin"],
        acl_labels=["owner:tomasz", "visibility:private", "visibility:public"]
    )
    ```
  - **Target Mode (Decoupled Keycloak Resource Server)**: Validates incoming Bearer JWT tokens against the external shared Keycloak JWKS endpoint (`https://auth.yourdomain.com/.../certs`) with in-memory caching. Extracts dynamic multi-tenant `acl_labels`.

### 2.3 Read-Only MCP Server (`rag-mcp-server` / Cloud Run)
- **Role**: Model Context Protocol adapter for external AI agents.
- **Authentication**: Accepts agent Bearer tokens and propagates the credentials down to the Query Service API.
- **Protocol Support**: Native HTTP Streaming and Server-Sent Events (SSE) for agent tool invocations.

### 2.4 GCP Hosted Model Prediction Endpoint (`vLLM` on Vertex AI)
- **Role**: Low-latency, dedicated model serving container for domain-fine-tuned models.
- **Engine**: `vLLM` container with PagedAttention and FP8/AWQ quantization running on NVIDIA L4 GPU.
- **Models Served**: Domain-adapted Gemma 2 9B / Llama 3 8B with merged LoRA weights for exact citation formatting and strict abstention.

### 2.5 Batch Ingestion Job & Model Training Pipelines
- **Batch Ingestion Job**: Run-to-completion Cloud Run Job parsing, chunking, and staging candidate index runs.
- **Vertex AI Pipelines**: Automated Kubeflow DAG triggered when significant new corpus snapshots are added, running triplet-loss embedding fine-tuning and LoRA instruction tuning.

### 2.6 External Shared Keycloak IdP (Target Evolution - Out of Scope)
- **Role**: Centralized identity provider for multi-tenant and multi-agent meshes across independent repositories.
- **Contract**: Exposes standard OIDC/OAuth2 discovery and JWKS endpoints; this repository contains zero Keycloak container or database definitions.
