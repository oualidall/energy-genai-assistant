# Free-tier campaign controls

Prepared 2026-10-01. This supersedes the proposed paid pilot: **paid execution is not authorized**. The existing CLI still rejects live mode. No credential has been used, and no real pilot results exist.

## Verified mechanics and remaining integration

CallGate uses SQLite transactions and integer nano-euros to reserve the maximum input/output theoretical cost in paid mode before invoking an injected transport. It persists successful output, complete returned usage, quota attempts and wait intervals. Unknown/timeout/interrupted outcomes retain their reservation and block new campaign calls; they are not automatically resent. Usage exceeding the reservation also stops execution. Automatic retry is limited to three explicit 429 retries, each with its own reservation. This is not an exactly-once delivery guarantee from Gemini.

RPM and input TPM use a rolling minute. RPD resets at midnight America/Los_Angeles, including daylight-saving changes. Quotas are mandatory positive configuration values, never inferred from old public tables. Waits are sliced into at most 30 seconds. A request larger than TPM fails instead of waiting forever. The OS needs IANA time-zone data (present on the Linux CI runner).

A dedicated CI step runs tests/test_call_gate.py verbosely. Tests prove a budget rejection results in **zero transport calls**, and cover cumulative spending, request token limits, persisted quota waits, 429 retries, uncertain outcomes and completed-call replay.

The gate is tested with an injected fake transport, not a Gemini transport. Provider token counting, verified free-project credentials and real adapter integration are still required before enabling any network campaign. A Python flag cannot change the billing tier of an API key: the project itself must be confirmed Free. No paid fallback is implemented.

The theoretical cost in paid mode field is hypothetical paid API usage, separate from the 20% planning provision. Billed theoretical cost in paid mode remains unknown in the generic ledger; never label it zero solely because free mode was requested. A verified free-project run should report API billed theoretical cost in paid mode zero separately from theoretical cost in paid mode. Host/CI theoretical costs in paid mode are not measured.

## Resume without regenerating completed answers

The offline paired runner accepts:

```bash
python -m src.eval.compare --checkpoint work/campaign.sqlite --output work/campaign-results
```

Create the work directory first. If interrupted before final export, rerun the same command. The checkpoint binds bank/corpus/snapshot hashes, difficulty labels, question IDs, repetitions, source hashes and commit. Each completed trial is committed separately, including failed answers. Changed configuration is rejected. Finished output directories are never overwritten.

Real campaigns additionally need the per-call gate: a trial checkpoint alone cannot prevent duplicate provider calls if interruption occurs between response arrival and saving the trial. The gate blocks ambiguous cases for reconciliation.

## Quotas and availability checked 2026-09-30

[Google's rate-limit documentation](https://ai.google.dev/gemini-api/docs/rate-limits) directs users to active project limits in [AI Studio](https://aistudio.google.com/usage?tab=rate-limit). RPM, TPM and RPD are project-wide, not per-key; daily reset is midnight Pacific. Public historical numbers are not proof of this project's current quota.

[Gemini 2.5 model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite) currently restricts 2.5 access to previous active users. Therefore model eligibility also needs confirmation. No automatic model substitution is authorized.

Current project limits: unknown for both gemini-2.5-flash-lite and gemini-2.5-flash. It is not possible to give a verified completion duration or number of days yet.

Planning load (not measured): 1,400 Flash-Lite calls and 400 Flash judge calls for 400 responses, without revisions. Expected input: 3,100,000 Lite tokens and 800,000 judge tokens. Retry/revision load can increase these counts. The six-question pilot corresponds to 42 Lite calls and 12 judge calls under the same conservative full-SQL-path assumption.

Given confirmed quotas, a daily capacity lower bound is max(ceil(1400/Lite_RPD), ceil(400/Flash_RPD)) quota-days. For each model the minute-capacity lower bound is max(calls/RPM, input_tokens/TPM). These are capacity bounds, not elapsed-time predictions: service latency, interleaving, already-used shared quotas and 429 errors add time. Pilot timings will provide the service component.

## Compact judge and recalculated estimate

Keep the exact question, mandatory criterion, final answer, unique documentary evidence, last SQL execution and reference rows where applicable. Remove model/variant identity, full database schema, routing prompts, orchestration traces, timing, duplicate documents and examples. Ask only for correct/incorrect/incertain and one short reason.

Use **compact-2000-v1 with a hard 2,000-input-token ceiling**, with 200 expected output tokens. This is an estimate to check in the pilot, not a measured compression ratio or proof of unchanged judge quality. Never truncate required evidence to hit the target; oversized prompts must fail visibly rather than silently falling back to the historical 4,096-input allowance; output is capped at 512. Human agreement remains mandatory before interpreting judge scores.

Prices checked 2026-09-30: [Google standard paid text rates](https://ai.google.dev/gemini-api/docs/pricing), USD per million:
Lite input 0.10/output 0.40; Flash input 0.30/output 2.50.

One full campaign:
- Agents unchanged: USD 0.422.
- Judge: 800,000 input and 80,000 output tokens = USD 0.440.
- Total theoretical cost in paid mode: **USD 0.862**.
- Planning EUR convention (1 USD = 1 EUR, plus 20% provision): **EUR 1.0344**.
- Reduction from previous EUR 1.3224: **EUR 0.288**.
- Six-question pilot under the same assumptions: **USD 0.02586**, provisioned **EUR 0.031032**.

These estimates are not billing, and free-tier access must be verified. Hard maxima remain EUR 0.50 shadow budget for the pilot and EUR 2.50 for a single full campaign; the second campaign is not authorized. The previous EUR 2.433024 hard envelope remains a conservative upper envelope; the stricter judge input ceiling cannot increase it.

## Pilot and subsequent approval

evals/pilot-plan.json fixes six IDs without editing the frozen bank: H07 (easy), H04/H08 (medium), H05/H09 (difficult), H01 (out-of-scope slot, whose difficulty remains difficult). One repetition and both variants give 12 responses. The out-of-scope slot is a category, not a fourth difficulty level.

After project quotas and free credentials are verified and the transport is integrated/tested, run only that free pilot. Publish estimated versus provider-observed input/output tokens and percentage differences for every call, then aggregate by role. Re-estimate the full campaign from actual route/revision frequencies; six questions cannot establish precise per-category tail latency.

The full campaign still requires the owner's new approval. Keep 40 questions and five repetitions if the pilot supports the estimate; if comparable theoretical cost in paid mode exceeds the forecast by more than 50%, propose three repetitions in the report. No second campaign is authorized. Real/model output is not silently replaced by mock output.

A difference between v1 and v2 concerns the complete tested systems, does not causally isolate multi-agent orchestration, and says nothing about BigQuery or real RTE data.

## Binding pilot policy

[The acceptance policy](pilot-acceptance.md) supersedes historical allowances and fixes immediate stops, twelve human reviews and the strict 150% trigger before outcomes. Verified Free-tier API expenditure is zero; public/synthetic submissions may be used to improve Google's products. Flash and Flash-Lite are from the same family, so leniency/shared bias is not excluded. Only the human-annotated sample establishes correctness. Validation is bound to the actual compact-2000-v1 protocol and source hash. No real agreement was measured on the old prompt, and any such agreement would not transfer.
