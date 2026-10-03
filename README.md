# energy-genai-assistant

A personal Python project for answering questions about French electricity data through documentary retrieval and read-only SQL. The existing v1 uses a LangGraph router; v2 is being built as a **LangGraph shared-state graph with a supervisor and specialized agents**.

## Measurement scope

**Current measurements use a synthetic snapshot in SQLite, not BigQuery under real conditions.** The offline smoke model exercises the graph and evaluation machinery; it does not measure Gemini answer quality.

These measurements cannot establish BigQuery dialect compatibility, IAM enforcement, network/service latency, query billing, production scalability or quality on real RTE observations. No production deployment or customer usage is claimed. Terraform and Docker files are implementation assets, not evidence of a deployed service.

## Current implementation

- v1: route to documentary retrieval, SQL generation, or a direct answer; FastAPI `/ask` and `/healthz`.
- Existing Gemini integration and BigQuery execution path remain available in source. The frozen evaluation currently uses neither service.
- v2: bounded shared-state supervisor/Retrieval/SQL/Critique graph, typed evidence, offline `/ask/v2`, paired mock evaluation and blinded human annotation tooling.
- Shared SELECT-only AST execution guard. Pending: MCP transport, live usage accounting, validated judge and committed full-campaign results.

The v1 reference is commit `3af1e67185db5f5c172dd0cb5482f132560fda0b`. Python 3.12 is used by Docker and CI.

## Run the offline evaluation

From the repository root with Python 3.12 and the pinned dependencies installed:

```bash
python -m src.eval.compare
```

The command defaults to both variants, 40 questions and five repetitions: 400 offline attempts. It writes a new results directory with a manifest, raw responses, aggregate JSON and Markdown tables by category and difficulty. This is the configured run size, not a claim that a full paired campaign has been completed.

CI uses an explicit eight-question stratified mock subset:

```bash
python -m src.eval.compare --limit 8 --repetitions 1 --output work/ci-eval
```

No LLM API credentials are required. See [evaluation instructions](evals/README.md) for annotation commands. Live mode remains disabled pending the dated EUR estimate and enforced campaign controls. The mock critic is not a semantic judge; mock accounting units are not provider tokens.

## Frozen bank and exact counts

The SHA-256 of the exact `evals/bank.json` bytes is published in [evals/bank.lock](evals/bank.lock), with original freeze date **2026-09-28** and explicit-lock publication date **2026-09-29**:

```text
f67ace63230678169d583243ebe7aa040fea19ee9b1692dda91e94cc3dfb5d76
```

The original [freeze.json](evals/freeze.json) predates the first benchmark answer and also protects the snapshot, corpus source and refusal rubric. Startup checks both locks, recomputes the file hash and stops before model construction on a mismatch or missing lock. A hash inside the bank itself is unnecessary and would create a self-reference; the external lock records it without changing the frozen file.

These are question inventory counts, not performance results:

| Category | Historical | Owner | Assistant | Total |
| --- | ---: | ---: | ---: | ---: |
| SQL (lookup and aggregation) | 12 | 3 | 0 | 15 |
| Documentary | 0 | 2 | 7 | 9 |
| Ambiguous | 0 | 2 | 6 | 8 |
| Out of scope | 0 | 3 | 5 | 8 |
| **Total** | **12** | **10** | **18** | **40** |

Recount directly from the locked file:

```bash
python -m src.eval.benchmark
```

[Difficulty metadata](evals/difficulty.json) is separate: **15 facile, 16 moyen, 9 difficile**. It supplies definitions for all three levels and a rationale for every ID. Labels were added on 2026-09-29 after initial mock smoke runs and before the v1/v2 comparison, based on task requirements rather than outcomes. Each future run records the metadata hash and mapping. Old artifacts are not silently relabeled.

## Architecture

See [the shared-state graph and exact budgets](docs/v2/lot-4.md). The v1 prompts and routing remain available; its execution boundary now shares the stricter SQL guard, a documented difference from the historical reference.

## Results

**Scope of every result table: synthetic snapshot in SQLite, not BigQuery under real conditions.** Consequently these results cannot demonstrate live BigQuery correctness, IAM controls, latency, billing or scalability, or Gemini quality with the mock model.

A paired v1/v2 performance table is not yet available. CI artifacts contain subset smoke outputs only. The report generator repeats the scope and limitations immediately before every category/difficulty result table and includes the scope in machine-readable summaries.

SQL execution match is separate from final-answer correctness. Final-answer and judge scores remain unvalidated until implemented and checked against the owner's annotations. No gain from multi-agent orchestration is claimed at this stage.

## Reproducibility and review

- Protocol: temperature 0, harness seed 42, five repetitions by default, concurrency 1; mock model seed is unsupported. Exact question IDs and actual sample sizes are saved.
- Latency: monotonic integer nanoseconds; nearest-rank p50/p95; failed attempts retained. Setup and scoring are separate.
- Human validation: at least 20% of responses, blinded CSV, correct/incorrect/incertain labels, exact agreement fractions and coverage.
- Quality: the bank and criteria do not change after results; negative v2 results will be published as measured.
- Development checks: `python -m ruff check src/ tests/` and `python -m pytest -q`.
- Design: [baseline and contracts](docs/v2/baseline-and-contracts.md), [measurement protocol](docs/v2/measurement-protocol.md), [owner constraints and refusal rubric](docs/v2/refusal-and-review-rules.md).

## Free-tier controls and resumption

[Free-tier controls](docs/v2/free-tier-controls.md) document durable pre-call monetary reservations, quota waits, uncertain-call handling, compact judge inputs and the six-question pilot plan. These controls are tested with injected mock transport; the Gemini adapter and project-specific Free status/quotas remain unverified. Paid mode is not authorized and live mode remains disabled. CI explicitly prints budget-blocking test names and the frozen category/difficulty inventory.

The offline benchmark can resume completed trials with `python -m src.eval.compare --checkpoint work/campaign.sqlite --output work/campaign-results` after creating `work/`. Keep the same source and configuration when resuming.

## Theoretical theoretical cost in paid mode in paid mode and delivery limits

Total effective-work budget: five days on the minimal path 1 -> 2 -> 4 -> minimal 3 -> 5 -> reduced 6. Stop and report proposed cuts if a lot exceeds its allocation.

**Paid mode is disabled and unauthorized.** The Free-tier pilot has a EUR 0.50 ceiling for theoretical cost in paid mode; stop and report afterward. One full campaign requires explicit subsequent approval and a EUR 2.50 ceiling. No second campaign is authorized. Mock API expenditure is zero because no provider calls occur; host/CI expenditure is not measured. No live tariff or billed total is asserted.

## License and author

[MIT](LICENSE). Personal work by Oualid Allouch.

## Pilot decision and human validation

[Preregistered pilot acceptance](docs/v2/pilot-acceptance.md) fixes stop conditions and eligibility before any real response. Verified Free-tier API expenditure is zero; submitted public/synthetic data may be used to improve Google's products ([official terms and pricing](https://ai.google.dev/gemini-api/docs/pricing)). Every monetary estimate is a **theoretical cost in paid mode**, not Free-tier expenditure.

The Flash judge and Flash-Lite agents share the Gemini model family: leniency and shared biases are not excluded. Only the human-annotated sample establishes correctness. Agreement must use the actual compact-2000-v1 prompt and its recorded source hash; old 4,000-token agreement cannot transfer. No real human agreement has been measured yet. Synthetic annotation test values are not results.

PR #4 targets v2-multi-agent. New pilot corrections stay on v2-free-tier-controls; CI evidence must identify its exact branch/commit. Nothing is merged into main before the pilot. The frozen September refusal rubric is preserved byte-for-byte for hash integrity; its historical monetary wording is superseded by the current pilot policy.
