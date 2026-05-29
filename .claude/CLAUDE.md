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

Team workflow (feature-driven iterative loop, driven by verify-engineer):

1. Verify engineer picks a feature from PRD/tecDoc (P0 first).
2. Verify engineer calls testing engineer to test that specific feature.
3. Testing engineer tests in browser and reports findings to verify engineer.
4. If issues found, verify engineer creates tasks and assigns frontend/backend engineers.
5. Engineer implements in worktree, self-verifies, notifies verify engineer.
6. Verify engineer reviews and calls testing engineer to re-test. If issues remain, repeat from step 4.
7. When feature passes, verify engineer updates docs, commits, and merges.
8. Repeat until all features in PRD/tecDoc are verified.
