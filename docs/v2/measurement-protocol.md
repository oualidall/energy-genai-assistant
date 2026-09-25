# Measurement protocol v1

Prepared 2026-09-25. Specification for review before lot 2, not a result report.
Concrete model IDs, pricing, snapshots and resource limits must be resolved and recorded before live execution. Any protocol change must be versioned before interpreting results.

## Matched experiment

- At least 40 questions across documentary facts, SQL aggregation, ambiguity and out-of-scope refusal; every question has a reference or explicit rubric. Retain the 12 legacy SQL questions with snapshot-compatible reference data.
- Five repetitions per question and variant: 200 attempts per variant and 400 total for exactly 40 questions. These are planned counts.
- Temperature 0 for agents and judge; harness seed 42, fixed execution order and alternating v1/v2 within matched trials. Concurrency 1.
- Pass seed 42 to model APIs when supported; record actual support. Do not claim temperature zero or a seed guarantees identical outputs.
- Same resolved model, corpus, snapshot and evaluator for both variants. Preserve v1 prompts/routing. Document compatibility or shared safety changes separately.
- Freeze finite timeouts, provider retries, graph steps, tool caps and token caps in configuration before execution. All agent retries consume the request budget and count in latency/cost.
- Never supply golden answers to the graph, tools or mocks. Mock tests verify mechanics; they do not establish Gemini answer quality.
- Use the same tool transport for the primary v1/v2 comparison. Record optional local/MCP transport experiments separately.
- Initialize clients and document embeddings explicitly before measured requests. Record setup time and cost separately and include them in full-run cost. Disable answer caches and record provider caching.

## Latency and quality

Time the complete agent call with a monotonic clock, from entry to return/error, including tools, MCP transport and critique. Exclude judging, reference SQL and initialization from request latency.

Compute p50 and p95 by nearest rank: sort n observations and select the one-based element ceil(p*n), for p=0.50 or 0.95. Publish n overall and per category. Include failed attempts and timeout elapsed durations in the all-attempt table, clearly identifying timeout censoring and counts. A successful-only supplementary table must state its denominator. Do not present incomplete runs as complete.

Quality denominators include every planned executed attempt, including failures. Publish exact pass/total fractions, per-category rates and per-question repetition outcomes. Distinguish SQL execution match from final answer correctness. Define column mappings, numeric tolerances and ordering requirements per criterion; do not inherit implicit two-decimal rounding. Validate reference queries on the frozen snapshot before running comparisons.

Record raw timing/usage values and exact decimal costs. Tables are generated from saved records. No manually rounded or invented results. Publish negative v2-v1 changes explicitly without implying general significance from this small bank.

## Tokens and cost

Record all provider usage categories available per call and their provenance. Separate generation, embeddings, judge and reference-query usage. Missing usage remains unknown; do not price it as zero. Mock estimates cannot be reported as measured live usage.

The pricing manifest records effective/check date, official source, model, units, rates as decimal strings and currency. Separate per-request agent cost, setup, scoring and full benchmark cost. Include BigQuery where measurable and identify excluded infrastructure costs. Actual billing is separate and requires billing evidence; estimated cost is labeled estimated. Free quota does not prove a zero invoice.

Report critic coverage (requests with critic calls / all attempts), revision rate (requests requesting revision / all attempts), total critic calls and tool calls separately. An always-on critic otherwise makes an escalation metric uninformative.

## Human validation of the LLM judge

Freeze judge model/prompt and rubric before human labeling. Select at least 20% of actual answer records with seed 42, stratified by category and variant; round stratum sizes upward. Spread samples across distinct questions before selecting repeated answers from the same question. For 400 answer records, at least 80 must be labeled by the owner.

Export question, answer, relevant evidence/reference and rubric; hide variant and judge verdict. Do not replace human labels with automated labels.

Publish:
- selected/total and annotated/total coverage;
- exact agreement numerator and valid paired denominator, plus rate;
- confusion matrix and invalid/missing verdict counts;
- sample seed, selection algorithm and rubric version.

Invalid judge outputs are reported rather than silently turned into rejection. Keep judge scores marked unvalidated until annotation coverage is complete. Agreement measures judge reliability, not assistant success. If the rubric changes after examining disagreements, version it and validate on a new held-out sample.

## Reproduction contract

Planned single entry point, not implemented in lot 1:

```bash
python -m src.eval.compare
```

Default is mock; runs both variants, writes raw results and generates comparison tables. Planned live variant:

```bash
python -m src.eval.compare --mode live
```

Human annotation requires an explicit export/import stage; it cannot be generated automatically. The final README must repeat the working command and configuration beside results.

Future output directory: evals/results/<run-id>/ with manifest, v1/v2 raw results, aggregates and generated Markdown comparison. Link human labels and agreement report by stable answer IDs. Never commit placeholders as if they were measured results.

## Publication rules

Separate mock and live results. State date, model, seed support, temperature, repetitions, actual n behind each percentile, snapshot, environment and pricing date beside the README table. If v2 does not improve v1, say so with the measured values and added latency/cost.

Facts for CV contains only reproduced measurements with commands and context, no deployment/customer claims, no superlatives and no connection to a graduation project. There are no new performance facts to publish at this checkpoint.
