# GPC parts RAG pilot

Deployable evidence for the GPC Senior Software Engineer Generative Artificial Intelligence interview session.

# Repository ownership

This repository owns production agentic Retrieval-Augmented Generation (RAG): ingestion,
catalog versioning, retrieval, reranking, grounding, citations, evaluation and freshness.

Application-owned infrastructure stays under `deployment/<provider>/`. 

The RAG service exposes a versioned, authenticated API and remains independently deployable
and rollbackable from its orchestration consumers.


# Security Policy

## Public Repository Architecture & Privacy

This repository is maintained as a **100% public, open-source template and application codebase**. It is intentionally designed to be fully decoupled from any private infrastructure, individual identities, or personal environments.

### Privacy & Sanitization Guarantees
- **No Hardcoded Credentials or Keys**: Authentication to cloud resources uses keyless Workload Identity Federation (WIF) and Secret Manager. No long-lived service account keys, tokens, or passwords are kept in this repository.
- **Generic Infrastructure**: All OpenTofu modules and application configurations use parameterization and environment variables.
- **Git History Sanitization**: All commit history is strictly maintained without references to private project IDs or user accounts.

### Reporting a Vulnerability
If you discover any security vulnerability or sensitive data disclosure, please do **not** open a public issue. Instead, report it privately via GitHub Security Advisories or contact the repository maintainers directly.
