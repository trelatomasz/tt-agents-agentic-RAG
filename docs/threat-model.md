# Threat model

| Threat | Enforcement point | Control |
|---|---|---|
| Unauthenticated use | Cloud Run IAM | Private service and explicit invoker |
| Runtime escalation | GCP IAM | Dedicated account: Vertex user and catalog read only |
| Cross-unit access | API/catalog boundary | Pilot has one unit; production needs server-derived filters or separate indexes |
| Prompt injection | Generator/tool boundary | Evidence is untrusted; no tools; model cannot authorize |
| Exfiltration | Runtime permissions | No arbitrary URL tool, generic credentials or service-account keys |
| Sensitive logs | Logging boundary | Identifiers and versions only, not prompts or document bodies |
| Stale/withdrawn part | Service and bucket | Versioned source, freshness gate, fail-closed fallback |

Supplier ingestion must quarantine input, validate source/schema/malware and write an
immutable version before changing `catalog/current.json`. Identity and business unit must
come from verified server context, never a client field.
