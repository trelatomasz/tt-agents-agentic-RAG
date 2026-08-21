# Implementation Plan - Phased Ingress, Auth & Decoupled Identity Architecture

Document the **Two-Stage Authentication & Ingress Architecture** for the Personal Agentic RAG Platform, formalizing the transition from a streamlined, single-user MVP (Bearer Token in Secret Manager) to the multi-tenant target architecture (Decoupled Centralized Keycloak IAM).

## Architecture Roadmap & Scope Boundaries

### Phase 1: MVP (Single-User, Streamlined GCP Deployment)
- **Scope**: Implemented entirely within `tt-agents-agentic-RAG`.
- **Authentication**: Pre-shared cryptographically secure Bearer Token stored in **GCP Secret Manager** (`RAG_API_BEARER_TOKEN`).
- **Security Middleware**: FastAPI `BearerAuthMiddleware` validating incoming `Authorization: Bearer <token>` and binding single-user context:
  `PrincipalContext(user_id="owner", roles=["owner", "admin"], acl_labels=["owner:tomasz", "visibility:private", "visibility:public"])`.
- **Infrastructure**: Single Cloud Run service (`rag-query-api`), Cloud Run batch job (`rag-ingest-job`), and single Cloud SQL PostgreSQL instance (`rag_db` with `pgvector`).
- **Zero Keycloak Footprint**: Zero Keycloak containers, zero Keycloak databases, and zero Keycloak IaC in this repository.

### Phase 2: Target (Multi-Tenant & Multi-Agent Platform Integration)
- **Scope**: Keycloak is deployed as an **Independent Shared Platform Service** outside this repository.
- **Integration**: `tt-agents-agentic-RAG` operates as a standard, stateless **OAuth2 Resource Server**:
  - FastAPI validates RS256 JWT signatures against the external Keycloak JWKS endpoint (`https://auth.yourdomain.com/.../certs`).
  - Claims dynamically extracted from token: `sub`, `roles`, and multi-tenant `acl_labels`.
  - Same SQL row-level security pushdown (`WHERE acl_labels && :user_labels`) seamlessly scales to multi-tenancy.

---

## Documents to Update in `/docs`

### 1. `docs/c4/01-system-context.md`
- Position Keycloak as an **External Enterprise Shared System** (`System_Ext`) outside the RAG platform boundary.
- Document Phase 1 (MVP Secret Manager Bearer Auth) vs. Phase 2 (Centralized Keycloak OIDC).

### 2. `docs/c4/02-containers.md`
- Remove Keycloak container and `keycloak` database from internal RAG Platform boundary.
- Depict Keycloak as `Container_Ext` in target architecture; document MVP Secret Manager Token authentication in container specifications.

### 3. `docs/c4/04-components-query.md`
- Update `AuthMiddleware` specification to support both **MVP Static Bearer Token Mode** and **Phase 2 Decoupled JWKS OIDC Mode**.
- Document OpenAPI schemas and rate limiting.

### 4. `docs/c4/07-deployment.md`
- Remove Keycloak Cloud Run container and database from the RAG deployment topology.
- Show pure RAG infrastructure: Cloud ALB, Cloud Run API, Cloud Run Ingestion Job, Cloud SQL (`rag_db`), and Secret Manager.

### 5. `docs/personal-rag-spec.md`
- Update Section 4 (Architecture) and Section 6 (API Security) to reflect MVP Bearer Token vs Target Shared Keycloak.

### 6. `docs/adr/0002-api-gateway-and-ingress-architecture.md`
- Update ADR-002 with the decision to decouple Keycloak into shared platform infra and use Secret Manager Bearer auth for MVP.
