# Frontend Milestone Notes

## Build application shell and navigation

Status: completed by frontend-engineer on 2026-05-29.

Delivered scope:

- React TypeScript SPA shell with persistent navigation for 工作台, 新建 Review, 历史记录, 规则配置, and report detail routes.
- Shared layout with header, navigation, loading state, error state, and unknown-route fallback.
- Route tests covering every MVP page entry, fallback behavior, navigation links, and report state shells.
- Vite build setup, TypeScript configuration, package lockfile, and generated-artifact ignore rules.

Verification:

- `pnpm typecheck` passes.
- `pnpm test` passes with 8 route tests.
- `pnpm build` passes.
- Local dev server starts and serves the SPA entry route.
- Headless browser verification could not be independently rerun in chief review because `agent-browser` is not installed in this environment; frontend engineer reported a successful headless route smoke across all routes and fallback.

## Define frontend API types and request layer

Status: completed by frontend-engineer on 2026-05-29.

Delivered scope:

- Typed request and response models for Review tasks, reports, issues, rules, and feedback.
- Centralized API client covering task lifecycle, report retrieval, rule CRUD, rule enable/disable, and issue feedback endpoints.
- Automatic request snake-case serialization, response camel-case normalization, and user-readable request errors.
- Chinese labels for English API enum values, aligned with backend persistence schema rule types.
- MockLLM-shaped report and rule fixtures plus API client tests for success, errors, filters, and feedback.

Verification:

- `pnpm typecheck` passes.
- `pnpm test` passes with 13 tests.
- `pnpm build` passes.

## Implement new Review task form

Status: completed by frontend-engineer on 2026-05-29.

Delivered scope:

- Form with PR title, PR description, project name, target branch, developer name, and diff content fields.
- Client-side validation: PR title and diff required, diff capped at 50k characters, live character count.
- Submission with loading state, API error surfacing, and navigation to task report on success.
- Form disables submit during creation, cancel button returns to workbench.
- Testable via injected API client prop; form styles responsive with mobile grid reflow.

Verification:

- `pnpm typecheck` passes.
- `pnpm test` passes with 17 tests (4 review form tests).
- `pnpm build` passes.

## Implement Review status polling flow

Status: completed by frontend-engineer on 2026-05-29.

Delivered scope:

- `ReportPage` with `setTimeout`-based polling at configurable 2s interval, auto-cleanup on unmount.
- Polls task status endpoint; on completed, fetches report; on failed, preserves task context with error message.
- `ReportDetailCard` with AI summary, risk level badge with reasons, issue statistics grid, and severity-sorted issue list.
- `TaskContextBar` preserves PR title, project, developer, and status pill on all non-completed states.
- Status pills and risk badges styled per state (pending/steel, running/accent, completed/green, failed/red, risk low/medium/high).

Verification:

- `pnpm typecheck` passes.
- `pnpm test` passes with 19 tests (4 polling flow tests).
- `pnpm build` passes.
- Polling tests cover: running-to-completed auto-reveal, failed context preservation, network error handling, and pending state display.

## Implement structured Review report detail page

Status: completed by frontend-engineer on 2026-05-29.

Delivered scope:

- PR info section with title, description, project, branch, developer, created time, and status pill.
- AI summary with purpose, business impact, changed modules, key files, and test/security notes.
- Risk level with colored per-level badge and numbered reason list.
- 5-column issue stats grid (total, high, medium, low, rule hits) with severity-colored numbers.
- Severity-grouped issue list (high/medium/low) with colored section headers, sorted high-first.
- Each issue card: per-severity badge, type badge, confidence badge, feedback badge, title, description, code location+snippet block, suggestion with accent border, matched rule IDs.
- Empty and minimal report fixtures; graceful handling of missing optional fields.

Verification:

- `pnpm typecheck` passes.
- `pnpm test` passes with 29 tests (10 report detail tests).
- `pnpm build` passes.
- Report tests cover: PR info, AI summary, risk level, issue stats, grouped/sorted issues, confidence badges, feedback state, code snippets, matched rules, empty report, and minimal report.

Next frontend milestone:


## Implement history Review records page

Status: completed by frontend-engineer on 2026-05-29.

Delivered scope:

- HistoryPage component with filterable task list, loading/error/empty states.
- Filter bar: project name, risk level select, status select, date range inputs.
- 7-column table: PR title, project, creator, time, risk badge, issue count, status pill.
- Clickable rows navigate to task detail; all four task statuses visually distinguishable.

Verification:

- pnpm typecheck passes.
- pnpm test passes including 9 history tests.
- pnpm build passes.

Next frontend milestone:

- Implement the Review rule configuration page with create, edit, enable/disable, and delete.
