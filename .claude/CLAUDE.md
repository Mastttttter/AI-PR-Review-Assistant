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
