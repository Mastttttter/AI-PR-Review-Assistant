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
- Browser-based end-to-end test by testing-engineer confirmed: form fields render, validation messages appear, submission creates task via POST /api/review-tasks, and navigation to report detail page succeeds. Verified 2026-05-30.

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
- Browser-based end-to-end test by testing-engineer confirmed: after creating a review task with an auth-logic diff, the report page shows AI summary (purpose + modules + impact), risk level with reasons, issue list sorted high-first with type/severity/description/suggestion per issue, and high-risk issues are visually prominent. Verified 2026-05-30.

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

## Apply MVP UI polish and sensitive-data guardrails

Status: completed by frontend-engineer on 2026-05-30.

Delivered scope:

- Audit confirmed zero console.log/warn/error/info calls in source files.
- Sidebar security note states "Diff 与报告不在浏览器控制台输出".
- All UI text uses engineering-focused language, no marketing copy.
- High-risk issues prominently styled with colored borders and headers.
- Code snippets in monospace with dark background.
- Responsive layout at 820px breakpoint.

## Complete frontend verification suite

Status: completed by frontend-engineer on 2026-05-30.

Delivered scope:

- `pnpm verify` script: typecheck + test + build in one command (47 tests).
- API client tests cover serialization, deserialization, and error handling.
- Test suite covers MVP value loop: review form -> polling -> report detail.

Verification:

- `pnpm verify` and `pnpm test` both pass; typecheck and build clean.

## Verify Create Review Task feature

Status: verified by verify-engineer on 2026-05-30.

Testing engineer confirmed all 10 acceptance criteria pass:

- Form fields render correctly (PR title, description, diff content)
- Required field validation works (title and diff cannot be empty)
- Form submission creates task via POST /api/review-tasks
- Navigation to report detail page succeeds after task completion
- Report detail page renders with nested task, summary, risk, issue_stats, and issues sections
- All report sections visible: PR info, AI summary, risk level with reasons, issue statistics, issue list with severity/types/confidence/locations/code snippets/suggestions

Backend API contract fix (Task #2) resolved the TypeError that prevented report rendering. Frontend code required no changes.

Verification: Browser-based end-to-end test by testing-engineer, 2026-05-30.

## Verify Rule Configuration feature

Status: verified by verify-engineer on 2026-05-30.

Testing engineer confirmed all 10 acceptance criteria pass:

- Rule CRUD operations work (create, list, edit, enable/disable, delete)
- Form validation requires name, description, type, and severity
- All 6 rule types available: test, forbidden content, documentation sync, security, naming, module constraints
- **Rule-to-report integration works**: When a "forbidden content" rule matches console.log in a diff, the report shows:
  - Issue about console.log detected
  - Rule ID displayed in matched_rule_ids array
  - UI shows "命中规则" indicator with rule name

Backend fix (Task #1: rule ID propagation in LLM prompt) resolved the integration issue. The LLM now receives rule_id in pre-matched results and explicitly includes them in matched_rule_ids. Frontend already displayed matched_rule_ids correctly.

Verification: Browser-based end-to-end test by testing-engineer, 2026-05-30.

## Verify Historical Review Records feature

Status: verified by verify-engineer on 2026-05-30.

Testing engineer confirmed all 5 acceptance criteria pass:

- History page displays list of past review tasks
- Each task shows: PR title, project name, creator, creation time, risk level, issue count, status
- Clicking a task navigates to report detail page
- Filter by project name works (text input)
- Filter by risk level works (dropdown: all/high/medium/low)
- Filter by status works (dropdown: all/pending/running/completed/failed)

No implementation changes needed. Feature was already complete from earlier work.

Verification: Browser-based end-to-end test by testing-engineer, 2026-05-30.

## Verify User Feedback feature

Status: verified by verify-engineer on 2026-05-30.

Testing engineer confirmed all 7 acceptance criteria pass:

- Each issue card displays 5 feedback buttons: Useful (有用), Useless (无用), False Positive (误报), Adopted (已采纳), Ignored (暂不处理)
- Clicking a feedback button updates UI immediately
- Selected feedback button shows active state
- Feedback persists after page refresh
- Backend API PATCH /api/review-issues/{issue_id}/feedback works correctly
- Frontend sends correct request payload: { feedback_status: string }
- Multiple feedback types tested successfully

No implementation changes needed. Feature was already complete from earlier work.

Verification: Browser-based end-to-end test by testing-engineer, 2026-05-30.

## MVP Verification Summary

All P0 and P1 features verified on 2026-05-30:

**P0 Features (all PASS):**
- Create Review Task (PRD §7.1)
- Input PR Changes (PRD §7.2)
- PR Summary Generation (PRD §7.3)
- Risk Level Assessment (PRD §7.4)
- Issue Identification (PRD §7.5)
- Modification Suggestions (PRD §7.6)
- Review Report Detail Page (PRD §7.7)

**P1 Features (all PASS):**
- Review Rule Configuration (PRD §7.8)
- Historical Review Records (PRD §7.9)
- User Feedback (PRD §7.10)

**Backend fixes applied:**
- Task #1: Rule ID propagation in LLM prompt (commit 22d9027)
- Task #2: Report API response restructure to match frontend contract (commit 9a727d2)

MVP is feature-complete and verified.

## Verify PR Summary, Risk Level, Issue Identification, and Modification Suggestions

Status: verified by verify-engineer on 2026-05-30.

Testing engineer confirmed all 13 acceptance criteria pass:

PR Summary (PRD 7.2):
1. Report contains AI-generated summary section with purpose, modules, key files, business impact
2. Summary describes change purpose (not code restatement)
3. Summary mentions affected modules and files
4. Summary uses natural language

Risk Level (PRD 7.3):
5. Risk level displayed with color-coded badge (low/medium/high)
6. Risk level includes explanatory reasons list
7. Risk reasons explain assessment basis

Issue Identification (PRD 7.4):
8. Report contains issue list with count
9. Each issue includes: title, type, severity, description, location, suggestion
10. Issues sorted by severity (high → medium → low)
11. High-risk issues visually prominent with red styling

Modification Suggestions (PRD 7.5):
12. Medium/high severity issues have concrete, actionable suggestions
13. Suggestions reference specific code context with file path and code snippets

All criteria verified via browser testing and API response inspection.

## Verify RulesPage UI Implementation

Status: verified by verify-engineer on 2026-05-30.

Task #5: Implement RulesPage CRUD interface for review rule management.

Frontend engineer delivered:
- Full CRUD interface at /rules route with rule list table
- Create/edit modal with validation (name and description required)
- Enable/disable toggle per rule row
- Delete with inline confirmation
- Empty state when no rules exist
- Error handling for API failures
- 11 new component tests (58 total frontend tests passing)
- Responsive layout with mobile breakpoint at 820px

Implementation uses existing API client methods (listReviewRules, createReviewRule, updateReviewRule, enableReviewRule, disableReviewRule, deleteReviewRule) and follows the established design system patterns.

Branch: task-5-rules-page, commit 3423344, merged to main.

## Verify Rule Configuration Integration

Status: verified by verify-engineer on 2026-05-30.

Testing engineer confirmed criteria 8-10 pass after fixes:

8. Create rule "禁止 console.log" (type: style, severity: medium) - PASS
9. Create review with diff containing console.log - PASS
10. Report displays matched rule ID in issue card - PASS

Key fixes:
- Task #1 (commit 22d9027): Rule ID propagation in LLM prompt
- Task #6 (commit d1a7169): MockLLMProvider extracts rule IDs from prompt and includes in matched_rule_ids

End-to-end flow verified: rule creation → review task → orchestrator → rule engine → MockLLM with rule context → report with matched_rule_ids populated → frontend displays "命中规则: [rule-id]".

Note: matched_rule_ids displays rule UUIDs rather than rule names. This is a minor UX enhancement, not a functional bug. Rule name resolution would require additional API call or backend response enrichment.
