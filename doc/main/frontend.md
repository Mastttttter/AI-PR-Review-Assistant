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

Next frontend milestone:

- Implement the new Review task form using the typed API request layer.
