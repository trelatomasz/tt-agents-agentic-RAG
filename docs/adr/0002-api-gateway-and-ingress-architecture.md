# ADR-002: Selection of Cloud Application Load Balancer & Cloud Armor as Edge API Gateway

- **Status**: Approved
- **Deciders**: Platform Architecture Team
- **Date**: 2026-08-21
- **Technical Scope**: Public & Internal Ingress, SSL Termination, WAF/DDoS Protection, Path Routing, and Zero-Trust Authorization.

---

## 1. Context & Problem Statement

The Personal Agentic RAG Platform hosts containerized services on GCP Cloud Run:
1. **Query Service API (`rag-query-api`)**: Stateless FastAPI application executing hybrid retrieval, rank fusion, and grounded answer synthesis.
2. **Read-Only MCP Server (`rag-mcp-server`)**: FastMCP adapter exposing streamable Server-Sent Events (SSE) and HTTP tools to autonomous AI agents.

Identity and Access Management follows a two-stage evolutionary strategy:
- **Phase 1 (MVP)**: Streamlined single-user deployment authenticated via pre-shared cryptographically secure Bearer tokens retrieved from **GCP Secret Manager**. Zero Keycloak operational overhead in this repository.
- **Phase 2 (Target)**: Decoupled integration with a **Centralized Shared Keycloak IAM Server** (managed in separate shared infrastructure) serving multiple agent repositories. The RAG service operates purely as a stateless OAuth2 Resource Server validating RS256 JWTs via public JWKS.

We need an ingress and API gateway layer to:
- Terminate TLS with automated Google-managed SSL certificates on custom domains (e.g. `api.rag.example.com`).
- Protect against DDoS attacks, automated scraping bots, and brute-force attempts via web application firewall (WAF) rules and rate limiting.
- Perform efficient, low-latency path-based routing (`/v1/*`, `/mcp/*`) to the backend Cloud Run containers without adding cold-start latency or excessive operational overhead.
- Maintain cost-effectiveness and serverless elasticity (scaling to zero when idle).

---

## 2. Considered Alternatives

| Evaluation Criteria | Option 1: Global External Application Load Balancer (HTTPS) + Cloud Armor (Selected) | Option 2: Self-Hosted API Gateway Container (Kong / Apache APISIX / Envoy on Cloud Run) | Option 3: GCP Cloud Endpoints / API Gateway (Managed) | Option 4: Direct Cloud Run Public Ingress (No Gateway) |
|---|---|---|---|---|
| **Operational Overhead** | **Zero-maintenance**: Fully managed GCP networking infrastructure. | **High**: Requires maintaining custom gateway container, plugins, and configuration synchronization. | **Medium**: Requires OpenAPI spec translation; limited support for SSE/streaming and custom WAF. | **Low**: But exposes raw Cloud Run URLs directly to the internet with no unified domain. |
| **DDoS & WAF Capabilities** | **Superior**: Google Cloud Armor provides Layer 7 WAF, rate limiting, and edge IP filtering. | **Software-level**: Dependent on gateway plugin performance; traffic hits container directly. | **Basic**: Limited rate limiting without native Cloud Armor integration. | **None**: Basic GCP DDoS only; no custom WAF or rate limiting. |
| **SSL Management** | **Automated**: Free Google-managed multi-domain SSL certificates with auto-renewal. | **Manual / Let's Encrypt**: Requires custom cert manager sidecars or certbot routines. | **Automated**: Managed certificates per gateway config. | **Automated**: Default `*.run.app` certificates only. |
| **Cost Profile** | **Low & Predictable**: Standard forwarding rule (~$18/mo) + Cloud Armor Standard ($0.75/policy). | **Medium**: Continuous container instance execution + CPU allocation costs ($15–$30/mo). | **Pay-per-call**: $3.00 per million calls after free tier. | **Zero extra**: Free default ingress. |
| **SSE / Streaming Support** | **Full**: Native support for HTTP/2, WebSockets, and long-lived SSE connections for FastMCP. | **Full**: Supports streaming if configured properly. | **Limited**: Buffers responses; breaks SSE streaming in some configurations. | **Full**: Native HTTP streaming on Cloud Run. |

---

## 3. Decision

We choose **Option 1: Global External Application Load Balancer (HTTPS) with Serverless NEGs + Cloud Armor WAF**:

1. **Unified Custom Domain & Edge Routing**:
   - Single global Anycast IP terminating TLS at Google's global edge network.
   - URL Maps route traffic cleanly:
     - `api.yourdomain.com/v1/*` $\rightarrow$ `rag-query-api` Serverless NEG
     - `api.yourdomain.com/mcp/*` $\rightarrow$ `rag-mcp-server` Serverless NEG
     - `api.yourdomain.com/health` $\rightarrow$ Query API health check
2. **Cloud Armor Security Policy**:
   - Edge rate limiting: Max 120 requests/minute per client IP for public `/v1/*` endpoints.
   - SQLi / XSS rule sets enabled via preconfigured WAF rules (`cve-canary`, `sqli-canary`).
   - Private IP blocking and optional geo-fencing (restricting administrative access to operator countries).
3. **Pluggable Two-Phase Authorization in FastAPI**:
   - **MVP**: Constant-time verification of `Authorization: Bearer <token>` matching `RAG_API_BEARER_TOKEN` in Secret Manager.
   - **Target**: Cryptographic signature verification against the external shared Keycloak JWKS endpoint (`https://auth.yourdomain.com/.../certs`) with in-memory caching.
   - Decouples identity lifecycle completely from this repository.

---

## 4. Consequences

### Positive
- **Instant Response & Zero Cold Starts at Gateway**: Google Cloud Load Balancing is always active globally; incoming connections terminate at the nearest edge point of presence (PoP).
- **Hardened Edge Defense**: Malicious traffic and rate-limit violations are dropped at the edge before consuming Cloud Run compute or database queries.
- **FastMCP SSE Compatibility**: Streaming responses for agents work seamlessly over HTTP/2 and long-lived HTTPS streams.
- **Clean Architecture**: All services reside behind a single, cohesive brand domain with standard ports (`443`).

### Negative / Trade-offs
- **Fixed Monthly Base Cost**: Global Forwarding Rule incurs a small baseline cost (~$18/month). For purely local development or testing, developers use the local in-process memory topology (`MemoryIndex`) with zero cloud cost.
