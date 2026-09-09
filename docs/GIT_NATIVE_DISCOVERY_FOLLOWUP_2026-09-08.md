# Git native discovery follow-up (2026-09-08)

## Situation

The prior Core follow-up left three failures where scratch directories inherited the user's ancestor checkout. A catalog identity assertion also had a TypeScript type mismatch.

## Reason

Git.repo.discover previously searched upward for .git with FSUtil.up, changed cwd to the located ancestor, and only then invoked Git. Setting GIT_CEILING_DIRECTORIES did not constrain that earlier filesystem walk.

## Action

- Changed runtime/packages/core/src/git.ts to start native Git discovery in the caller's requested directory rather than preselecting an ancestor.
- Return unavailable when Git cannot resolve a working-tree root, including a bare repository.
- Retain the existing git-directory and common-directory parsing.
- Changed the catalog identity assertion in runtime/packages/core/test/models.test.ts to Object.is followed by a boolean assertion; this does not assert catalog schema validity.
- Attempted to add six fixture cases in runtime/packages/core/test/git.test.ts for nested directories, ceilings, nearest repositories, linked worktrees, and bare repositories.

The test insertion has an unresolved authoring error: JavaScript String.replace interpreted a dollar-backtick sequence in the inserted Bun shell source as a replacement token and inserted the original source prefix. The generated test file therefore cannot be parsed.

## Result

The targeted command reported:

- 87 passing tests.
- 1 failed test-file load and 1 unhandled error.
- 176 assertions across the loaded tests.
- Core typecheck exit 2, with syntax errors in test/git.test.ts.
- Runtime: 52.50 seconds.

All three previously failing Project, ProjectCopy, and Snapshot scenarios passed. Candidate, catalog, Cloudflare, process, and existing linked-worktree scenarios in the other selected files also passed.

The six new Git discovery cases and the pre-existing cases in git.test.ts did not execute because that file failed to load. This is not a passing gate. A full Core rerun was not performed.

## Evidence

- Pinned repository-local Bun 1.3.14, Windows.
- BASE_HARNESS_DISABLE_MODELS_FETCH=true and BASE_HARNESS_PURE=1.
- Terminal result: GIT_DISCOVERY_TARGETED_GATE tests=1 typecheck=2.
- Source of first parse error: runtime/packages/core/test/git.test.ts:145.
- Companion diagnostic JSON: GIT_NATIVE_DISCOVERY_FOLLOWUP_2026-09-08.json.

These are developer-run diagnostics, not independent user validation or Harness Evidence/Ready.

## Residual Risk

- The newly introduced test syntax error remains and was disclosed; it must be repaired before promotion.
- Use a replacement callback when reconstructing the test insertion from the cached pre-edit source so shell source is inserted literally.
- Native discovery requires a usable directory and working-tree root. Bare repositories are intentionally unavailable; prospective or file-path callers need separate compatibility assessment.
- Git discovery ceilings are discovery configuration, not a sandbox or authorization boundary. Linked-worktree common storage can legitimately be outside the ceiling.
- No claim is made about all operating systems, real OAuth accounts, or long-running workload stability.
- No repository commit or push was performed. net_monitor.py and the user's home .git were not modified by the repair.

