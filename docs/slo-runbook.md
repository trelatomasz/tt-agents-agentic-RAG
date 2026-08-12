# Service objectives and runbook

At 200,000 queries/day, average load is `200000 / 86400 = 2.31 QPS`; ten-times peak is
23.1 QPS. At 3.5-second p95 latency, Little's Law gives 81 concurrent requests; plan for
120 plus measured headroom. Cloud Run is capped at 20 × 16 = 320 request slots, subject to
load tests and Vertex quota.

| Objective | Target | Escalation |
|---|---:|---|
| Availability | 99.9% monthly | Page on fast error-budget burn |
| p95 latency | <3.5 seconds | Ticket unless fallback also fails |
| Citation correctness | >=95% | Page on compatibility-risk regression |
| Unsafe compatibility claim | 0 known | Page immediately |
| Catalog freshness | <1 hour | Disable generation and use conventional search |

Cost is six million monthly queries multiplied by measured input/output tokens and current
Vertex prices, plus Cloud Run, storage, logging and network. Track cost per successful
answer. Model latency/quota is the likely bottleneck.

For a slice regression, disable generation for that category, correlate model/prompt/
catalog versions, replay the failing slice, roll back the Cloud Run revision and restore
through shadow traffic plus canary. Page for leakage, authorization failure, unsafe
compatibility claims or loss of primary and fallback paths.
