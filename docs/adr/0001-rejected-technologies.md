# Architecture Decision Record (ADR) 001: Rejected Technologies & Trade-Off Analysis

> **Status**: Accepted / Active Record  
> **Date**: 2026-08-19  
> **Scope**: Technology evaluation and rejection rationale across Data, AI, Security, Compute, and Evaluation tiers.  
> **Note**: In accordance with project standards, this document focuses **exclusively on rejected technologies and alternatives**, detailing the explicit technical and operational reasons they were rejected.

---

## 1. Vector Database Tier

### 1.1 Pinecone (Managed SaaS Vector DB)
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Cross-Cloud & Network Ingress Penalty**: Hosted outside the Google Cloud VPC, introducing public Internet or private interconnect latency (adding 40–80 ms per query round-trip) and extra egress bandwidth costs.
  2. **Decoupled Relational & Vector Metadata**: Requires maintaining a separate relational database for document versions, ACLs, and ingestion runs, leading to dual-write consistency issues and distributed transactions.
  3. **Vendor Lock-In & Cost Scaling**: Closed-source SaaS with pricing tied to pod hours and vector counts, making idle development environments and multi-environment dev/test deployments unnecessarily costly compared to consolidated Cloud SQL instances.
  4. **Lack of In-Database ACL Pre-Filtering**: Cannot execute atomic SQL `WHERE acl_labels && :user_labels` joined directly against relational provenance tables prior to distance calculation.

### 1.2 Weaviate & Qdrant (Dedicated Vector Engines)
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Operational Overhead of a Second Stateful Cluster**: Running a dedicated Weaviate or Qdrant cluster on GKE or Compute Engine requires node provisioning, persistent volume backups, distributed shard management, and custom monitoring pipelines.
  2. **Memory Footprint**: High base RAM overhead for JVM/Go/Rust engines just to maintain baseline availability for a personal knowledge corpus (~50,000–500,000 chunks).
  3. **Dual-Store Synchronization Complexity**: Document metadata, revision hashes, and deletion tombstones must be synchronized between PostgreSQL and the vector engine across failure and rollback scenarios.

### 1.3 ChromaDB & Milvus
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **ChromaDB**: Lacks enterprise-grade multi-client transactional concurrency, robust crash recovery, and mature SQL indexing for production Cloud Run workloads. Primarily designed for single-process prototyping.
  2. **Milvus**: Extreme infrastructure complexity (requires etcd, MinIO, Pulsar/Kafka, and coordinator/worker nodes), creating disproportionate operational toil for small-to-medium scale agentic RAG.

---

## 2. LLM Orchestration & Agent Frameworks

### 2.1 LangChain
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Opaque & Leaky Abstractions**: Heavy layer of nested classes and dynamic runtime wrappers that obscure HTTP calls, error handling, and prompt structures.
  2. **Breaking API Churn**: Frequent major version releases with breaking changes, deprecated imports, and unversioned runtime dependencies.
  3. **Debugging & Latency Overhead**: Substantial execution overhead and deep call stacks make profiling, token budgeting, and hermetic offline unit testing difficult.
  4. **Violation of 12-Factor Decoupling**: Embeds vendor-specific query mechanics directly into agent pipelines rather than exposing clean, typed interfaces.

### 2.2 LlamaIndex
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Opinionated Index Monolith**: Tightly binds parsing, chunking, indexing, and querying into a single opaque framework. Does not provide clean separation between candidate index runs and atomic pointer swaps.
  2. **Rigid Query-Time Assumptions**: Imposes custom node/index abstractions that conflict with strict SQL-level ACL filtering, Reciprocal Rank Fusion (RRF), and custom structured locator provenance schemas.

### 2.3 AutoGen & CrewAI (Multi-Agent Swarm Frameworks)
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Unbounded Autonomy & Cost Risk**: Autonomous agent swarms with non-deterministic inter-agent dialogue loops lead to explosive token consumption, unpredictable latency (15s–60s+), and uncontrolled tool recursion.
  2. **Violation of Autonomy Boundary**: Violates the repository's strict autonomy policy (Section 2 & Threat Model), which mandates deterministic hybrid retrieval and bounded generation over unconstrained agent loops.
  3. **Auditability Gaps**: Multi-agent chat protocols lack strict, single-turn citation verification and atomic rollback guarantees.

### 2.4 Haystack (Deepset)
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Pipeline Graph Rigidity**: The DAG pipeline execution model introduces unnecessary abstraction overhead for simple, deterministic linear RAG flows (Normalize $\rightarrow$ Chunk $\rightarrow$ Enrich $\rightarrow$ Embed $\rightarrow$ Candidate).
  2. **Duplicate Interface Layer**: Replaces standard Python asynchronous protocols with proprietary node/component classes, hindering direct control over GCP SDKs.

---

## 3. Identity, Authentication & Security Tier

### 3.1 Auth0 / Okta (SaaS Identity Providers)
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Cost at Scale & Per-MAU Pricing**: High recurring monthly active user (MAU) and enterprise tier costs for advanced features (custom token claims, multiple realms, agent service accounts).
  2. **Third-Party SaaS Data Residency**: User identities, session tokens, and access logs reside outside self-controlled infrastructure.
  3. **Offline Development Incompatibility**: Cannot easily run a lightweight, hermetic local container during air-gapped or local workstation development.

### 3.2 Firebase Authentication / Google Identity Platform
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Limited Custom Claims Flexibility**: Strict 1,000-byte limit on custom JWT claims makes injecting rich, granular ACL label arrays (`acl_labels = ["owner:tomasz", "group:dev", "project:alpha", ...]`) fragile.
  2. **GCP Proprietary Lock-In**: Tightly couples identity management to Google Cloud, preventing portable multi-cloud or local workstation identity federation.
  3. **Restricted Client Credentials / Machine-to-Machine Flow**: Cumbersome setup for issuing short-lived agent/CI machine tokens compared to standard Keycloak service accounts.

---

## 4. Search & Indexing Engines

### 4.1 Elasticsearch & OpenSearch
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **JVM Memory & Instance Sizing**: Requires dedicated compute instances with at least 4–8 GB RAM for master/data nodes, creating constant baseline infrastructure cost even during periods of zero query activity.
  2. **Secondary Index Maintenance**: Introduces the exact same dual-store split-brain risk as dedicated vector databases—every document version, update, and deletion tombstone must be synchronized across both stores.
  3. **Query Engine Duplication**: PostgreSQL native `tsvector` with `pg_trgm` and BM25 ranking already delivers sub-50ms lexical retrieval for corpora up to 1,000,000 chunks without a separate search cluster.

### 4.2 Apache Solr
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **High Operational Complexity**: Requires Apache ZooKeeper for cluster coordination, complex XML schema configurations, and heavy resource commitments.

---

## 5. Ingestion Orchestration & Queueing

### 5.1 Celery + RabbitMQ / Redis
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Always-On Worker Compute**: Requires running continuously active Celery worker processes and a persistent message broker (RabbitMQ/Redis), violating the scale-to-zero operational principle.
  2. **Complex State Reconciliation**: Managing task retries, task deduplication, and candidate index aggregation across distributed workers is far more complex than invoking a single ephemeral Cloud Run Job.

### 5.2 Apache Kafka
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Massive Over-Engineering**: Designed for high-throughput streaming (millions of events/sec). Batch and incremental knowledge ingestion operates on discrete file sets and Git commits, where Cloud Run Jobs and Cloud Storage manifests provide superior traceability and zero baseline cost.

---

## 6. Evaluation Platforms & Tooling

### 6.1 Proprietary Closed-SaaS Evaluation Platforms
- **Status**: **REJECTED**
- **Rejection Rationale**:
  1. **Exfiltration of Sensitive Knowledge**: Submitting full prompts, retrieved personal notes, and model outputs to third-party SaaS evaluation clouds violates the zero-leakage security mandate.
  2. **Opaque Scoring Methodologies**: Black-box proprietary evaluation metrics cannot be inspected, version-pinned in git, or executed hermetically within offline CI/CD release gates.
  3. **High Subscription Costs**: Recurring enterprise seat licensing fees that do not provide corresponding technical value over open-source libraries (`Ragas`, `DeepEval`, `TruLens`, `Promptfoo`).
