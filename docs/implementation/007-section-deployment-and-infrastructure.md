# Section 007: GCP Infrastructure & OpenTofu Deployment

- **Module**: GCP OpenTofu Infrastructure & Edge Gateway
- **Status**: `IN_PROGRESS`
- **Assigned Subagent**: Infrastructure Subagent
- **Dependencies**: All upstream application sections ([`001`](001-section-contracts-and-models.md) through [`006`](006-section-ci-cd-and-cli-tools.md))
- **Target Files**:
  - [`deployment/gcp/main.tf`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/deployment/gcp/main.tf)
  - [`deployment/gcp/services.tf`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/deployment/gcp/services.tf)
  - [`deployment/gcp/sql.tf`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/deployment/gcp/sql.tf)
  - `deployment/gcp/alb.tf` (Pending)
  - `deployment/gcp/armor.tf` (Pending)

---

## 1. Objectives & Scope
Provision Google Cloud Platform serverless compute, Cloud SQL PostgreSQL 16 instance with `pgvector`, versioned Cloud Storage buckets, Secret Manager secrets, Workload Identity Federation (WIF) pools, and Global Application Load Balancer (ALB) with Cloud Armor WAF.

## 2. Checklist & Deliverables
- [x] [DONE] Cloud Run Query Service (`dev-tt-rag-parts`) OpenTofu configuration.
- [x] [DONE] Cloud Run Batch Ingestion Job (`dev-personal-rag-ingest`) OpenTofu configuration.
- [x] [DONE] Cloud SQL PostgreSQL 16 instance with `pgvector` extension and Secret Manager credential binding.
- [x] [DONE] Versioned Cloud Storage buckets for catalog and raw/normalized artifacts.
- [x] [DONE] Keyless GitHub Actions Workload Identity Federation (WIF) pool and provider.
- [ ] Implement Global External Application Load Balancer (`alb.tf`) with Serverless NEGs for `/v1/*` and `/mcp/*`.
- [ ] Implement Cloud Armor Security Policy (`armor.tf`) for Layer-7 rate limiting (120 req/min) and SQLi/XSS WAF rules.
- [ ] Provision dedicated Cloud Run service definition for `rag-mcp-server`.

## 3. Changes Implemented & Verification
- OpenTofu modules active in `deployment/gcp/`.
- Verified syntax with `tofu validate` (in WSL environment).

## 4. Next / Follow-Up Sections
- Upstream dependency for [`008-section-evaluation-and-observability.md`](008-section-evaluation-and-observability.md).
