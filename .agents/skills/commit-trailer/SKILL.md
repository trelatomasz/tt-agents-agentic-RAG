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

### Recognized Agents
- Codex: `Co-authored-by: Codex codex@openai.com`
- Gemini: `Co-authored-by: Gemini gemini@google.com`
- Claude: `Co-authored-by: Claude claude@anthropic.com`

### Behavior
- Only the specific AI agent(s) who assisted with or authored the changes (the agent making the commit) MUST be included in the `Co-authored-by:` trailer. Do NOT append all configured AI agents.
- If multiple AI agents collaborated on the commit, include trailers for each collaborating agent.
- If the commit already contains human co-authors, append AI co-author(s) after them.
- Do NOT remove or modify existing trailers.

### Enforcement
This rule MUST be applied by:
- local git hooks (prepare-commit-msg)
- project-level automation
- AI coding agents operating in this repository
