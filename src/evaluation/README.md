# RAG Evaluation Harness

Hermetic, deterministic evaluation of the recap + retrieval + grounding
quality layers. No external APIs, no database.

## Running

Evaluation tests are opt-in and excluded from the default `tests/unit` run
via the `evaluation` marker. Run them explicitly:

```bash
uv run pytest tests/evaluation -m evaluation -v
```

Run a single layer:

```bash
uv run pytest tests/evaluation/test_recap_eval.py -m evaluation -v
uv run pytest tests/evaluation/test_retrieval_eval.py -m evaluation -v
uv run pytest tests/evaluation/test_grounding.py -m evaluation -v
```

## What gets evaluated

| Layer      | File                         | Metric                                                                 |
| ---------- | ---------------------------- | ---------------------------------------------------------------------- |
| Recap      | `test_recap_eval.py`         | Per-fixture schema + topic / tone / risk-flag polarity (100% required) |
| Retrieval  | `test_retrieval_eval.py`     | hit@3 across all test queries (>= 0.7 required)                        |
| Grounding  | `test_grounding.py`          | Jaccard-overlap sentence-grounding metric unit tests                   |

## Fixtures

Six synthetic transcripts in `tests/evaluation/fixtures/`:

- `transcript_anxiety_work.json`
- `transcript_grief.json`
- `transcript_sleep.json`
- `transcript_relationship.json`
- `transcript_substance.json`
- `transcript_si_risk.json` (contains SI language to exercise risk-flag detection)

Every fixture carries a `disclaimer` field asserting it is fictional. No
real PHI is used anywhere in the harness.

## Mocks

Defined in `tests/evaluation/conftest.py`:

- `mock_claude_client`: `FakeClaudeClient` that matches an input transcript
  to its fixture via the fixture disclaimer, then returns canned JSON that
  satisfies the fixture's `expected_recap` contract.
- `mock_embedding_client`: `FakeEmbeddingClient` that produces a
  deterministic 1536-dim pseudo-embedding. Same text -> identical vector;
  texts sharing topic tokens cluster by design.
- `fake_vector_search_repo`: in-memory cosine-similarity search with
  per-patient isolation, mirroring the API of `VectorSearchRepository`.

## Interpreting the metrics

- **Recap pass rate: 100% required.** The recap tests use canned
  deterministic responses — a failure indicates drift in either the
  fixture contract, the prompt, or `SessionRecapPayload`.
- **hit@3: currently observed and asserted >= 0.7.** Lower indicates the
  fake embedder's bag-of-words projection no longer clusters the fixture
  vocabulary. Tune `_TOPIC_TOKENS` in `conftest.py` before lowering.
- **Grounding score: 0.0 - 1.0.** `1.0` means every answer sentence is
  supported by the retrieved sources (lexical, not semantic).
