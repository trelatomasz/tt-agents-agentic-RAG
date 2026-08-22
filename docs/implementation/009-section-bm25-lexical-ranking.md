# Section 009: True BM25 Lexical Ranking in PostgreSQL

- **Module**: Lexical ranking (`src/personal_rag/index/postgres.py`, `db/migrations/`)
- **Status**: `PENDING`
- **Assigned Subagent**: Database & Index Subagent
- **Dependencies**: [`003-section-database-and-vector-store.md`](003-section-database-and-vector-store.md)
- **Target Files**:
  - `src/personal_rag/db/migrations/` (corpus statistics tables)
  - `src/personal_rag/index/postgres.py` (lexical branch)

---

## 1. Why this exists

Section 003 delivers the lexical branch with `ts_rank_cd`, not Okapi BM25. The debt is
recorded here rather than left implicit.

`MemoryIndex` computes BM25 with inverse document frequency derived from the **ACL-filtered
candidate set** — the documents this particular principal may read. PostgreSQL cannot
reproduce that cheaply: it needs a document-frequency count per query term over the readable
subset, which is a full pass over exactly the rows the GIN index exists to avoid touching.

So the two implementations of one protocol rank differently *within* the lexical branch.
Reciprocal Rank Fusion consumes ranks rather than scores, so absolute scale never reaches the
fused result, and the practical difference on the sample corpus is small — but it is a real
divergence and it is not measured yet.

## 2. Checklist & Deliverables

- [ ] Measure the divergence first: run the retrieval evaluation set (section 008) against
      `MemoryIndex` and `PostgresIndex` on identical corpora and report recall@k and MRR.
      **If the gap is inside the noise band, close this section as "won't do" rather than
      building machinery for it.**
- [ ] If it is not: add a `lexeme_document_frequency` table and a `corpus_statistics` row
      (document count, average `lexical_source` length), maintained at activation time from
      the newly activated run rather than recomputed per query.
- [ ] Decide explicitly whether IDF is computed over the whole active corpus or per ACL
      partition. Whole-corpus IDF leaks a weak signal about document frequency in sources the
      principal cannot read; per-partition IDF multiplies the statistics tables by the number
      of grant combinations. This is a threat-model question, not a performance question —
      route it through [`../threat-model.md`](../threat-model.md).
- [ ] Implement `bm25_score(tsvector, text[], …)` as an `IMMUTABLE` SQL function with
      $k_1 = 1.2$, $b = 0.75$ to match `index/memory.py`.
- [ ] Extend the parity test in `test_postgres_integration.py` from "same top result" to
      "same lexical ordering".

## 3. Changes Implemented & Verification

Nothing implemented yet.

## 4. Next / Follow-Up Sections

- Feeds the retrieval quality metrics in [`008-section-evaluation-and-observability.md`](008-section-evaluation-and-observability.md).
