---
description: Spec-Driven Development and Modular Implementation Plan Workflow Rule
always_on: true
---

# Spec-Driven Development & Modular Implementation Plan Rule

## 1. Specification-First Refinement Protocol
- Before undertaking any implementation or code modification task:
  1. Inspect reference specifications (`docs/specs/personal-rag-spec.md` & `docs/architecture.md`).
  2. Verify technical boundaries and requirements against existing implementation code.
  3. Formalize any new architectural decisions or trade-offs as a new Architecture Decision Record (ADR) in `docs/adr/`.
  4. Reflect all refined requirements into the appropriate modular section of `docs/implementation/`.

## 2. Modular Implementation Plan Protocol
- All planned and active development work MUST be tracked in section files under `docs/implementation/` using the 3-digit numeric prefix scheme (`XXX-section-name.md`).
- Before starting work, agents and subagents MUST identify and read their designated section file.
- After completing a task:
  - Update the section plan file.
  - Mark completed tasks as `[DONE]`.
  - Record technical changes and verification output in the section file.
  - Create follow-up section files if new tasks or technical debts emerge.
  - Update the master assembly plan (`docs/implementation/plan.md`).
