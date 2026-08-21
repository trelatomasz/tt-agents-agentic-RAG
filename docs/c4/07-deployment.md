# C4 Deployment View: Local & Cloud Topologies

This document specifies the **Deployment Architecture** of the Personal Agentic RAG Platform, detailing physical node layouts, runtime environments, network isolation boundaries, and IAM role mappings.

---

## 1. Cloud Production Deployment Topology (GCP)

```plantuml
@startuml "07-deployment"
!include <C4/C4_Deployment>

LAYOUT_WITH_LEGEND()

title Deployment Diagram - Google Cloud Platform (GCP) Production / Dev

Deployment_Node(user_env, "Client Workstations & Agents", "External Network") {
    Deployment_Node(agent_client, "Autonomous Agent Client", "Local Host") {
        Container(agent_proc, "AI IDE Agent", "Antigravity / Claude Code", "Queries MCP server over TLS")
    }
    Deployment_Node(human_client, "Human Researcher", "Browser / CLI") {
        Container(browser, "Web Browser / CLI", "HTTPS", "Sends queries & reviews evidence")
    }
}

Deployment_Node(github_env, "GitHub Actions CI", "GitHub Hosted Runner") {
    Container(ci_proc, "rag-index Runner", "GitHub Action", "Executes incremental repo indexing")
}

Deployment_Node(gcp, "Google Cloud Platform", "Region: europe-west1") {
    Deployment_Node(iam_wif, "Identity & Access Management", "GCP IAM") {
        Container(wif_pool, "Workload Identity Pool & Provider", "WIF", "Exchanges GitHub OIDC for short-lived OAuth token")
    }

    Deployment_Node(edge_ingress, "Global Edge & Ingress Tier", "GCP Edge Network") {
        Container(cloud_armor, "Cloud Armor Security Policy", "WAF / DDoS", "Layer-7 rate limiting (120 rpm), SQLi/XSS filters & IP geo-fencing")
        Container(cloud_alb, "Global External Application Load Balancer", "HTTPS / Anycast IP", "Managed SSL termination & URL map path routing")
        Container(neg_api, "Serverless NEG (api)", "Network Endpoint Group", "Points to rag-query-api Cloud Run")
        Container(neg_mcp, "Serverless NEG (mcp)", "Network Endpoint Group", "Points to rag-mcp-server Cloud Run")
    }

    Deployment_Node(vpc, "Virtual Private Cloud (VPC)", "VPC Network") {
        Deployment_Node(serverless_vpc, "Serverless VPC Access Connector", "10.8.0.0/28", "Routes Cloud Run egress to private Cloud SQL IP")
        
        Deployment_Node(cloud_sql_env, "Cloud SQL Managed Instance", "PostgreSQL 16") {
            ContainerDb(pg_db, "Cloud SQL PostgreSQL", "Cloud SQL", "Database: rag_db (pgvector + FTS)")
        }
    }

    Deployment_Node(serverless_env, "Serverless Compute Tier", "Cloud Run") {
        Container(cloud_run_api, "Query Service (dev-tt-rag-parts)", "Cloud Run (HTTPS)", "Stateless FastAPI container with scale-to-zero")
        Container(cloud_run_mcp, "MCP Adapter Service", "Cloud Run (HTTPS/SSE)", "Read-only agent gateway")
        Container(cloud_run_job, "Batch Ingestion Job (dev-personal-rag-ingest)", "Cloud Run Job", "Ephemeral indexing worker")
    }

    Deployment_Node(storage_env, "Managed Storage Tier", "Cloud Storage") {
        ContainerDb(gcs_raw, "Raw Artifacts Bucket", "GCS Versioned", "gs://${PROJECT_ID}-raw-artifacts")
        ContainerDb(gcs_norm, "Normalized Docs Bucket", "GCS Versioned", "gs://${PROJECT_ID}-normalized-docs")
    }

    Deployment_Node(ai_tier, "Google AI Platform", "Vertex AI") {
        Container(vertex_emb, "Text Embeddings API", "text-embedding-004", "Dense vector embeddings")
        Container(vertex_gen, "Gemini 2.5 Flash", "Model Garden", "Grounded answer synthesis")
    }

    Deployment_Node(sec_ops, "Security & Observability", "GCP Managed") {
        Container(sm, "Secret Manager", "Secret Manager", "Stores DB connection string, Vertex tokens & RAG_API_BEARER_TOKEN")
        Container(cloud_ops, "Cloud Logging & Monitoring", "Cloud Operations", "Metrics, audit logs, and alerts")
    }
}

Rel(browser, cloud_alb, "API queries & search (Bearer Auth)", "HTTPS / 443 (Google SSL)")
Rel(agent_proc, cloud_alb, "MCP tool invocations (Bearer Auth)", "HTTPS / SSE / 443")
Rel(cloud_alb, cloud_armor, "Applies WAF & rate-limiting policies")

Rel(cloud_alb, neg_api, "Routes /v1/*", "URL Map")
Rel(cloud_alb, neg_mcp, "Routes /mcp/*", "URL Map")

Rel(neg_api, cloud_run_api, "Forwards sanitized request", "HTTPS")
Rel(neg_mcp, cloud_run_mcp, "Forwards sanitized request", "HTTPS")

Rel(ci_proc, wif_pool, "Authenticates via GitHub OIDC token", "HTTPS / WIF")
Rel(wif_pool, cloud_run_job, "Invokes Cloud Run Job", "GCP IAM")

Rel(cloud_run_mcp, cloud_run_api, "Forwards tool requests", "Internal HTTPS")
Rel(cloud_run_api, serverless_vpc, "Routes egress to Cloud SQL", "Internal VPC")
Rel(serverless_vpc, pg_db, "Executes hybrid SQL queries (db: rag_db)", "PostgreSQL / TLS")
Rel(cloud_run_api, vertex_emb, "Generates query embedding", "HTTPS / Vertex SDK")
Rel(cloud_run_api, vertex_gen, "Grounded synthesis", "HTTPS / Vertex SDK")
Rel(cloud_run_api, sm, "Reads secrets at startup", "GCP IAM")
Rel(cloud_run_api, cloud_ops, "Emits logs and traces", "Cloud Operations")

Rel(cloud_run_job, gcs_raw, "Reads raw items", "HTTPS / GCS API")
Rel(cloud_run_job, gcs_norm, "Writes normalized snapshots", "HTTPS / GCS API")
Rel(cloud_run_job, serverless_vpc, "Connects to DB for indexing", "Internal VPC")
Rel(cloud_run_job, vertex_emb, "Generates chunk embeddings", "HTTPS / Vertex SDK")

@enduml
```

---

## 2. Local Development Topology

To guarantee fast feedback, zero developer cost, and hermetic offline testing, the platform provides a complete **in-process local topology**:

```plantuml
@startuml "07-local-dev-topology"
skinparam componentStyle rectangle

package "Local Workstation Environment" {
    package "Python Virtual Environment (.venv)" {
        [Personal RAG CLI] as CLI
        [In-Process MemoryIndex\n(BM25 + Cosine + RRF)] as MEM
        [Offline HashingEmbedder\n(64-dim Feature Hasher)] as EMB
        [DeterministicAnswerGenerator\n(Mock Generator)] as GEN
    }
    
    database "Local Filesystem\n(Ebooks & Git Repos)" as FS
    file ".rag/manifest.json\n(State Tracker)" as MANIFEST
}

CLI --> FS : Scans sources
CLI --> MANIFEST : Tracks file hashes
CLI --> EMB : Generates local vectors
CLI --> MEM : Indexes chunks
CLI --> GEN : Grounded evaluation

@enduml
```

- **Zero Cloud Dependencies**: The local suite runs entirely offline via `pytest` and `python scripts/personal_rag_demo.py`.
- **Reference Semantics**: `MemoryIndex` implements the identical search and candidate-activation semantics as Cloud SQL `pgvector`.

---

## 3. Least-Privilege IAM Matrix

| Principal / Service Account | Assigned Roles | Bound Resources | Principle of Least Privilege Justification |
|---|---|---|---|
| **Query Service SA** (`sa-query-api`) | `roles/cloudsql.client`<br/>`roles/secretmanager.secretAccessor`<br/>`roles/aiplatform.user`<br/>`roles/logging.logWriter` | Cloud SQL instance<br/>`RAG_API_BEARER_TOKEN` & DB secrets<br/>Vertex AI project<br/>Cloud Logging | Allows read-only hybrid retrieval and grounded generation; zero storage mutation rights. |
| **Ingestion Job SA** (`sa-ingestion-job`) | `roles/cloudsql.client`<br/>`roles/storage.objectAdmin`<br/>`roles/secretmanager.secretAccessor`<br/>`roles/aiplatform.user`<br/>`roles/logging.logWriter` | Cloud SQL instance<br/>Artifact buckets (`raw`, `norm`)<br/>DB connection secret<br/>Vertex AI project | Allows batch chunk insertion and artifact persistence; isolated from public ingress. |
| **CI/CD WIF Service Account** (`sa-github-ci`) | `roles/run.invoker`<br/>`roles/run.jobsExecutor` | Cloud Run ingestion endpoint<br/>Cloud Run ingestion job | Allows triggering batch indexing jobs from verified GitHub repos without service account keys. |
| **Human Owner / Researcher** | `roles/run.invoker` | Cloud Run services | Allows direct HTTPS invocation using pre-shared Bearer token or GCP credentials. |
