# Frontend Todo List

Chief engineer writes tasks. Frontend engineer updates completed items after implementation, test, commit, and role sign-off.

## P0 main review flow

- [x] Build application shell and navigation
  - Scope: Create the SPA layout for 首页 / 工作台, 新建 Review, 历史记录, 规则配置, and report detail routes; include consistent header, sidebar or top navigation, loading and error shells.
  - Acceptance: Users can navigate between all MVP pages without dead links, and unknown routes show a safe fallback.
  - Tests: Route rendering tests for every page entry; manual browser smoke test for navigation.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer

- [x] Define frontend API types and request layer
  - Scope: Add typed request and response models for review tasks, reports, issues, rules, and feedback; centralize API calls under one client layer.
  - Acceptance: UI code consumes typed API functions instead of hard-coded fetch calls; API enums use English technical values with Chinese UI labels; request errors surface user-readable messages.
  - Tests: Type check; mocked API unit tests for success and failure responses using MockLLM-shaped fixtures.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer

- [x] Implement new Review task form
  - Scope: Build PR title, PR description, project name, target branch, developer name, and diff input fields; use Monaco Editor or a diff-friendly text area for code changes.
  - Acceptance: PR title and diff are required; validation prevents empty submission and diff input over 50k characters; successful submission handles returned task id and status, enters generating state, and routes to the task/report flow.
  - Tests: Form validation tests; 50k diff-limit test; mocked submit test using task id plus status response; manual browser test with a sample diff.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30
  - Verification: Browser-based end-to-end test confirmed all acceptance criteria pass. Backend API contract fix (Task #2) resolved report rendering issue. Frontend code required no changes. 2026-05-30.

- [x] Implement Review status polling flow
  - Scope: Poll task and report endpoints after creation and while viewing an unfinished task; show pending, running, completed, and failed states.
  - Acceptance: Completed tasks automatically reveal the report; failed tasks show the failure state without losing the task context; polling assumes task creation returns only task id and status.
  - Tests: Mocked polling tests for pending-to-completed and running-to-failed transitions; manual browser test with delayed MockLLM-backed API.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30

- [x] Implement structured Review report detail page
  - Scope: Show PR basics, status, AI summary, risk level with reasons, issue statistics, grouped issue list, matched rules, suggestions, confidence, and code location snippets.
  - Acceptance: High-risk issues appear before medium and low; every issue clearly shows type, severity, explanation, suggestion, confidence, and feedback state.
  - Tests: Component tests with high, medium, low, empty, and malformed-but-accepted report fixtures; manual browser review of a full sample report.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30
  - Verification: All 13 acceptance criteria for PR Summary (PRD 7.2), Risk Level (PRD 7.3), Issue Identification (PRD 7.4), and Modification Suggestions (PRD 7.5) confirmed pass. 2026-05-30.

## P1 rules, history, and feedback

- [x] Implement history Review records page
  - Scope: Show historical tasks with title, project, creator, created time, risk level, issue count, and status; support project, risk, status, and date filters if backend endpoints are available.
  - Acceptance: Users can distinguish pending, running, completed, failed, and deleted states; users can open a task detail from the list.
  - Tests: List rendering tests; filter interaction tests with mocked query params; manual browser test on seeded task data.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30

- [x] Implement Review rule configuration page
  - Scope: Build rule list, create/edit form, severity selector, type selector, enable/disable action, and delete action.
  - Acceptance: Users can create, edit, enable, disable, and delete basic Review rules; validation requires name, description, type, severity, and enabled state.
  - Tests: CRUD interaction tests against mocked API; validation tests; manual browser test for full rule lifecycle.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30
  - Verification: Task #5 implemented full CRUD UI (replaced stub). All 10 acceptance criteria pass. Rule-to-report integration verified: matched_rule_ids displayed as "命中规则". Backend Task #1 resolved rule ID propagation in LLM prompt. Backend Task #6 enhanced MockLLMProvider to include rule IDs in mock output. 2026-05-30.

- [x] Implement per-issue feedback controls
  - Scope: Add feedback actions for useful, useless, false positive, adopted, and ignored on each issue in the report detail page.
  - Acceptance: Feedback can be submitted per issue as the latest status with an optional comment, the visible issue feedback state updates, and submit failure leaves the previous state intact with an error message.
  - Tests: Feedback component tests; mocked success and failure mutation tests; manual browser test on a MockLLM sample report.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30
  - Verification: Task #7 implemented feedback submission UI with 7 new tests. All 5 feedback options (useful, useless, false_positive, adopted, ignored) render per issue. Clicking submits via updateIssueFeedback API, updates local state immediately, shows loading state during submission, and displays error message on failure while preserving previous status. 2026-05-30.

- [x] Implement dashboard summary cards
  - Scope: Show create Review entry, recent Review tasks, risk statistics, and issue statistics on the home/workbench page.
  - Acceptance: Dashboard provides a clear entry to create a Review and a quick view of recent risk distribution without implying complex analytics beyond MVP.
  - Tests: Rendering tests for populated and empty states; manual browser test using seeded summary data.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30

## Cross-cutting frontend quality

- [x] Apply MVP UI polish and sensitive-data guardrails
  - Scope: Keep language engineering-focused, avoid marketing copy, avoid logging full diff/report content in browser console, and ensure long code snippets are readable without breaking layout.
  - Acceptance: Main pages are suitable for competition demo, high-risk findings stand out, and sensitive diff/report content is not intentionally logged.
  - Tests: Manual browser pass across all pages; console inspection during create, report, rule, and feedback flows.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, 2026-05-30

- [x] Complete frontend verification suite
  - Scope: Add or update frontend unit/component tests, type checking, linting, and an end-to-end smoke path from create Review to report feedback using mocked or local backend data.
  - Acceptance: Frontend verification commands pass locally and the smoke path covers the MVP value loop against MockLLM-backed data.
  - Tests: Type check; lint; unit/component suite; browser-driven smoke test with MockLLM fixtures.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, 2026-05-30

- [x] Reorganize frontend into `frontend/` directory
  - Scope: Move src/, index.html, package.json, pnpm-lock.yaml, tsconfig.json, vite.config.ts into a new frontend/ directory; update justfile with frontend-install, frontend-dev, frontend-build, frontend-test, frontend-verify commands following backend-dir pattern; delete root node_modules/.
  - Acceptance: Root directory clean (backend/, frontend/, doc/, docker-compose.yml, justfile, .gitignore). cd frontend && pnpm verify passes. just frontend-dev works. Backend unaffected.
  - Tests: pnpm verify (typecheck, 45 tests, build).
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer

## Bug fixes (2026-05-30)

- [x] Fix navigation dead link for /reviews/demo-report
  - Scope: Remove invalid "报告详情" nav item from navigationItems array pointing to non-existent UUID; update shell navigation test.
  - Acceptance: No dead nav links; report detail only reachable via history row clicks.
  - Tests: Updated App.test.tsx navigation test.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30

- [x] Implement live dashboard metrics on WorkbenchPage
  - Scope: Add DashboardResponse type, getDashboardMetrics() API method, update WorkbenchPage to fetch live data with loading/error states.
  - Acceptance: Dashboard shows real metrics from GET /api/metrics/dashboard instead of hardcoded numbers.
  - Tests: Added getDashboardMetrics mock to all test files; 45 tests pass.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30

- [x] Add "新建 Review" CTA button to WorkbenchPage
  - Scope: Add prominent primary button on WorkbenchPage navigating to /reviews/new per PRD 8.1.
  - Acceptance: Users can create a new review directly from the workbench landing page.
  - Tests: Rendered via WorkbenchPage component; navigates to /reviews/new route.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30

- [x] Remove duplicate HistoryPage test suite
  - Scope: Remove duplicate describe('History records page', ...) block from App.test.tsx.
  - Acceptance: No duplicate test definitions or function re-declarations.
  - Tests: 45 tests pass after removing 8 duplicate tests.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, verify-engineer 2026-05-30

## Assistant settings feature

- [x] Add assistant settings page with AI provider configuration UI
  - Scope: Build SettingsPage at /settings route with OpenAI and Anthropic provider forms; add nav item, route, API types, and client methods; implement masked API key display with reveal toggle; handle load, edit, save, save-success, save-error, testing, test-success, and test-failure states; fix masked-key sentinel handling so masked backend keys are cleared to empty on save and omitted on test.
  - Acceptance: Users can view and edit provider configs, save them, and test connectivity per provider; masked API keys display last 4 chars and auto-reveal on focus; save/load uses GET/PUT /api/settings; test uses POST /api/settings/test; green success/red failure badges shown inline.
  - Tests: 59 tests pass (12 new: 8 SettingsPage component tests + 4 API client settings tests); typecheck and build clean.
  - Owner: frontend-engineer
  - Signed-off: frontend-engineer, 2026-05-30
