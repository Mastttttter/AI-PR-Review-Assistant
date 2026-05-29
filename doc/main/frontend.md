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

Next frontend milestone:

- Implement the Review status polling flow so users see live task progress after form submission.
