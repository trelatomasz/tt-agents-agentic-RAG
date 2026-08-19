# GCP Operations & Monitoring Dashboard

This dashboard centralizes direct links to the Google Cloud Console for all active infrastructure, services, metrics, traces, and log streams for the `dev` and `prod` environments.

> [!NOTE]
> Replace `your-gcp-project-id` with your target GCP Project ID, or run `./scripts/smoke.sh` to retrieve live URLs dynamically.

---

## 1. Cloud Run Services & Ingestion Jobs

| Component | Environment | Direct Console Link | Real-Time Logs | Metrics & Health |
|---|---|---|---|---|
| **Query API Service** (`tt-rag-parts`) | `dev` | [Cloud Run Service Details](https://console.cloud.google.com/run/detail/europe-west1/dev-tt-rag-parts/overview?project=your-gcp-project-id) | [Service Logs](https://console.cloud.google.com/run/detail/europe-west1/dev-tt-rag-parts/logs?project=your-gcp-project-id) | [CPU, Memory & Latency](https://console.cloud.google.com/run/detail/europe-west1/dev-tt-rag-parts/metrics?project=your-gcp-project-id) |
| **Batch Ingestion Job** (`personal-rag-ingest`) | `dev` | [Cloud Run Job Details](https://console.cloud.google.com/run/jobs/details/europe-west1/dev-personal-rag-ingest/executions?project=your-gcp-project-id) | [Job Execution Logs](https://console.cloud.google.com/run/jobs/details/europe-west1/dev-personal-rag-ingest/logs?project=your-gcp-project-id) | [Job History](https://console.cloud.google.com/run/jobs/details/europe-west1/dev-personal-rag-ingest/executions?project=your-gcp-project-id) |

---

## 2. Cloud SQL PostgreSQL Instance (pgvector)

| Resource | Identifier / Connection | Console Link | Query Insights | Logs |
|---|---|---|---|---|
| **PostgreSQL 16 Instance** | `dev-rag-db` | [Instance Overview](https://console.cloud.google.com/sql/instances?project=your-gcp-project-id) | [Query Insights & Plans](https://console.cloud.google.com/sql/instances?project=your-gcp-project-id) | [Database Logs](https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloudsql_database%22?project=your-gcp-project-id) |
| **Database & User** | `dev_personal_rag` / `rag_app` | [Users & Databases](https://console.cloud.google.com/sql/instances?project=your-gcp-project-id) | - | - |

---

## 3. Cloud Storage (GCS) Buckets

| Purpose | Bucket Name | Console Browser Link |
|---|---|---|
| **Catalog Bucket** (Versioned JSON) | `your-gcp-project-id-dev-catalog` | [Open Catalog Bucket](https://console.cloud.google.com/storage/browser/your-gcp-project-id-dev-catalog?project=your-gcp-project-id) |
| **Artifacts Bucket** (Embeddings & Indices) | `your-gcp-project-id-dev-rag-artifacts` | [Open Artifacts Bucket](https://console.cloud.google.com/storage/browser/your-gcp-project-id-dev-rag-artifacts?project=your-gcp-project-id) |
| **OpenTofu State Bucket** (Remote State) | `your-gcp-project-id-tf-state` | [Open TF State Bucket](https://console.cloud.google.com/storage/browser/your-gcp-project-id-tf-state?project=your-gcp-project-id) |

---

## 4. Container Registries & Security

| Resource | Name / Scope | Console Link |
|---|---|---|
| **Artifact Registry** | `tt-rag-parts` (Docker) | [Docker Repository](https://console.cloud.google.com/artifacts/docker/your-gcp-project-id/europe-west1/tt-rag-parts?project=your-gcp-project-id) |
| **Secret Manager** | `dev-rag-database-url`, `dev-rag-db-password` | [Secret Manager Console](https://console.cloud.google.com/security/secret-manager?project=your-gcp-project-id) |
| **Workload Identity Pools** | `github-pool-dev` | [WIF Pools & Providers](https://console.cloud.google.com/iam-admin/workload-identity-pools?project=your-gcp-project-id) |
| **Service Accounts & IAM** | Runtime, Ingestion & Deployer SAs | [IAM & Admin Console](https://console.cloud.google.com/iam-admin/iam?project=your-gcp-project-id) |

---

## 5. Observability, Tracing & Operations

| Tool | Focus | Console Link |
|---|---|---|
| **Logs Explorer** | Centralized structured logs | [Logs Explorer](https://console.cloud.google.com/logs/query?project=your-gcp-project-id) |
| **Cloud Trace** | Distributed request latency & spans | [Trace Overview](https://console.cloud.google.com/traces/overview?project=your-gcp-project-id) |
| **Cloud Monitoring** | Custom dashboards & alerting policies | [Monitoring Overview](https://console.cloud.google.com/monitoring?project=your-gcp-project-id) |
| **Error Reporting** | Automatic exception detection | [Error Reporting Console](https://console.cloud.google.com/errors?project=your-gcp-project-id) |

---

## 6. Quick Operational Commands (WSL)

```bash
# Smoke test live endpoints
./scripts/smoke.sh

# View Cloud Run service logs
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="dev-tt-rag-parts"' --limit=20 --project=your-gcp-project-id

# Trigger batch ingestion job execution
gcloud run jobs execute dev-personal-rag-ingest --region=europe-west1 --project=your-gcp-project-id

# Inspect OpenTofu outputs
tofu -chdir=deployment/gcp output
```
