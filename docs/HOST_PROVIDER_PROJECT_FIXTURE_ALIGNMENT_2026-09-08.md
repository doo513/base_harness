# Host Provider and Project Fixture Contract Alignment

## Situation

The expanded Host suite terminated with exit 1 after 1,401 tests across 117 files in 499.24 seconds, stopping at 20 failures. One xAI fixture assertion also produced an unhandled local-server error response.

Analysis separated outdated test contracts from unresolved provider behavior. Project identity assertions ran before the failing checks; those failures expected an obsolete opencode cache filename or branch prefix. They did not themselves establish incorrect project IDs.

## Reason

Do not reintroduce model-name heuristics or weaken runtime invariants to satisfy obsolete fixtures. Codex model tests should use a deterministic service catalog instead of whatever Codex executable and account catalog happen to be installed on the developer machine.

The concurrent plugin installation test created base-harness.jsonc and later asserted that the same file did not exist. Its expectation contradicted its own setup.

## Action

- Added an optional internal discoverCatalog dependency to CodexAuthPlugin; production still defaults to app-server discovery.
- Replaced the environment-dependent model-name/context-limit test with explicit catalog fixtures.
- Asserted exact high, max and VendorExact effort identifiers, deduplication, variant merging, provider metadata immutability and per-plugin discovery reuse.
- Added an API-key bypass test proving it never invokes Codex catalog discovery.
- Kept existing legacy fallback behavior explicit, without inventing new model limits.
- Updated cache paths, worktree branch names, provider User-Agent and xAI referrer expectations to the existing Base Harness product contract.
- Updated the worktree collision setup too, so it tests collision with the actual generated branch prefix.
- Fixed concurrent install coverage to assert seed/update preservation in canonical JSONC and absence of an unnecessary JSON sibling.
- No verifier, evidence policy, Ready authority or production repository identity algorithm changed.
- No repository commit/push was performed; net_monitor.py was not modified.

## Result

The six-file target run passed 109 tests, skipped two and failed none, with 314 assertions in 124.77 seconds. Host typecheck exited 0.

All 15 baseline failures belonging to these six files are resolved in the target run. The other five known failures remain open. This is not a full Host suite pass.

The two skipped cases are not validated by this run. This invocation used only-failures output and does not enumerate their names.

## Evidence

- Expanded baseline: .tools/validation/host-suite-expanded-1788847294624.log
- Targeted result: .tools/validation/host-provider-project-fixtures-1788848099600.log
- Companion summary: docs/HOST_PROVIDER_PROJECT_FIXTURE_DIAGNOSTICS_2026-09-08.json
- Runtime seam: runtime/packages/base-harness/src/plugin/openai/codex.ts
- Tests: test/plugin/codex.test.ts, install-concurrency.test.ts, snowflake-cortex.test.ts, xai.test.ts, test/project/project.test.ts and worktree.test.ts under the Host package.

These are developer diagnostics, not Harness Evidence or independent user validation. Tests use synthetic credentials/local endpoints and catalog fixtures; they do not establish real-account compatibility.

## Residual Risk

The remaining known failures are DigitalOcean token autoload, provider-package variant regeneration, custom model API URL inheritance, variant config merge and Azure chat-completions option filtering. Their root causes are not yet established.

Codex's existing legacy allowlist and fallback remain unchanged. The new fixture does not certify their freshness, cross-account applicability or all configured model aliases/modes. No current service context limits are claimed from mock numbers.

The full Host suite stopped before its remainder ran. The earlier possible user-configuration loss remains unresolved; no guessed recovery or credential-file modification was performed.
