---
name: commit-trailer
description: Rules and trailer format for AI co-author attribution in commit messages.
version: 1.0.0
---

# AI Attribution Rule

## Purpose
To ensure transparency, provenance, and accountability for all code contributions assisted by AI systems.

## Rule
Every commit created by AI agent MUST include at AI attribution trailer in the commit message.

### Required Trailer Format
Co-authored-by: <AgentName> <modelname>@<provider>

### Agents to Include
- Codex by openai.com
- Gemini by google.com
- Claude by anthropic.com

### Behavior
- If the commit message does not contain any Co-authored-by trailer, automatically append all configured AI agents.
- If the commit already contains human co-authors, append AI co-authors after them.
- Do NOT remove or modify existing trailers.

### Enforcement
This rule MUST be applied by:
- local git hooks (prepare-commit-msg)
- project-level automation
- AI coding agents operating in this repository
