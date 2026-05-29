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

Next backend milestone:

- Implement the diff parser module so the worker can parse diff input for metric extraction and prompt building.
