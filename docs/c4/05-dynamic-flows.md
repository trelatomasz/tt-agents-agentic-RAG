# C4 Dynamic Flows: Use Cases & Sequence Diagrams

This document specifies the **Dynamic Behavioral Architecture** of the Personal Agentic RAG Platform, providing end-to-end sequence diagrams and failure handling flows for the **8 core platform use cases**.

---

## 1. End-to-End Grounded Q&A Flow

```plantuml
@startuml "05-dynamic-flows"
autonumber
skinparam BoxPadding 10
skinparam ParticipantPadding 10

title Dynamic Flow: Hybrid Search & Grounded Q&A with Keycloak Verification

actor "Knowledge Owner / Agent" as Client
box "Query Service API (FastAPI)" #f8f9fa
    participant "FastAPI Router" as Router
    participant "JWT Guard" as Guard
    participant "Hybrid Retriever" as Retriever
    participant "RRF & Evidence Mgr" as Fusion
    participant "Abstention Gate" as Gate
    participant "Model Router" as LLMRouter
    participant "Citation Validator" as Validator
end box

participant "Keycloak IAM" as Keycloak
database "Cloud SQL\n(pgvector + FTS)" as DB
participant "vLLM Endpoint\n(Fine-Tuned LLM)" as vLLM
participant "Vertex AI\n(Gemini 2.5 Flash)" as Gemini

Client -> Router: POST /v1/answer {query, token_budget}\nAuthorization: Bearer <JWT>
activate Router

Router -> Guard: Validate Bearer JWT
activate Guard
Guard -> Keycloak: Fetch / Verify JWKS (Cached in-memory)
Keycloak --> Guard: Public Key Set
Guard --> Router: PrincipalContext(user_id, acl_labels=["owner:tomasz", "group:dev"])
deactivate Guard

Router -> Retriever: hybrid_search(query, acl_labels)
activate Retriever

par Sparse & Dense Retrieval
    Retriever -> DB: SELECT chunks WHERE acl_labels && user_labels\nORDER BY ts_rank(tsv, q) LIMIT 50
    Retriever -> DB: SELECT chunks WHERE acl_labels && user_labels\nORDER BY cosine_distance(vec, q_emb) LIMIT 50
end
DB --> Retriever: Sparse & Dense Candidate Sets
Retriever --> Fusion: raw_candidates
deactivate Retriever

activate Fusion
Fusion -> Fusion: Compute Reciprocal Rank Fusion (k=60)
Fusion -> Fusion: Apply Token Budget & Deduplicate
Fusion --> Gate: top_k_evidence_chunks
deactivate Fusion

activate Gate
alt Retrieval Score < Threshold (0.35) or Empty Evidence
    Gate --> Router: AbstentionResponse("I do not have sufficient verified evidence.")
    Router --> Client: 200 OK (Abstained = true)
else Evidence Sufficient
    Gate --> LLMRouter: approved_chunks + system_prompt
    deactivate Gate
    
    activate LLMRouter
    alt Standard Grounded Synthesis
        LLMRouter -> vLLM: Generate Answer with XML Grounding Context
        vLLM --> LLMRouter: Raw Completion + [chunk_id] Citations
    else Complex Multi-Hop Synthesis
        LLMRouter -> Gemini: Generate Answer with Gemini Flash
        Gemini --> LLMRouter: Raw Completion + [chunk_id] Citations
    end
    
    LLMRouter -> Validator: validate_citations(raw_completion, approved_chunks)
    activate Validator
    Validator -> Validator: Verify all [chunk_ids] exist in evidence
    Validator --> Router: VerifiedAnswer(text, citations, provenance)
    deactivate Validator
    deactivate LLMRouter
    
    Router --> Client: 200 OK {answer, citations, metadata}
end

deactivate Router
@enduml
```

---

## 2. Use Case 1: Local Ebooks (PDF/EPUB) Ingestion

**Trigger**: Owner runs `python -m personal_rag.ingest.filesystem --path 'ebooks/' --source-id ebooks --manifest '.rag/manifest.json'`.

```plantuml
@startuml "05-uc1-ebook-ingestion"
autonumber
skinparam BoxPadding 10
skinparam ParticipantPadding 10

title Use Case 1: Local Ebooks (PDF/EPUB) Ingestion

actor "Knowledge Owner" as Owner
participant "Ingestion CLI" as CLI
participant "Local Filesystem" as FS
participant "PDF/EPUB Parser" as Parser
participant "Ingestion Pipeline" as Pipe
database "Cloud Storage" as GCS
database "Cloud SQL (pgvector)" as SQL

Owner -> CLI: Execute ingest command (--manifest, --changed-only)
CLI -> FS: Scan folder (guarding against junction escapes)
FS --> CLI: File list (.pdf, .epub, .md)

loop For Each Discovered File
    CLI -> CLI: Compute SHA-256 hash & check manifest
    alt Content Hash Unchanged
        CLI -> CLI: Mark SKIPPED in manifest
    else New or Modified File
        CLI -> Parser: Parse file
        alt PDF Document
            Parser -> Parser: Extract text page-by-page (record page locators)
        else EPUB Document
            Parser -> Parser: Extract chapters from spine (record chapter locators)
        end
        Parser --> CLI: RawDocument + Locators
        CLI -> Pipe: Normalize, Chunk & Enrich
        Pipe --> CLI: Chunks with heading paths & locators
        CLI -> GCS: Upload raw file & normalized snapshot
        CLI -> SQL: Stage chunks in candidate batch
        CLI -> CLI: Record file status as PROCESSED in manifest
    end
end

CLI --> Owner: Display ingestion summary (Processed, Skipped, Errors)

@enduml
```

---

## 3. Use Case 2: Web Article Ingestion with SSRF Protection

**Trigger**: Ingestion of an approved technical article via `python -m personal_rag.ingest.web --url 'https://docs.cloud.google.com/...'`.

```plantuml
@startuml "05-uc2-web-ingestion"
autonumber
skinparam BoxPadding 10
skinparam ParticipantPadding 10

title Use Case 2: Web Article Ingestion with SSRF Protection

actor "Knowledge Owner" as Owner
participant "Web Adapter" as WebAdapter
participant "DNS Resolver / SSRF Guard" as DNS
participant "Target Web Host" as WebHost
participant "HTML Extractor" as Extractor
participant "Pipeline & Index" as Pipe

Owner -> WebAdapter: Ingest URL (https://example.com/doc)
WebAdapter -> DNS: Resolve Hostname
DNS --> WebAdapter: Resolved IP Addresses

alt IP is Private / Loopback / Metadata (169.254.169.254)
    WebAdapter --> Owner: REJECT: SSRF violation (Forbidden IP range)
else Public IP Address
    WebAdapter -> WebHost: GET /robots.txt
    WebHost --> WebAdapter: robots.txt rules
    alt Scraping Disallowed by robots.txt
        WebAdapter --> Owner: REJECT: Policy violation (robots.txt blocked)
    else Scraping Allowed
        WebAdapter -> WebHost: GET /doc (Timeout 15s, Max 10MB)
        WebHost --> WebAdapter: HTTP 200 (HTML Content + ETag)
        WebAdapter -> Extractor: Extract article body, headings, metadata
        Extractor --> WebAdapter: Clean Markdown + URL locators
        WebAdapter -> Pipe: Send RawDocument for chunking & embedding
        Pipe --> Owner: Success: Article indexed with canonical URL provenance
    end
end

@enduml
```

---

## 4. Use Case 3: `tt-root/info` Git-Aware Knowledge Ingestion

**Trigger**: Ingestion of canonical reference notes from local/remote Git repository.

```plantuml
@startuml "05-uc3-git-sync"
autonumber
skinparam BoxPadding 10
skinparam ParticipantPadding 10

title Use Case 3: tt-root/info Git-Aware Knowledge Ingestion

participant "GitTree Adapter" as Adapter
participant "Git Repo (tt-root/info)" as Git
participant "Normalizer & Chunker" as Pipe
database "Cloud SQL" as SQL

Adapter -> Git: Read Git HEAD commit SHA & working tree
Git --> Adapter: Current commit SHA: "a1b2c3d4", file tree

loop For Each Markdown & YAML File
    Adapter -> Git: Read file contents & path
    Git --> Adapter: Markdown text
    Adapter -> Adapter: Extract Level-1 title & detect language (EN/PL)
    Adapter -> Pipe: Build DocumentVersion(source_revision="a1b2c3d4")
    Pipe -> Pipe: Structure-aware chunking by heading hierarchy
    Pipe -> SQL: Insert chunks with locator_json={"git_commit": "a1b2c3d4", "path": "notes/..."}
end
SQL --> Adapter: Batch inserted successfully

@enduml
```

---

## 5. Use Case 4: Project Repository CI/CD Indexing

**Trigger**: GitHub Actions workflow runs on commit push to `main`.

```plantuml
@startuml "05-uc4-ci-indexing"
autonumber
skinparam BoxPadding 10
skinparam ParticipantPadding 10

title Use Case 4: Project Repository CI/CD Indexing

participant "GitHub Actions Runner" as GHA
participant "GCP Workload Identity (WIF)" as WIF
participant "rag-index CLI" as CLI
participant "Git Workspace" as Git
participant "Query/Ingest Service" as IngestAPI
database "Cloud SQL" as SQL

GHA -> WIF: Exchange GitHub OIDC token for short-lived GCP token
WIF --> GHA: Federated GCP OAuth2 Token

GHA -> CLI: rag-index publish --commit $GITHUB_SHA --changed-only
CLI -> Git: git diff --name-status HEAD~1 HEAD
Git --> CLI: List of Added (A), Modified (M), Deleted (D) files

CLI -> CLI: Filter files against .ragignore

loop For Added / Modified Files
    CLI -> CLI: Chunk code/docs & enrich with Git commit & lines
end

loop For Deleted Files
    CLI -> CLI: Create deletion tombstones (DocumentStatus=DELETED)
end

CLI -> IngestAPI: POST /v1/ingest/publish (Signed Manifest + Chunks)
IngestAPI -> SQL: Execute batch insert & tombstone update
SQL --> IngestAPI: Transaction committed
IngestAPI --> CLI: HTTP 200 OK (Run ID: run-9876)
CLI --> GHA: Ingestion complete. Run logged in build summary.

@enduml
```

---

## 6. Use Case 5: Hybrid Search Execution with SQL Pre-Filtering

**Trigger**: User or agent submits `POST /v1/search` with query and source filters.

```plantuml
@startuml "05-uc5-hybrid-search"
autonumber
skinparam BoxPadding 10
skinparam ParticipantPadding 10

title Use Case 5: Hybrid Search Execution with SQL Pre-Filtering

actor "User / Agent" as Caller
participant "Query Service API" as API
participant "Vertex AI" as Vertex
database "Cloud SQL (pgvector)" as SQL

Caller -> API: POST /v1/search {"query": "vector indexing", "source_ids": ["ebooks", "tt-root-info"]}
API -> API: Authenticate caller & resolve authorized ACL labels

par Generate Dense Vector
    API -> Vertex: Generate text embedding for query
    Vertex --> API: 768-dim float32 vector
and Build Sparse Query
    API -> API: Generate tsquery("vector & indexing")
end

API -> SQL: Execute Unified Hybrid SQL Query (WHERE acl_labels && user_labels)
note over SQL
  Evaluates Sparse ts_rank_cd & Dense <=> cosine in parallel,
  fuses rankings using RRF: 1/(60 + rank_sparse) + 1/(60 + rank_dense)
end note
SQL --> API: Top-K Ranked Chunks + Provenance + RRF Scores

API --> Caller: SearchResponse (Ranked chunks, source locators, scores, execution_time_ms)

@enduml
```

---

## 7. Use Case 6: Grounded Q&A with Strict Abstention

**Trigger**: User submits `POST /v1/answer` to obtain a factual, cited response.

```plantuml
@startuml "05-uc6-grounded-qa"
autonumber
skinparam BoxPadding 10
skinparam ParticipantPadding 10

title Use Case 6: Grounded Q&A with Strict Abstention

actor "Researcher" as User
participant "Query Service API" as API
participant "Hybrid Search Engine" as Search
participant "Abstention Gate" as Gate
participant "Vertex AI Gemini" as LLM
participant "Citation Validator" as Val

User -> API: POST /v1/answer {"query": "How is rollback handled?"}
API -> Search: Execute hybrid search for query
Search --> API: Retrieved candidate chunks

alt Max Retrieval Score < Min Threshold OR Zero Candidates
    API -> Gate: Trigger Abstention
    Gate --> API: Abstain response
    API --> User: {"answer": "Insufficient verified evidence.", "status": "abstained", "citations": []}
else Sufficient Evidence Retrieved
    API -> API: Assemble delimited context & token budget (max 4000 tokens)
    API -> LLM: Prompt Gemini (temperature=0.0, strict grounding)
    LLM --> API: Raw completion text with embedded [chunk-id] tags
    
    API -> Val: Validate citations & claim entailment
    alt LLM Fabricated Invalid Chunk IDs
        Val --> API: REJECT: Ungrounded synthesis
        API --> User: Fallback: Raw evidence snippets with warning
    else Citations Valid & Verified
        Val --> API: Verified Answer + Structured Citation Objects
        API --> User: HTTP 200 {"answer": "...", "status": "grounded", "citations": [...]}
    end
end

@enduml
```

---

## 8. Use Case 7: Read-Only AI Agent MCP Interaction

**Trigger**: Autonomous IDE Agent (Google Antigravity, Claude Code) needs project knowledge.

```plantuml
@startuml "05-uc7-agent-mcp"
autonumber
skinparam BoxPadding 10
skinparam ParticipantPadding 10

title Use Case 7: Read-Only AI Agent MCP Interaction

participant "Autonomous IDE Agent" as Agent
participant "Read-Only MCP Server" as MCP
participant "Query Service API" as API
database "Cloud SQL" as SQL

Agent -> MCP: ListTools()
MCP --> Agent: Available tools: [rag_search, rag_answer, rag_sources, rag_ingestion_status]

Agent -> MCP: CallTool("rag_search", {"query": "GCP Cloud SQL pgvector configuration"})
MCP -> API: POST /v1/search (Forward with Agent IAM Identity)
API -> SQL: Pre-filtered hybrid search
SQL --> API: Relevant chunks
API --> MCP: SearchResponse
MCP --> Agent: ToolResult (Ranked chunks + exact locators)

note over Agent: Agent incorporates verified facts into its generation plan

@enduml
```

---

## 9. Use Case 8: Candidate Index Rebuild, Evaluation & Rollback

**Trigger**: Batch ingestion completes a new corpus index; platform validates before live swap.

```plantuml
@startuml "05-uc8-index-activation"
autonumber
skinparam BoxPadding 10
skinparam ParticipantPadding 10

title Use Case 8: Candidate Index Rebuild, Evaluation & Rollback

actor "Platform Engineer" as Dev
participant "Batch Ingestion Job" as Job
participant "Evaluation Gate" as Eval
database "Cloud SQL" as SQL
participant "Query Service API" as LiveAPI

Dev -> Job: Trigger batch index rebuild
Job -> SQL: Insert document versions & chunks under run_id="run-20260819-02" (Status=CANDIDATE)

Job -> Eval: Execute Golden & Negative Test Suites against run-20260819-02
alt Evaluation Gate Fails (Negative Query Answered or Recall < 90%)
    Eval --> Job: FAIL: Quality threshold missed
    Job -> SQL: UPDATE ingestion_runs SET status='QUARANTINED' WHERE run_id='run-20260819-02'
    Job --> Dev: Alert: Candidate index quarantined. Active pointer unchanged.
    else Evaluation Gate Passes (100% Negative Precision, Recall >= 90%)
    Eval --> Job: PASS: Release gate cleared
    Job -> SQL: BEGIN TRANSACTION; UPDATE active_index_pointers SET active_run_id='run-20260819-02'; COMMIT;
    SQL --> Job: Pointer swapped atomically
    Job --> Dev: Success: Index run-20260819-02 is now LIVE.
    
    opt Emergency Rollback Needed
        Dev -> SQL: UPDATE active_index_pointers SET active_run_id='run-previous-stable';
        SQL --> LiveAPI: Live queries instantly route back to prior index version
    end
end

@enduml
```

---

## 10. Use Case 9: Edge Ingress, Authentication Handshake & Token Refresh

**Trigger**: Human researcher logs in via Web SSO or Autonomous Agent acquires/refreshes machine client credentials token.

```plantuml
@startuml "05-uc9-edge-auth-flow"
autonumber
skinparam BoxPadding 10
skinparam ParticipantPadding 10

title Use Case 9: Edge Ingress, Authentication Handshake & Token Lifecycle

actor "Human / Agent Client" as Client
box "Edge Ingress Tier" #e3f2fd
    participant "Cloud Armor WAF" as WAF
    participant "Cloud Application Load Balancer" as ALB
end box

box "GCP Compute Services" #f5f5f5
    participant "Keycloak IAM (Cloud Run)" as Keycloak
    participant "Query API (Cloud Run)" as API
end box

database "Cloud SQL (Keycloak DB)" as KC_DB

== 1. Agent / Machine Token Issuance ==
Client -> WAF: POST /auth/realms/personal-rag/protocol/openid-connect/token\n(grant_type=client_credentials, client_id, client_secret)
WAF -> WAF: Check Rate Limit (max 30 req/min)
WAF -> ALB: Forward Validated Request
ALB -> Keycloak: Route to keycloak-iam Serverless NEG
Keycloak -> KC_DB: Validate client credentials & lookup ACL scopes
KC_DB --> Keycloak: Scopes: ["owner:tomasz", "group:dev", "visibility:private"]
Keycloak --> Client: 200 OK {access_token: <RS256 JWT>, expires_in: 3600}

== 2. Authenticated Query Ingress & Execution ==
Client -> WAF: POST /v1/search {query: "pgvector HNSW"}\nAuthorization: Bearer <RS256 JWT>
WAF -> WAF: Rate Limit Check (max 120 req/min) & SQLi/XSS Scan
WAF -> ALB: Forward Clean Request
ALB -> API: Route to rag-query-api Serverless NEG
API -> API: Verify JWT Signature via cached JWKS & extract acl_labels
API -> API: Execute hybrid search with SQL pushdown
API --> Client: 200 OK {results: [...], execution_time_ms: 112}

== 3. Token Expiration & Refresh ==
Client -> WAF: POST /auth/realms/personal-rag/protocol/openid-connect/token\n(grant_type=refresh_token, refresh_token=...)
WAF -> ALB: Forward Request
ALB -> Keycloak: Route to keycloak-iam Serverless NEG
Keycloak --> Client: 200 OK {access_token: <New JWT>, refresh_token: <New Refresh>}

@enduml
```

