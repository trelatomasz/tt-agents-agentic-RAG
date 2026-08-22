# ADR-003: Public Repository Hygiene, Zero-Leak Mandate, and Identity Sanitization

- **Status**: Approved
- **Deciders**: Platform Architecture Team
- **Date**: 2026-08-22
- **Technical Scope**: Public Repository Standards, Identity Placeholders, Path Portability, and Documentation Hygiene.

---

## 1. Context & Problem Statement

This repository is maintained as a **100% public, open-source codebase and architectural reference**. 

During documentation analysis, several instances of personal developer handles (`tomasz`, `owner:tomasz`), machine-specific absolute drive paths (e.g., `D:\src\...`, `D:\Books`), and private account references were identified in earlier specification drafts and notes.

To prevent any sensitive information exposure, maintain public auditability, and ensure cross-platform reproducibility (across Windows and Linux/WSL environments), we need a standardized convention for identity redaction, path representations, and documentation hygiene across all files, specifications, and architecture diagrams.

---

## 2. Considered Approaches

| Evaluation Criteria | Option 1: Inline Sanitization Standard with Generic Placeholders (Selected) | Option 2: Private Fork / Split-Repository Model | Option 3: Dynamic Runtime Token Replacement Only |
|---|---|---|---|
| **Public Transparency** | **High**: The entire repository remains open-source, reproducible, and verifiable. | **Low**: Divides architectural history into private and public silos. | **Medium**: Relies on CI scripts to scrub files, risking accidental commits. |
| **Operational Simplicity** | **High**: Clear, consistent placeholders applied statically across code and docs. | **Low**: High maintenance overhead syncing two repositories. | **Low**: Complex pre-commit hooks and filter-branch tooling required. |
| **Cross-Platform Portability** | **High**: Repository-relative paths work uniformly on Windows, Linux, and macOS. | **Medium**: Still prone to platform-specific path leaks. | **Low**: Does not solve documentation path portability. |

---

## 3. Decision

We establish the following **Zero-Leak & Documentation Hygiene Standards** across all documentation, specifications, diagrams, and code comments:

### 3.1 Generic Identity & Role Placeholders
- **User / Operator Identity**: Use generic placeholders such as `user:your-email@example.com`, `user:owner`, or `operator`. Never commit personal usernames, emails, or LDAP handles.
- **ACL Labels**: Format access control labels with generic prefixes:
  ```python
  acl_labels = ["owner:primary", "group:dev", "visibility:private", "visibility:public"]
  ```
- **GCP Project Identifiers**: Use `your-gcp-project-id`, `PROJECT_ID`, or `${var.project_id}`. Never use real cloud project names.

### 3.2 Repository-Relative Path Conventions
- **Documentation & Spec Paths**: All internal references must use repository-relative paths (e.g., `docs/architecture.md`, `src/personal_rag/`, `data/personal/sources/`).
- **External / Canonical Sources**: References to external canonical knowledge trees must use generic placeholders (e.g., `<SOURCE_ROOT>/info`, `/path/to/ebooks`) rather than absolute machine drive letters (`C:\`, `D:\`).

### 3.3 Specification Preservation Policy
- Historical and living specifications (`docs/specs/*`) that serve as established baselines are preserved under version control.
- Any architectural evolution, disambiguation, or standardizations must be formalized via **Architecture Decision Records (ADRs)** rather than ad-hoc spec alterations, ensuring full traceability and consent.

---

## 4. Consequences

### Positive
- **Guaranteed Privacy**: Zero risk of leaking personal identities, corporate credentials, or environment-specific data into public Git history.
- **Portability**: All documentation, code snippets, and OpenTofu modules can be cloned and run by any engineer or CI/CD runner without modification.
- **Clear Governance**: Architectural decisions remain immutably recorded in ADRs with explicit deciders and rationale.

### Negative / Trade-offs
- **Placeholder Substitution**: Operators deploying to private GCP environments must provide their real project IDs and invoker emails via gitignored `terraform.tfvars` and `.env` files.
