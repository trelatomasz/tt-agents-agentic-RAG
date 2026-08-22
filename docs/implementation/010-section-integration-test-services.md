# Section 010: PostgreSQL Integration Tests in CI

- **Module**: CI (`.github/workflows/ci.yml`)
- **Status**: `PENDING`
- **Assigned Subagent**: CLI & Tooling Agent
- **Dependencies**: [`003-section-database-and-vector-store.md`](003-section-database-and-vector-store.md)
- **Target Files**:
  - `.github/workflows/ci.yml`

---

## 1. Why this exists

`tests/personal_rag/test_postgres_integration.py` is written and skipped. It skips unless
`PERSONAL_RAG_TEST_DSN` is set, and CI sets no such variable, so **no automated check
currently proves that PostgreSQL accepts the DDL or the retrieval queries**. The offline
suite asserts the shape of the SQL; only this suite asserts that a server runs it.

Until this section lands, a change to `db/migrations/` or to `_SEARCH_SQL` can go green in CI
and fail on first contact with Cloud SQL.

## 2. Checklist & Deliverables

- [ ] Add a `pgvector/pgvector:pg16` service container to the `lint-and-test` job, with a
      health check, so the suite waits for readiness rather than racing it.
- [ ] Export `PERSONAL_RAG_TEST_DSN` for the pytest step and confirm the 13 tests **run**
      rather than skip — assert the collected count, since a silently skipping suite is
      indistinguishable from a passing one in the CI log.
- [ ] Pin the pgvector image by digest; the retrieval path depends on `hnsw.iterative_scan`,
      which exists only in pgvector ≥ 0.8, and a floating tag can withdraw it.
- [ ] Verify the version guard works both ways by running the suite once against
      `pgvector:pg16` with an older pgvector and confirming `PostgresIndex._tune` logs
      `index_tuning_unavailable` instead of failing.

```yaml
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_PASSWORD: rag
        ports: [ "5432:5432" ]
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
```

## 3. Changes Implemented & Verification

Nothing implemented yet.

## 4. Next / Follow-Up Sections

- Shares the CI job with [`006-section-ci-cd-and-cli-tools.md`](006-section-ci-cd-and-cli-tools.md).
