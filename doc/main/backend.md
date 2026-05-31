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

## Implement report retrieval API

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- `GET /api/review-tasks/{task_id}/report` endpoint returning full structured report.
- `ReportResponse` model with PR basics, status, risk level, error message, summary, risk reasons, issue stats, and severity-sorted issues.
- `ReportIssueResponse` with all PRD-required fields: type, severity, description, suggestion, confidence, code location, matched rule IDs, and feedback status.
- Owner access control via demo owner header; deleted tasks excluded.
- Handles pending (null summary), failed (preserves error), completed, and empty-issue states.

Verification:

- `uv run python -m pytest tests/` passes with 115 tests (11 report API + 104 prior).
- Report tests cover: PR basics, summary/risk population, severity sorting, issue stats, PRD field completeness, feedback status, pending task null summary, failed task error, access control, deleted exclusion, and empty issues.

Next backend milestone:

## Implement Review rule CRUD API

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- Full REST API: create, list, update, enable, disable, and soft-delete endpoints.
- Pydantic request/response models with validation for name, description, rule type, and severity enum fields.
- Owner-enforced access via demo owner header; deleted rules excluded from list.
- Enable/disable as idempotent PATCH operations returning updated rule.

Verification:

- `uv run python -m pytest tests/` passes with 131 tests (16 rules CRUD + 115 prior).
- CRUD tests cover: create, validation, invalid enums, disabled creation, owner-filtered list, full update, access control, enable/disable, idempotency, soft delete, and post-delete exclusion.

Next backend milestone:

## Implement issue feedback API

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- `PATCH /api/review-issues/{issue_id}/feedback` endpoint accepting feedback status and optional comment.
- Updates `ReviewIssue.feedback_status` and creates `IssueFeedback` history record.
- All five PRD statuses accepted: useful, useless, false_positive, adopted, ignored.
- Owner-enforced access; AI report content (description, suggestion) unchanged by feedback.

Verification:

- `uv run python -m pytest tests/` passes with 150 tests (19 feedback + 131 prior).
- Feedback tests cover: all 5 statuses, issue update, optional/null comment, feedback record persistence, repeated update overwrite, invalid status 422, missing issue 404, missing owner 422, and report content immutability.

Next backend milestone:

## Implement history filtering and dashboard metrics API

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- `GET /api/metrics/dashboard` returning total tasks, tasks in last 30 days, total issues, risk distribution, useful/false_positive/adoption rates.
- Added `risk_level`, `created_after`, `created_before` query filters to task list endpoint.
- Owner-scoped metrics; deleted tasks/their issues/feedback excluded; zero-division safe rates.

Verification:

- 162 tests pass (12 metrics + 150 prior).
- Metrics tests cover: risk level filter, date range filters, combined filters, deleted exclusion, total tasks, risk distribution, 30-day window, issue count, feedback rates, empty dashboard, and owner isolation.

Next backend milestone:

- Implement baseline authentication and logging guardrails.

## MVP Verification Summary

Status: verified by verify-engineer on 2026-05-30.

All P0 and P1 backend features confirmed working via browser-based end-to-end tests:

**Backend API endpoints verified:**
- POST /api/review-tasks: creates review task and triggers async processing
- GET /api/review-tasks: lists tasks with filters (project, risk level, status)
- GET /api/review-tasks/{id}: returns task details
- GET /api/review-tasks/{id}/report: returns nested response with task, summary, risk, issue_stats, issues
- PATCH /api/review-issues/{id}/feedback: persists user feedback
- POST/GET/PATCH/DELETE /api/review-rules: full CRUD for rule configuration
- GET /api/review-rules: lists rules for current owner

**Backend fixes applied during verification:**
1. Task #1 (commit 22d9027): Rule ID propagation in LLM prompt
   - Added rule_id to pre-matched rule results sent to LLM
   - Updated prompt instruction to use rule IDs in matched_rule_ids
   - Fixed rule integration: created rules now appear in report's matched_rule_ids

2. Task #2 (commit 9a727d2): Report API response restructure
   - Changed from flat fields to nested structure: task, summary, risk, issue_stats
   - Parse summary JSON string into object
   - Nest risk_level and risk_reasons into risk object
   - Add rule_hits count to issue_stats
   - Nested issue location (file_path, line_hint, code_snippet)
   - Updated tests: 165/165 passing

**Integration test results:**
- Rule configuration integration: PASS (rule ID appears in matched_rule_ids)
- Report detail page rendering: PASS (no TypeError, all sections visible)
- History page with filters: PASS (all filters work)
- User feedback persistence: PASS (feedback survives page refresh)

3. Task #4 (commit 4913231): .env variable naming fix for real LLM
   - Settings used env_prefix="APR_" expecting APR_LLM_API_KEY, APR_LLM_BASE_URL, APR_LLM_MODEL but .env had ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL, ANTHROPIC_MODEL
   - Added APR_LLM_* variables to .env with real credentials from existing ANTHROPIC_* keys
   - Updated .env.example to document all LLM configuration variables
   - Adjusted test for mock_enabled path since .env now always provides the API key
   - 173/173 tests passing; real LLM provider loads when APR_LLM_MOCK_ENABLED=false

4. Task #14 (pending merge): Anthropic-compatible LLM provider
   - Added `AnthropicLLMProvider` using Anthropic Messages API format
   - Uses `x-api-key` header, `anthropic-version: 2023-06-01`, top-level `system`, content blocks response
   - Added `LLMQuotaExhaustedError` for HTTP 429 responses
   - Added `APR_LLM_PROVIDER` setting (default "openai", set to "anthropic" for Aliyun endpoint)
   - 237/237 tests passing (17 new Anthropic provider + factory tests)

Backend is feature-complete for MVP.

## Verify AI Review Generation (Summary, Risk, Issues, Suggestions)

Status: verified by verify-engineer on 2026-05-30.

Testing engineer confirmed backend produces correct AI review output matching all 13 frontend criteria:

AI Review Output Structure:
- Summary object with purpose, changed_modules, key_files, business_impact, test_or_security_notes
- Risk object with level enum and reasons array
- Issues array with title, type, severity, description, location (file_path/line_hint/code_snippet), suggestion
- Issues sorted by severity (high/medium/low)

Verification Results:
1. Summary generation works correctly - natural language, mentions modules/files
2. Risk level assessment accurate with explanatory reasons
3. Issue identification comprehensive - each issue includes all required fields
4. Modification suggestions concrete and reference code context
5. Output structure matches frontend ReviewReport type contract
6. All enum values valid (risk level, severity, issue type)

Backend orchestrator, LLM adapter, and validator all functioning correctly.

## Assistant Settings API with Config Persistence

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- `GET /api/settings` returns merged config from config.json + env vars with masked API keys (only last 4 characters shown).
- `PUT /api/settings` writes provider config to `backend/config/config.json`, auto-creating the directory.
- `POST /api/settings/test` validates provider connectivity with a minimal API call, returning success/failure with reason.
- Config loader module (`core/config_loader.py`) with shared `load_llm_config()` implementing the priority chain: config.json values override provider-specific env vars (APR_OPENAI_*/APR_ANTHROPIC_*), which override legacy APR_LLM_* defaults.
- Six new Settings fields: `openai_base_uri`, `openai_api_key`, `openai_model`, `anthropic_base_uri`, `anthropic_api_key`, `anthropic_model`.
- LLM factory (`create_llm_provider`) updated to use `load_llm_config()` for provider selection and configuration, with unknown-provider normalization to openai.

Bug fixes applied during testing:

- PUT endpoint preserves existing real API key when receiving masked placeholder values (starts with `***-`) or empty strings, preventing accidental overwrite.
- POST /test endpoint resolves stored API key from config when no key is provided or a masked placeholder is sent.

Verification:

- 286 tests pass (20 settings API tests, 7 config loader factory tests, 259 prior tests).
- Settings tests cover: env var defaults, masked keys, config.json persistence, update, override priority, connectivity success/failure/timeout/invalid-key/403/server-error, put-preserves-key (masked, empty, real), test-uses-stored-key (missing, direct, none-configured).

## Fix OS Env Pollution in Settings Tests

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- Replaced monkeypatch.setenv() calls in 3 GetSettings tests (test_returns_env_var_defaults_when_no_config_file, test_masks_api_keys, test_masks_none_api_key) with monkeypatch.setattr() mocking load_llm_config() directly.
- Each test returns a self-contained controlled config dict, fully immune to OS-level APR_OPENAI_*/APR_ANTHROPIC_* environment variables.
- Net change: +33/-34 lines (simpler, drops ~5 setenv calls per test).

Verification:

- 287/287 tests pass; 21 settings API tests pass independently.

## Fix Report 500 for String-Typed Summary Fields

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- Added _normalize_list() helper in review_tasks.py that coerces string values to single-element lists for changed_modules and key_files fields in _parse_summary.
- List values pass through unchanged; null/missing default to empty list.
- Prevents Pydantic validation error (500) when AI output has string-typed list fields.

Verification:

- 290/290 tests pass (3 new normalization tests).

## System Prompt Configuration

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- Added `system_prompt` setting (APR_SYSTEM_PROMPT env var, default empty).
- Added system_prompt to config_loader.py: included in default config dict and read from config.json.
- Added system_prompt to settings API: GET returns it unmasked, PUT persists it.
- Updated _build_prompt in orchestrator.py: reads system_prompt from load_llm_config(); uses custom prompt when non-empty, falls back to hardcoded SYSTEM_PROMPT when empty/whitespace.

Verification:

- 297/297 tests pass (7 new: 3 config_loader, 2 settings API, 2 orchestrator).

## PR Fetch API

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- Created POST /api/pr-fetch endpoint that accepts a GitHub PR URL and returns title, description, and diff_content.
- URL parsing extracts owner/repo/pull_number, handles trailing paths and fragments.
- Two GitHub API calls: metadata (Accept: vnd.github.v3+json) and diff (Accept: vnd.github.v3.diff).
- Diff capped at 50k characters.
- Error handling: invalid URL -> 400, 404 -> 404, 403 -> 403, 429 -> 429, timeout/network -> 502.
- Demo owner header required.

Verification:

- 312/312 tests pass (15 new PR fetch endpoint tests).

## Extend PR Fetch Response + Add pr_url to Review Task Model

Status: completed by backend-engineer on 2026-05-30.

Delivered scope:

- Part A: Extended `FetchPrResponse` in POST /api/pr-fetch with `project_name` (from `base.repo.full_name`), `target_branch` (from `base.ref`), and `developer_name` (from `user.login`). All fields default to `""` when GitHub API returns missing nested data.
- Part B: Added `pr_url` column (String 2048, nullable) to `ReviewTask` model with Alembic migration `3134f36008b3_add_pr_url_to_review_tasks`. Updated `ReviewTaskCreate` schema, store on create, and return in `ReviewTaskDetailResponse`, `ReviewTaskListItem`, and `ReportTaskNested`.
- Updated docs: `doc/chief/PRD.md` section 7.12, `doc/chief/tecDoc.md` PR fetch API section, `doc/backend/todolist.md`.

Verification:

- 317/317 tests pass (5 new: 2 PR fetch extended fields, 2 review task lifecycle pr_url, 1 report pr_url).

## Go API Dispatcher Server

Status: completed by backend-engineer on 2026-05-31.

Delivered scope:

- Go HTTP server in `dispatcher/` using gin-gonic/gin with two endpoints.
- `POST /api/issue-key`: generates cryptographically random temporary API keys (32 hex chars with `tmp-` prefix), stored in memory with 10-minute TTL. Key rotation on subsequent calls — existing valid key is destroyed and replaced. Thread-safe via sync.Mutex.
- `GET /health`: returns `{"status": "ok"}` with HTTP 200.
- Environment variable configuration: `DISPATCHER_LLM_API_KEY` (required, fatal startup error if missing), `DISPATCHER_LLM_BASE_URL` (default: `https://api.openai.com/v1`), `DISPATCHER_LLM_MODEL` (default: `gpt-4o-mini`), `DISPATCHER_PORT` (default: `8318`).
- Module path: `github.com/apr-review/dispatcher`.

Verification:

- `go build ./...` passes cleanly.
- `go test ./... -v` passes with 5/5 tests: health endpoint (200 + correct JSON), issue-key response structure (api_key prefix + length, base_uri, model, expires_in), key rotation (sequential calls return different keys), concurrent access safety (50 goroutines, no panics), missing API key detection.

## Dispatcher-Fetch Endpoint

Status: completed by backend-engineer on 2026-05-31.

Delivered scope:

- `POST /api/settings/dispatcher-fetch` endpoint in the settings API that proxies credential issuance from the Go dispatcher server.
- Accepts a dispatcher URL, calls `POST {url}/api/issue-key` via httpx with a 10-second timeout, overrides the `base_uri` in the response with the user-provided URL (since the dispatcher may report an internal Docker hostname that is unreachable from the browser).
- Pydantic request/response models: `DispatcherFetchRequest` (url field) and `DispatcherFetchResponse` (api_key, base_uri, model, expires_in).
- Error handling: connection refused/timeout returns HTTP 502 with descriptive message; dispatcher non-200 responses forwarded as 502.
- Requires `X-Demo-Owner` header (reuses existing `DemoOwnerHeader`).

Verification:

- 323/323 tests pass (6 new: success credentials, base_uri override, connection error 502, timeout 502, non-200 forwarding, owner header required).
