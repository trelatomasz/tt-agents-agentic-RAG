# Section 005: Read-Only FastMCP Agent Server

- **Module**: Model Context Protocol (MCP) Read-Only Server
- **Status**: `PENDING`
- **Assigned Subagent**: Agent Integration Subagent
- **Dependencies**: [`004-section-fastapi-query-service.md`](004-section-fastapi-query-service.md)
- **Target Files**:
  - `src/personal_rag/mcp/server.py` (Pending)
  - `src/personal_rag/mcp/tools.py` (Pending)
  - `tests/personal_rag/test_mcp.py` (Pending)

---

## 1. Objectives & Scope
Implement an independent, read-only Model Context Protocol (MCP) server using FastMCP over Server-Sent Events (SSE) and HTTP streaming, enabling autonomous AI agents to query evidence without direct database access or write permissions.

## 2. Checklist & Deliverables
- [ ] Implement FastMCP application entry point in `src/personal_rag/mcp/server.py`.
- [ ] Implement read-only tool handlers:
  - `rag_search(query: str, top_k: int = 5, source_ids: List[str] = None)`
  - `rag_answer(query: str, token_budget: int = 4000)`
  - `rag_sources()`
  - `rag_ingestion_status()`
- [ ] Implement Bearer token credential propagation from MCP agent request down to Query Service API.
- [ ] Verify zero write or database mutation tools are exposed.
- [ ] Write integration test suite verifying agent tool invocations over HTTP/SSE.

## 3. Changes Implemented & Verification
- Architecture specified in [`ADR-002`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/docs/adr/0002-api-gateway-and-ingress-architecture.md) and [`docs/c4/04-components-query.md`](file:///d:/src/tt-agents-agentic-RAG.gh.public.git/docs/c4/04-components-query.md).

## 4. Next / Follow-Up Sections
- Deployed via [`007-section-deployment-and-infrastructure.md`](007-section-deployment-and-infrastructure.md).
