# V2 lot 1: baseline and common contracts

Prepared on 2026-09-25 for a personal portfolio project.

This is the review checkpoint before lot 2. Contracts below are specifications, not implemented schemas. Benchmark results and new test counts are not asserted.

## Immutable v1 reference

- Repository: https://github.com/oualidall/energy-genai-assistant
- Commit: `3af1e67185db5f5c172dd0cb5482f132560fda0b` (2026-07-31).
- Historical successful CI: https://github.com/oualidall/energy-genai-assistant/actions/runs/30627601905
- Python 3.12 in Docker and CI; declared minimum 3.11.
- Existing entry point: `EnergyAgent.answer(question)` returning `answer`, `route`, optional `sql`.
- Integration branch: `v2-multi-agent`. Lot branch: `v2-lot-1-baseline-contracts`.
- No deployment or production usage is established by this audit.

## Verified source findings

All paths refer to the immutable v1 commit above.

| Source | Observation | Planned consequence |
| --- | --- | --- |
| src/agent/graph.py | SQL/RAG feed synthesis; direct ends immediately. | Preserve v1 routing and prompts. |
| src/api/schemas.py | Response contains answer, route and optional SQL. | Preserve public v1 API with an internal adapter. |
| src/sql/text_to_sql.py | Prefix/forbidden-word guard runs during generation. | Strengthen validation at the execution boundary before MCP exposure. |
| src/sql/executor.py | Executor trusts callers. | Validate every submitted query, including MCP and reference SQL. |
| src/agent/graph.py | SQL exceptions become empty results; direct prompt does not enforce scope refusal. | Do not infer verified refusals or hidden errors in the v1 adapter. |
| src/eval/golden_questions.json | 12 questions, all SQL. | Add documentary, ambiguous and out-of-scope categories. |
| src/eval/runner.py | Judge helper is not called by run_eval; numeric matching rounds to two decimals; agent call is outside exception handler. | Shared evaluator with explicit tolerances and per-attempt error capture. Preserve legacy evaluator separately. |
| src/config.py | Moving model alias gemini-flash-latest. | Record a resolved model for comparison. |
| src/sql/text_to_sql.py | Temperature 0; no seed configured. | Record actual seed support rather than promise determinism. |
| src/rag/knowledge.py | Seven knowledge notes, cosine retrieval and lazy document embeddings. | Version corpus and measure initialization separately. |
| requirements.txt | Direct dependencies pinned; no complete transitive lock in tree. | Capture a tested resolved environment. |
| .github/workflows/ci.yml | Python 3.12, Ruff, pytest; pushes/PRs target main. | Use draft PR checks; expand CI later. |
| terraform/main.tf | BigQuery, Artifact Registry and Cloud Run; no budget-alert resource. | Correct unsupported README claims. |
| README.md | Deployment and some tracing work marked pending. | Describe only verified capabilities and measurements. |

## Architecture wording

> A LangGraph shared-state graph with a supervisor and specialized agents for retrieval, SQL and critique.

Roles share state. They are not four autonomous conversational agents. The critic checks evidence and can request at most two revisions after the initial draft. Its verdict is not proof of correctness.

## Common contracts

Use existing Pydantic; serialize with schema_version "1". Reject invalid enums and negative counters. Missing observations are null with an availability reason, never silently zero.

### AnswerResult

- request_id, variant (v1/v2), answer.
- route: sql/rag/direct/mixed/unknown.
- status: answered/clarification_required/refused/budget_exhausted/error/unknown.
- sql: optional string.
- evidence: Evidence list; metrics: RequestMetrics.
- error: optional structured code and sanitized detail.

Preserve raw v1 output alongside the normalized result. Do not invent evidence or infer a refusal from prose. The adapter may report unknown status. No changed prompts or extra model calls in v1 instrumentation.

### Evidence

evidence_id, kind (document/sql_result), source_id, source_version, content_hash, content, tool_call_id. SQL evidence includes executed query, ordered column metadata, typed rows, snapshot identifier and truncation flag. Citations must resolve to evidence actually obtained in the request. Distinguish empty, failed and truncated results.

### RequestMetrics

Integer monotonic duration_ns, LLM/tool call records, critic_calls, revision_requests, trace_id. Per-call records include role/tool, outcome, duration, retry index, model, provider usage categories and usage provenance. Estimated cost is a decimal string plus currency and pricing-manifest reference.

Count attempted tool calls including failures, without double-counting internal calls. Separate request costs from setup, reference evaluation and judging. Missing provider usage produces incomplete cost, not zero. Mock token counts are not provider-measured usage.

### RunManifest

run_id, UTC dates, full code commit and dirty status, protocol/schema versions, Python/resolved dependencies, OS/hardware, bank/corpus hashes, data snapshot, mock/live mode, exact agent/judge models, prompt hashes, generation settings, seed and support, repetitions, execution order, concurrency, initialization/cache policy, timeouts/retries, tracing configuration and dated pricing source.

### EvaluationRecord

Question ID/category, repetition, variant, raw and normalized response, expected criterion, validation method, objective outcome, judge verdict/rationale, human verdict, timing/error data and manifest reference. Invalid judge output is distinct from a negative verdict.

### SharedState (v2)

Question, plan, route, evidence, draft, critique with evidence references, revision count, remaining token/tool budgets, call records and final result.

Maximum two revisions. Record a finite graph step limit and concrete token/tool limits before measurement. Reserve input and capped output before every model call, including supervisor/critic. Explicitly fail if the chosen provider cannot support enforcement rather than claiming a hard cap. Budget exhaustion is a terminal typed outcome.

### MCP boundary

- search_documents(query, limit): identified excerpts and corpus version.
- query_readonly(sql): typed rows, column metadata, snapshot, truncation and usage.
- get_metrics(request_id): sanitized metrics or typed not-found.

Enforce a single allowed read-only statement, allowed tables/functions and configured limits at execution, with restricted BigQuery credentials. Use one tool implementation behind adapters. Minimal transport: stdio, three tools, a demo client and protocol/error tests. Verify and justify a pinned MCP SDK before changing existing dependencies.

## Effort and minimal path

Planning estimates, excluding access delays and human annotation wait time:

| Lot | Output | Focused days | Main risk |
| --- | --- | --- | --- |
| 1 | Reference, audit, contracts, fresh checks | 0.5-1 | Invalid baseline |
| 2 | Shared bank, evaluator, mock fixtures | 1.5-2.5 | Biased evaluation or leakage |
| 3 minimal | Three stdio MCP tools and demo | 0.5-1 | Compatibility and executor safety |
| 4 | Shared-state graph and bounded critique | 2-3 | More cost without improvement |
| 5 | Matched measurements and human validation | 1.5-2.5 | Confounding and incomplete labels |
| 6 | README, CI finish, changelog, CV facts | 1-1.5 | Claims beyond evidence |

Minimal path: 1 -> 2 -> 4 -> minimal 3 -> 5 -> reduced 6. Define tool contracts before lot 4; final measurements include MCP. Tests accompany each implementation lot. Small English commits; no history rewriting.

See [the measurement protocol](measurement-protocol.md). Do not proceed to lot 2 before presenting this checkpoint to the owner.
