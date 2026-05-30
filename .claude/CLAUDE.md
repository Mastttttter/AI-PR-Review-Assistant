# Project Instructions

Project: AI PR Review Assistant MVP v1.0.

Before development work, read:

- `doc/chief/PRD.md`
- `doc/chief/tecDoc.md`
- `doc/chief/constrains.md`

Product boundary:

- Input: PR title, description, and diff.
- Output: structured review report with summary, risk level, issues, and suggestions.
- Never auto-modify code or auto-merge PRs.
- Treat submitted code and reports as sensitive data.

Team rules:

- Chief engineer decomposes work and assigns tasks.
- Frontend tasks live in `doc/frontend/todolist.md`.
- Backend tasks live in `doc/backend/todolist.md`.
- Each task includes acceptance requirements and test expectations.
- Use one git worktree and branch per implementation task.
- Implementation engineers work only inside the assigned task worktree.
- Task owner marks completed items and signs with role name.
- After each finished task, implementation engineer notifies chief engineer for review, documentation, and commit.
- Chief engineer updates milestone docs under `doc/main/` and creates one commit containing only that finished task.
- **Main agent (you) must NEVER use browser MCP tools or any tool that may receive image data.** All browser-based UI testing is delegated exclusively to the testing engineer.
- **Only frontend and backend engineers may modify project files.** All source code, documentation, config, and test changes are made exclusively by frontend/backend engineers in their assigned worktrees. Chief engineer, verify engineer, testing engineer, and main agent must NEVER edit project files directly — they coordinate changes through the f/b engineers.

PR discipline:

- One PR = one feature or fix. Keep PRs as small and granular as possible.
- Large features must be split into multiple independent PRs.
- PR title: one sentence summarizing what was added/changed.
- PR description must include: feature description, implementation approach, and test method.
- Main branch must remain runnable at all times — any reviewer can pull and demo at any point.

Iteration workflow (requirement-driven, coordinated by chief engineer):

1. User gives a new requirement to the chief engineer.
2. Chief engineer breaks down the requirement (if needed), creates task list, and updates `doc/chief/PRD.md` and `doc/chief/tecDoc.md`.
3. Chief engineer assigns tasks to frontend/backend engineers.
4. Engineer implements in worktree, self-verifies, and notifies chief engineer on completion.
5. Chief engineer reviews and calls testing engineer to test the feature.
6. If issues found, chief engineer sends them back to the engineer. Repeat from step 4.
7. When feature passes, engineer updates `doc/main/` milestone docs, `doc/frontend/todolist.md` / `doc/backend/todolist.md`, and chief engineer integrates (commit, merge). Cycle repeats.
