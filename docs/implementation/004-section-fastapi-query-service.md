# Section 004: FastAPI Query Service & Auth Middleware

- **Module**: FastAPI Grounded Query API
- **Status**: `IN_PROGRESS`
- **Assigned Subagent**: API Subagent
- **Dependencies**: [`003-section-database-and-vector-store.md`](003-section-database-and-vector-store.md)
- **Target Files**:
  - [`src/personal_rag/query/service.py`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/src/personal_rag/query/service.py)
  - [`src/personal_rag/query/grounding.py`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/src/personal_rag/query/grounding.py)
  - `src/personal_rag/api/auth.py` (Pending)
  - `src/personal_rag/api/routes.py` (Pending)

---

## 1. Objectives & Scope
Implement stateless FastAPI REST query endpoints (`/v1/search`, `/v1/answer`), pluggable two-phase Bearer auth middleware (Secret Manager MVP & Keycloak JWKS target), Reciprocal Rank Fusion (RRF), claim-level grounding validation, and strict abstention gates.

## 2. Checklist & Deliverables
- [x] [DONE] Implemented core query service logic and grounding validation in `src/personal_rag/query/`.
- [x] [DONE] Abstention gate and citation presence validation tests implemented.
- [ ] Implement `UnifiedAuthMiddleware` (Secret Manager Bearer token check for MVP + Keycloak JWKS JWT for Target).
- [ ] Implement generic FastAPI endpoints `/v1/search` and `/v1/answer` returning Pydantic response models.
- [ ] Implement Vertex AI `text-embedding-004` and Gemini 2.5 Flash integrations under `USE_VERTEX=true`.
- [ ] Implement sliding-window rate limiting per IP/user (`120 req/min`).

## 3. Changes Implemented & Verification
- GPC parts query service functional in `src/gpc_rag/service.py`.
- Generic query service core functional in `src/personal_rag/query/service.py`.
- **Verification**: `pytest tests/personal_rag/test_query_service.py` passes.

## 4. Next / Follow-Up Sections
- Upstream dependency for [`005-section-fastmcp-agent-server.md`](005-section-fastmcp-agent-server.md).
