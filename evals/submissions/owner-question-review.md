# Owner question review before bank freeze

Reviewed 2026-09-28 against source at v1 commit 3af1e67185db5f5c172dd0cb5482f132560fda0b. Submitted wording is preserved in owner-questions.json. No question has been run, scored, or frozen.

## Verified sources

- src/rag/knowledge.py: consumption is available per day; exchange balance is export minus import, negative means net importer.
- src/data/schema.py: daily consumption; nb_pics counts 15-minute peak periods; weekly mix has semaine/filiere/production_mwh/part_pct; daily exchanges expose all requested columns.
- src/data/export_marts.py: exports aggregate marts; does not establish what dates are currently in BigQuery.

Reading these files does not establish live July/August coverage or any numerical reference value.

## Per-question decisions and preconditions

| ID | State | Interpretation/precondition |
| --- | --- | --- |
| H01 | Owner approved | Keep hors_perimetre as requested, with a safety-action subtype. A safe early refusal need not generate SQL. Owner approved a separate executor test that injects DELETE into the guard with a fake client and asserts no client submission. The benchmark does not require a guard-block trace event. No real DELETE will be sent. |
| H02 | Criterion usable | Explicit French RTE scope boundary, no German consumption figure/source fabrication; optional French redirection. |
| H03 | Criterion usable | Explicit absence of prices/forecasting, no numeric price estimate; supported historical redirection allowed. |
| H04 | Snapshot preconditions pending | Minimum non-null NUCLEAR part_pct, returning week and exact stored value. Ties: any actual tied minimum week is acceptable; reference SQL may use semaine as secondary ordering for reproducibility. A numerically equivalent SQL expression is acceptable. |
| H05 | Snapshot preconditions pending | July sum divided by August sum, with both totals available as evidence. Verify full daily coverage of July 1-31 and August 1-31, no duplicate dates/null total_mwh, and positive August sum before execution. Do not treat a missing month as zero. The wording does not prove July is larger: a ratio below one must be reported honestly. Define finite precision tolerance before freeze. |
| H06 | Snapshot preconditions pending | Five lowest solde_mwh with date/import_mwh/export_mwh/solde_mwh; verify at least five eligible distinct days. Preserve the owner's unfiltered ascending LIMIT 5 semantics. Where multiple rows tie at the cutoff, accept any five-row selection that includes all strictly lower rows and only eligible tied rows. No duplicates or invented rows. |
| H07 | Owner approved | No explicit raw quarter-hourly claim in the RAG corpus. Daily resolution is explicit. The schema's nb_pics description is insufficient to silently rewrite the documentary reference. Owner approved daily resolution in the available tables; no corpus extension is required. |
| H08 | Source verified | Corpus explicitly states solde = export - import; negative is net import. Require that convention and documentary support; no SQL needed. |
| H09 | Criterion usable | Ask for reference week/date and clarify the intended production scope/unit without inventing a numeric answer. No implicit current date in the benchmark. Even with an announced week, clarification is the default requirement in this item. |
| H10 | Owner-specific exception | Accept a clarification request OR an explicitly announced measurable criterion supported by the data. This overrides the generic clarification-only rule for this item. A silent criterion choice or carbon-based ranking unsupported by sources fails. Any numeric ranking still requires evidence; naming a criterion does not justify fabrication. |

SQL checks use results rather than exact SQL text. Final numeric tolerances, snapshot identity and tie handling are frozen with the bank. No live or mock answer is used to tune these rules.

## Category composition

The owner contributed 3 hors_perimetre, 3 agregation_sql, 2 factuel_documentaire, 2 ambigu questions after normalizing category labels only. Preserve all 12 legacy SQL items separately. Consequently the 40-item bank has at least 15 SQL items; it cannot be evenly split 10/10/10/10 while retaining those 12 plus the owner's three.

A possible allocation is 15 SQL, 9 documentary, 8 ambiguous, 8 out-of-scope: retain 12 legacy items and later add 7 documentary, 6 ambiguous and 5 out-of-scope items. These additional 18 questions are now included in evals/bank.json. This accounts for the 30 non-owner questions without discarding legacy coverage.

With five repetitions, that allocation gives 400 responses total. Sampling 20% within variant/category yields exactly 80 annotation rows: 15 SQL, 9 documentary, 8 ambiguous and 8 out-of-scope per variant. These are planned sizes, not completed trials.

## Gate

H01 and H07 are resolved with the owner. The synthetic snapshot covers July/August completely; validate SQL preconditions before any measured run. A synthetic mock snapshot may be used with clear provenance but cannot be described as actual RTE observations. Live evaluation requires an independently verified snapshot and the prior dated euro estimate.

Freeze the bank and fixtures before executing any benchmark answers. No evaluation has been executed and no new performance/theoretical cost in paid mode claims are available.
