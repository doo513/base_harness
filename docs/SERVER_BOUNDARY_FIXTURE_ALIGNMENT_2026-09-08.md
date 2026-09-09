# Server Boundary and Fixture Alignment

## Situation

The expanded Host regression run reached 2839 tests across 205 files and stopped after 20 failures, with exit code 1 after 1415.79 seconds. This is a fail-fast baseline, not a full-suite completion or a count of passing tests.

## Reason

Three production boundary inconsistencies were identified:

- The V2 location middleware still read x-opencode-directory and x-opencode-workspace. New Base Harness header inputs were ignored, so directory resolution could fall back to the Host process working directory. This also affected workspace-local references.
- The shared server defaulted authentication to opencode while the Host used base-harness.
- CORS implicitly trusted the upstream opencode.ai domain and its subdomains despite this product being independent.

Separately, several tests retained obsolete credentials or file names, and two session path fixtures created packages/opencode/src while querying packages/base-harness/src. These fixture inconsistencies did not justify weakening production behavior.

## Action

- Updated V2 directory/workspace header keys to the Base Harness contract, retaining query precedence and directory decoding.
- Aligned shared server authentication defaults with Host defaults.
- Removed the inherited OpenCode remote-origin allowlist. Remote web origins now require explicit CORS configuration; no unowned base-harness.ai domain was added as a trusted default. Existing local UI and same-host behavior is preserved.
- Added coverage for Host/shared credential parity, rejection of the old default username, explicit remote-origin configuration, default remote rejection, encoded directory headers, and query precedence.
- Updated project config persistence expectations to base-harness.jsonc.
- Made fixture creation and query paths consistent, preserving directory/path filtering assertions.
- Left the existing reference-location test assertions unchanged.

## Result

- Focused server regression checks: 56 passed, 0 failed, 217 assertions across 9 files, 133.46 seconds.
- Host typecheck: exit code 0.
- Shared server typecheck: exit code 0.
- The nine server-related baseline failures are covered by the successful focused run.
- Eleven baseline failures remain outside this patch: cancellation timing, task metadata, prompt composition/order, snapshot behavior, Windows symlink capability, contract fixtures, task schema snapshot, and removed plan-agent permission fixtures.
- No post-patch full-suite pass is claimed.

## Evidence

- Baseline log: .tools/validation/host-suite-provider-fixed-1788849237669.log.
- Focused log: .tools/validation/server-boundary-followup-1788850881642.log.
- Focused terminal marker: SERVER_BOUNDARY_GATE tests=0 hostTypes=0 serverTypes=0.
- Diagnostic companion: SERVER_BOUNDARY_FIXTURE_DIAGNOSTICS_2026-09-08.json.
- Test files: auth.test.ts, httpapi-config.test.ts, httpapi-cors.test.ts, httpapi-instance-route-auth.test.ts, cors-origin-policy.test.ts, session-list.test.ts, httpapi-session.test.ts, httpapi-v2-location.test.ts, httpapi-reference.test.ts.
- These results are engineering diagnostics, not Harness Evidence, Ready attestations, or independent user validation.

## Residual Risk

- The full Host suite stopped early, so later tests and cross-suite effects remain unproven.
- External web UIs that relied on the inherited OpenCode allowlist must explicitly configure their origin. CORS is not a replacement for authentication or OS isolation.
- V2 clients must send the Base Harness header contract or explicit location query. Legacy OpenCode header aliases were not introduced.
- Native TUI interaction, real-account OAuth, long-duration use, and complete platform sandboxing were not newly tested here.
- Windows symlink failures were observed as EPERM; no privilege escalation, OS policy change, or silent test skip was applied.
- Existing local UI origin handling was not comprehensively redesigned or audited.
- The prior possible user-configuration exposure remains unresolved and is not repaired or disproved by this patch.
- No Git operations were performed. net_monitor.py was untouched.
