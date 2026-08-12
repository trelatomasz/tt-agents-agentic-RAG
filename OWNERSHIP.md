# Repository ownership

This repository owns production agentic Retrieval-Augmented Generation (RAG): ingestion,
catalog versioning, retrieval, reranking, grounding, citations, evaluation and freshness.

Application-owned infrastructure stays under `deployment/<provider>/`. Shared networking,
identity federation, registries, Domain Name System, budgets and central log sinks belong
in `tt-cloud-infra`. Workflow state, tool orchestration, approvals and compensation belong
in `tt-agents-agentic-workflows-orchestration`.

The RAG service exposes a versioned, authenticated API and remains independently deployable
and rollbackable from its orchestration consumers.
