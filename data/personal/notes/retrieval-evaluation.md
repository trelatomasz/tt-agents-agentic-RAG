# Designing a retrieval evaluation gate

A retrieval evaluation gate is the check that decides whether a candidate index is allowed
to become the active index. It runs offline, against a fixed question set, and it produces
a decision rather than a dashboard.

## Why retrieval and generation are measured separately

A blended score hides which half of the system regressed. When a single number falls, the
team cannot tell whether the retriever stopped finding the passage or the generator stopped
using it. Measuring retrieval on its own answers a narrow question: given this query, did
the correct chunk appear in the top k results at all? Generation quality can only be
assessed over evidence that was actually retrieved, so retrieval is the upstream gate.

The practical consequence is that a retrieval regression should page, while a generation
regression can often be handled by rolling back a prompt version. The two failures have
different owners and different remedies.

## Choosing the question set

A gate is only as good as the questions behind it. Thirty to fifty real queries collected
from actual use beat several hundred invented ones, because invented queries encode the
assumptions of whoever wrote them. Each question needs a recorded expected passage, not
just an expected answer string, so that retrieval can be scored without a model in the
loop.

Balance the set across sources. A corpus that mixes books, web pages and repository files
will regress unevenly, and one blended threshold lets a strong slice mask a broken one.
Score each slice against its own threshold.

## Negative and adversarial cases

Roughly a fifth of the set should be questions the corpus cannot answer. Without them a
gate rewards a system that always produces something, which is the failure mode that
matters most in a research tool. Negative cases cover four situations: the fact is absent,
the fact is stale, the fact exists in a source the caller may not read, and the document
contains text attempting to redirect the model.

The expected outcome for every negative case is an abstention, not a hedged answer. An
abstention that names what was searched is more useful than a paragraph that sounds
plausible and cites nothing.

## Metrics worth recording

| Metric | What it catches |
|---|---|
| recall@k | The retriever no longer surfaces the passage at all |
| Mean Reciprocal Rank | The passage is found but ranked below the context budget |
| Citation precision | The answer cites evidence that does not support it |
| Abstention precision | The system answers when it should have declined |
| Freshness lag | Deleted or updated content is still being cited |

Record the source snapshot, chunker version, embedding model and prompt version alongside
every result. A score without those identifiers cannot be compared against the next run,
and comparison is the only thing the gate exists to do.

## When the gate should block a release

Block on any access-control leak or exposed secret, and on any unsupported answer in the
negative set. Treat a drop in recall@k as a block only when it crosses the threshold agreed
for that slice; small movements on a fifty-question set are noise, and a gate that fires on
noise gets disabled within a month.
