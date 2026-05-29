# Backend Milestone Notes

## Scaffold backend API, worker, and shared settings

Status: completed by backend-engineer on 2026-05-29.

Delivered scope:

- FastAPI application factory with a `/health` readiness endpoint.
- Shared environment-based settings for API and worker runtime values.
- RQ worker entrypoint with a check mode that validates settings without Redis or LLM access.
- Local `just` commands for API startup, worker startup, worker readiness check, and backend tests.
- Backend package metadata, environment template, local ignore rules, and development README.

Verification:

- `just backend-worker-check` passes and returns worker readiness metadata.
- `just backend-test` passes with 3 targeted tests covering health readiness and worker check mode.

## Create persistence schema and migrations

Status: completed by backend-engineer on 2026-05-29.

Delivered scope:

- SQLAlchemy database base, session factory, English enum values, and models for Review tasks, reports, issues, rules, and feedback.
- Alembic configuration and initial migration for the persistence schema.
- SQLite local database setting, migration commands, environment template, local ignore rules, and README command updates.
- Persistence tests for migration up/down, every table, enum validation, and the 50k diff-content cap.

Verification:

- `just backend-test` passes with 8 tests.
- `just backend-migrate && just backend-migrate-down` passes on SQLite.
- `just backend-worker-check` passes.

## Implement Review task lifecycle API

Status: completed by backend-engineer on 2026-05-29.

Delivered scope:

- Create, list, get detail, soft delete, and rerun endpoints for Review tasks.
- Pydantic request/response models with validation: required PR title and diff, 50k diff limit, blank rejection.
- Demo owner header for task ownership; all endpoints filter by owner and exclude soft-deleted records.
- RQ job enqueuing on create and rerun; task state reset on rerun.
- Response models expose PRD fields: status, risk level, issue count, created/updated timestamps.

Verification:

- `uv run python -m pytest tests/` passes with 17 tests (9 lifecycle API tests + 8 prior tests).
- Lifecycle tests cover: validation errors, 50k limit, create + enqueue, list filtering, detail, soft delete exclusion, rerun reset, and deleted-task rejection.

## Implement diff parser and change metrics

Status: completed by backend-engineer on 2026-05-29.

Delivered scope:

- Unified diff parser with file splitting, hunk line counting, rename/new/deleted file detection, and language hints for 40+ file extensions.
- Plain code snippet fallback when input lacks git diff headers.
- Test path detection via path patterns, sensitive keyword extraction from file paths.
- Structured output: file entries, hunks, and aggregated diff metrics (file count, line deltas, test coverage, keywords, languages).

Verification:

- `uv run python -m pytest tests/` passes with 32 tests (15 parser tests + 17 prior tests).
- Parser tests cover: multi-file diff, rename paths, new/deleted file modes, hunk line counts, empty/whitespace input, plain snippet fallback, language detection, test file detection, and sensitive keywords.

## Implement Review rule engine

Status: completed by backend-engineer on 2026-05-29.

Delivered scope:

- Six hard-rule checkers: banned content (console.log, debugger, TODO, etc.), missing tests, security keywords (hardcoded secrets, eval, SQL injection), generic variable names, missing function docstrings, and controller-layer DB access.
- Rule engine dispatches checkers by rule type, skips disabled rules, passes parsed diff for test/module checks and raw diff content for line-level checks.
- RuleMatch dataclass with rule ID, type, severity, description, file path, line hint, and code snippet fields.
- All six `RuleType` enum values have registered checkers.

Verification:

- `uv run python -m pytest tests/` passes with 52 tests (20 rule engine tests + 32 prior tests).
- Rule engine tests cover: each checker type (banned, test, security, naming, docs, module), disabled rule exclusion, multiple enabled rules, unknown rule types, checker coverage completeness, and edge cases (deleted-only files, empty diffs).

## Implement LLM adapter and mock provider

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- Abstract `LLMProvider` base class with `generate_review` interface for IOC.
- `MockLLMProvider` returning canonical structured review output for tests and demo without real LLM calls.
- `OpenAICompatibleProvider` with bearer auth, JSON mode, configurable base URL, model, and timeout.
- Log redaction for full prompt and result content; prompt preview capped at 200 chars.
- Factory function auto-selects MockLLM when API key is unset or mock is enabled.
- Error hierarchy: `LLMError` base, `LLMTimeoutError`, `LLMResponseError`.

Verification:

- `uv run python -m pytest tests/` passes with 52 tests (20 LLM adapter tests + 32 prior tests).
- Adapter tests cover: MockLLM output structure and idempotency, OpenAI success/error/timeout/JSON/invalid/network paths, bearer auth verification, log redaction, factory selection, and error hierarchy.

Next backend milestone:

## Implement AI Review orchestration worker

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- Full orchestration pipeline: task load, status update (pending->running->completed/failed), diff parse, rule load+engine, prompt build with system/rules/diff layers, LLM call, output validation/normalization, report+issue persistence.
- `_build_prompt` assembles four-layer prompt: system role, review policy, team rules, PR context with diff metrics.
- `_validate_and_normalize_ai_output` enforces enum values, fills missing fields, filters unknown rule IDs, and ensures high-risk issues have suggestions.
- `_persist_report` writes `ReviewReport` and `ReviewIssue` rows atomically, updates task risk level and issue count.
- `run_review_orchestrator` handles deleted task skip, LLM errors writing failure state, and unexpected exceptions caught with error message.

Verification:

- `uv run python -m pytest tests/` passes with 81 tests (9 orchestrator tests + 72 prior).
- Orchestrator tests cover: full success pipeline, report persistence, issue persistence, LLM failure state, error message preservation, rerun clearing failure, invalid enum normalization, missing field completion, and enabled-rule-only loading.

Next backend milestone:

## Validate and normalize AI Review output

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- `validate_ai_output` module with typed dataclasses for ValidatedSummary, ValidatedRisk, ValidatedIssue, and ValidatedReview.
- Enum normalization for risk level, issue type, severity, and confidence with safe defaults.
- Type coercion for strings, lists, and locations; graceful degradation for non-dict/non-list inputs.
- Issue sorting by severity (high first), stale/unknown rule ID stripping, missing description filtering.
- Raw AI output preserved alongside validated result for debugging.

Verification:

- `uv run python -m pytest tests/` passes with 95 tests (23 validator tests + 72 prior).
- Validator tests cover: valid output acceptance, invalid enum normalization, missing field defaults, issue re-sorting, stale rule ID filtering, non-dict/none/list/string input, type coercion, and raw preservation.

Next backend milestone:

## Implement history filtering and dashboard metrics API

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- `GET /api/metrics/dashboard` returning total tasks, tasks in last 30 days, total issues, risk distribution, useful/false_positive/adoption rates.
- Added `risk_level`, `created_after`, `created_before` query filters to `GET /api/review-tasks` list endpoint.
- Owner-scoped metrics via demo owner header; deleted tasks and their issues/feedback excluded.
- Zero-division safe feedback rate calculations return 0.0 for empty data.

Verification:

- `uv run python -m pytest tests/` passes with 116 tests (12 metrics + 104 prior).
- Metrics tests cover: risk level filter, date range filters, combined filters, deleted exclusion, total tasks, risk distribution, 30-day window, issue count, feedback rates, empty dashboard zeros, and owner isolation.

Next backend milestone:

- Implement baseline authentication and logging guardrails.
