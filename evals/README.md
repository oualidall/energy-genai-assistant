# Frozen evaluation bank

Bank: 40 questions, including 10 owner-authored questions and all 12 legacy SQL questions.
Distribution: 15 SQL, 9 documentary, 8 ambiguous, 8 out of scope.

The owner's H01 decision accepts early refusal; actual executor guard enforcement is a separate security test. H07 expects daily granularity in the available tables. H10 accepts either clarification or an explicitly announced data-supported criterion. See submissions/ for the original wording and review.

## Freeze

The bank, synthetic snapshot, existing corpus source and refusal rubric were hashed in commit 4290dca6dbb59cc7b856e98e32dffa1cd4c21864 before any benchmark answer was generated. The exact UTF-8 file bytes are checked against freeze.json before every run. No post-result edits to these inputs are permitted for this campaign.

Bank SHA-256: f67ace63230678169d583243ebe7aa040fea19ee9b1692dda91e94cc3dfb5d76

The snapshot is synthetic and contains all July/August days. It is not a download of real RTE values and does not demonstrate real BigQuery date coverage. Reference queries are preflighted before timing agent calls. SQLite supports only the frozen query subset here; it is not a BigQuery emulator. A live snapshot must be independently validated, including ties and full-month coverage, before live scoring.

## Reproduce (Python 3.12, dependencies installed)

```bash
python -m src.eval.compare
```

The default runs the actual v1 and v2 graphs against offline injected dependencies for all 40 questions, five repetitions each. It creates 400 attempt records in a new evals/results/<run-id>/ directory, with manifest.json, v1.json, v2.json, summary.json and summary.md. This describes the command's behavior, not a claim that a full run has already been completed.

CI uses an explicit stratified subset:

```bash
python -m src.eval.compare --limit 8 --repetitions 1 --output work/ci-eval
```

The subset takes questions round-robin from sorted category buckets in frozen bank order. Its identity is recorded in the manifest. It is not reported as a full-bank result.

The smoke LLM has no access to golden answers. It deliberately returns a generic COUNT query for SQL prompts and copies supplied evidence for synthesis. This exercises graph/tool/evaluator plumbing, not Gemini reasoning. SQL execution match is reported separately from final answer correctness, which remains unscored. Do not put these smoke quality scores in a CV as Gemini performance.

Both variants are implemented with offline adapters. Their mock policies differ, so quality differences cannot be attributed to orchestration alone. The critic is a structural smoke fixture, not a semantic judge. Live mode fails before model initialization until a dated euro estimate and conservative enforced bounds fit the total 5 EUR cap. No fake v2 baseline, judge score or provider token usage is substituted.

The measured latency uses integer monotonic nanoseconds and nearest-rank p50/p95 with n. Failures stay in the denominator. Setup is separate. This smoke protocol is local injection; the final paired v1/v2 experiment will use common MCP transport. No live provider timeout or billing guarantee is implied.

## Human annotation

After actual runs, export at least 20% of responses:

```bash
python -m src.eval.annotation export --results evals/results/RUN/v1.json --directory work/annotations
```

When v2 results exist, supply both JSON paths after --results. For 400 responses with this category allocation the sample contains 80 rows, covering each question once per variant.

Give the owner only answers.csv, not private-map.json. The CSV contains question, category, answer, criterion, evidence, blank verdict and comment. Allowed verdicts: correct, incorrect, incertain. Uncertain verdicts require a comment. Do not alter IDs or replace source result files. The mapping verifies the result hash.

```bash
python -m src.eval.annotation agreement --results evals/results/RUN/v1.json --directory work/annotations
```

This prints exact agreement fractions, paired counts, confusion matrix and coverage. With no judge labels it cannot claim judge validation. Uncertain/missing labels remain visible; definite human coverage must reach 20% and all definite labels need valid judge pairs before the report marks the judge validated.

Target human effort is 45 minutes (5-minute briefing and approximately 30 seconds per row for 80 rows), not a measured promise. Time the first ten rows and report any mismatch rather than weakening coverage silently.

## Current boundaries

Implemented here: frozen bank, synthetic references, actual v1/v2 offline graph execution, bounded v2 retries/accounting, output records, percentiles, reference SQL comparison and human annotation workflow.

Still required in subsequent lots: MCP, provider usage/cost capture, live/judge implementation, actual human annotations, paired full-run result commits and final README results. Model prices and real scores have not been invented. No paid API execution occurs in CI.

## September 29 clarification: scope, explicit lock and difficulty

All current measurements use a **synthetic snapshot in SQLite, not BigQuery under real conditions**. They cannot establish BigQuery dialect correctness, IAM enforcement, network/service latency, query cost, scalability, real RTE data quality or Gemini answer quality. This scope is repeated immediately before each generated result table and saved in each summary group.

The explicit bank.lock publishes the same SHA-256 as the original freeze.json, with freeze and publication dates. Startup rejects mismatches, missing locks and disagreement between locks before agent construction. bank.json has not been modified.

Exact inventory (question counts, not performance results):

| Category | Historical | Owner | Assistant | Total |
| --- | ---: | ---: | ---: | ---: |
| SQL (lookup and aggregation) | 12 | 3 | 0 | 15 |
| Documentary | 0 | 2 | 7 | 9 |
| Ambiguous | 0 | 2 | 6 | 8 |
| Out of scope | 0 | 3 | 5 | 8 |
| **Total** | **12** | **10** | **18** | **40** |

Reproduce these counts with `python -m src.eval.benchmark`.

difficulty.json contains all 40 IDs: 15 facile, 16 moyen and 9 difficile, with level definitions and individual rationales. It was added after initial smoke runs, before the multi-agent comparison, based on task requirements. New raw records include the level; summaries include difficulty groups and their own denominators. Run manifests preserve the full mapping and its SHA-256. Historical outputs remain unchanged and unclassified unless explicitly analyzed as a separately identified retrospective report.

The paired report protocol is mock-smoke-3. It preserves difficulty metadata and scope labels, records alternating variant order and mock source hashes, and does not change frozen inputs. Provider token counts remain null. V1 shares the new executor guard; this deviation from the historical baseline is recorded. See [lot 4](../docs/v2/lot-4.md).
