# Backend Todo List

Chief engineer writes tasks. Backend engineer updates completed items after implementation, test, commit, and role sign-off.

## P0 main review flow

- [x] Scaffold backend API, worker, and shared settings
  - Scope: Set up FastAPI service, RQ worker entrypoint, shared configuration, environment variables, health endpoint, and local development commands.
  - Acceptance: API and RQ worker can start independently; health check reports service readiness without requiring an LLM call.
  - Tests: Health endpoint test; startup smoke test for API and RQ worker.
  - Owner: backend-engineer
  - Signed-off: backend-engineer, 2026-05-29

- [x] Create persistence schema and migrations
  - Scope: Add database models and migrations for review tasks, review reports, review issues, review rules, and issue feedback with soft delete support for tasks.
  - Acceptance: Schema stores PR metadata, diff content capped at 50k characters, demo owner field, English technical enum values, task status, report summary, risk reasons, issue details, matched rule IDs, and latest feedback status.
  - Tests: Migration up/down test on a clean database; model persistence tests for every table; enum and 50k diff-limit persistence tests.
  - Owner: backend-engineer
  - Signed-off: backend-engineer, 2026-05-29

- [x] Implement Review task lifecycle API
  - Scope: Implement create, list, get detail, soft delete, and rerun endpoints for Review tasks; validate required PR title and diff content.
  - Acceptance: Creating a task validates the 50k character diff limit, stores input with a simplified demo owner field, returns a task id and status, enqueues an RQ Review job, and never exposes deleted tasks as active records.
  - Tests: API tests for validation errors, diff limit, successful creation response shape, list filters, detail lookup, soft delete, and rerun behavior.
  - Owner: backend-engineer
  - Signed-off: backend-engineer, 2026-05-29

- [x] Implement diff parser and change metrics
  - Scope: Parse unified diff or code snippet input into file entries, hunks, line counts, language hints, test-file detection, and sensitive keyword signals.
  - Acceptance: Parser supports normal unified diffs and graceful fallback for plain code snippets; metrics are available for risk assessment and prompt context.
  - Tests: Unit tests for multi-file diff, rename-like paths, test file detection, sensitive keywords, empty invalid diff, and plain snippet fallback.
  - Owner: backend-engineer
  - Signed-off: backend-engineer, 2026-05-29

- [x] Implement Review rule engine
  - Scope: Load enabled rules and evaluate hard-rule matches for banned content, missing tests, security keywords, naming/documentation constraints, and module constraints where deterministic matching is feasible.
  - Acceptance: Initial rule matching uses hard-rule checks plus LLM review explanation, not complex static analysis; rule matches can become report issues or matched rule IDs, and disabled rules never affect Review results.
  - Tests: Unit tests for each supported hard-rule type, enabled/disabled behavior, and matched rule propagation with MockLLM explanation fixtures.
  - Owner: backend-engineer
  - Signed-off: backend-engineer, 2026-05-29

- [x] Implement LLM adapter and mock provider
  - Scope: Add provider abstraction, OpenAI-compatible adapter shape, mock adapter for tests/demo, server-side API key handling, timeout handling, and no frontend LLM exposure.
  - Acceptance: Business code calls the adapter interface only; MockLLM is the canonical acceptance-test provider; tests can run without a real LLM; full diff content is not logged.
  - Tests: Unit tests for MockLLM provider, adapter error handling, timeout path, and redacted logging behavior.
  - Owner: backend-engineer
  - Signed-off: backend-engineer, 2026-05-30

- [ ] Implement AI Review orchestration worker
  - Scope: Process queued Review jobs through task load, status update, diff parse, rule evaluation, prompt build, LLM call, result validation, report persistence, and final status update.
  - Acceptance: RQ worker transitions pending to running to completed or failed; failures preserve a useful error state; completed reports are persisted atomically.
  - Tests: Worker integration tests using MockLLM for successful Review, LLM failure, invalid AI output, and retry or rerun behavior.
  - Owner: backend-engineer
  - Signed-off: pending

- [ ] Validate and normalize AI Review output
  - Scope: Enforce structured JSON schema for summary, risk level, risk reasons, issues, severity, location, suggestion, confidence, and matched rule IDs using English technical enum values.
  - Acceptance: Invalid enum values, missing required fields, high/medium issues without suggestions, and unknown matched rules are rejected or normalized safely; API responses keep English values for frontend label mapping.
  - Tests: Schema validation tests for valid MockLLM output, missing fields, invalid enums, unsorted issues, missing suggestions, and stale rule IDs.
  - Owner: backend-engineer
  - Signed-off: pending

- [ ] Implement report retrieval API
  - Scope: Return structured report details with PR basics, status, summary, risk, reasons, issue statistics, grouped/sorted issues, matched rules, suggestions, and feedback states.
  - Acceptance: Report API supports frontend detail page without additional data stitching; issues are sorted by severity and include all PRD-required fields.
  - Tests: API tests for completed task report, pending task response, failed task response, empty issue list, and severity sorting.
  - Owner: backend-engineer
  - Signed-off: pending

## P1 rules, history, and feedback

- [ ] Implement Review rule CRUD API
  - Scope: Add create, list, update, enable, disable, and delete endpoints for Review rules with validation for name, description, type, severity, and enabled state.
  - Acceptance: Enabled rules are available to the worker, disabled/deleted rules are excluded, and invalid rule payloads are rejected.
  - Tests: API tests for rule CRUD lifecycle, validation errors, enable/disable transitions, and worker rule loading.
  - Owner: backend-engineer
  - Signed-off: pending

- [x] Implement issue feedback API
  - Scope: Add per-issue feedback update endpoint for useful, useless, false positive, adopted, and ignored states, with optional comment storage.
  - Acceptance: Feedback stores the latest status per issue with an optional comment and updates the issue-visible state without changing AI report content.
  - Tests: API tests for each feedback status, optional comment, invalid status, missing issue, repeated update, and report response reflecting latest feedback.
  - Owner: backend-engineer
  - Signed-off: backend-engineer, 2026-05-30

- [ ] Implement history filtering and dashboard metrics API
  - Scope: Support task list filters for project, risk level, status, and date range; expose lightweight counts for recent tasks, risk distribution, issue counts, useful rate, false-positive rate, and adoption rate where data exists.
  - Acceptance: Frontend can render history and dashboard cards without complex analytics; metrics remain accurate for soft-deleted records.
  - Tests: Query tests for each filter; metrics aggregation tests with mixed task statuses, severities, and feedback states.
  - Owner: backend-engineer
  - Signed-off: pending

## Cross-cutting backend quality

- [ ] Add baseline authentication and access checks
  - Scope: Implement a simplified demo owner field suitable for MVP so reports are not globally public; ensure report, task, rule, and feedback endpoints enforce owner matching.
  - Acceptance: Requests without the expected demo owner cannot read submitted diff content or reports; no full authentication or enterprise permission system is introduced.
  - Tests: API ownership tests for own records, other-owner records, missing owner, and deleted records.
  - Owner: backend-engineer
  - Signed-off: pending

- [ ] Add sensitive-data logging and storage guardrails
  - Scope: Prevent full diff/report content from application logs, keep LLM API keys in server environment only, and document which sensitive fields are stored.
  - Acceptance: Normal request, worker, and error logs do not print full submitted code or full AI report content.
  - Tests: Logging tests or manual log inspection for create task, worker success, worker failure, and report retrieval paths.
  - Owner: backend-engineer
  - Signed-off: pending

- [ ] Provide Docker Compose development stack
  - Scope: Add local services for backend API, worker, PostgreSQL, Redis, and optionally frontend proxy integration through nginx or documented ports.
  - Acceptance: A developer can start the MVP stack locally and run the main Review flow against seeded or mock LLM data.
  - Tests: Compose startup smoke test; API health check; worker consumes one mock Review job.
  - Owner: backend-engineer
  - Signed-off: pending

- [ ] Complete backend verification suite
  - Scope: Add unit, API, worker integration, migration, and smoke tests for the complete create Review to report retrieval loop using the mock LLM provider.
  - Acceptance: Backend verification commands pass locally and cover validation, queue processing, report persistence, rule matching, and feedback.
  - Tests: Type/static checks if configured; lint; unit tests; API tests; worker integration tests; migration tests.
  - Owner: backend-engineer
  - Signed-off: pending
