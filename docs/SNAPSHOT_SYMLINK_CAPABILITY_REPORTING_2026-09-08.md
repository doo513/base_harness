# Snapshot Symlink Capability Reporting

## Situation
The two remaining earlier Host failures occurred before Snapshot.patch: native Windows file symlink creation failed with EPERM. The process was not elevated, and the queried developer-mode registry value was absent. This is not proof of a snapshot implementation defect.

## Reason
- Tests assumed the environment could create file and directory symbolic links.
- The circular-symlink fixture swallowed creation errors, potentially reporting success without any link.
- Unsupported platform capabilities must not be represented as successful validation.

## Action
- Added a temporary-directory probe for actual file and directory symlink creation.
- Classified only Windows EPERM/EACCES as unavailable; unexpected errors and non-Windows failures still fail.
- Added explicit capability warnings and named unavailable tests.
- Added BASE_HARNESS_REQUIRE_SYMLINK_TESTS=1, which rejects a run when either capability is absent.
- Removed swallowed link-creation errors from the circular fixture and asserted a real symbolic link exists when supported.
- Added deterministic classification and required-gate tests.
- Did not enable developer mode, elevate privileges, substitute hardlinks/junctions for file symlinks, or change snapshot production behavior.

## Result
- Fresh baseline: 0 passed, 2 failed, 54 filtered out, 11.73 seconds; both failures were EPERM at fs.symlink.
- Snapshot plus capability tests: 52 passed, 6 skipped, 0 failed, 731 assertions, 58 cases across 2 files, 204.95 seconds.
- The skipped set includes the three capability-dependent link cases; these are NOT passed checks.
- Host typecheck passed.
- Required native-symlink gate: exit 1 with SYMLINK_CAPABILITY_REQUIRED, 0 passed, 1 failed, 1 module error, 5.34 seconds.
- Actual Windows file/directory symlink behavior remains unverified and cannot be promoted as complete.

## Evidence
- Baseline session 81896 exited 1.
- Read-only host metadata: Elevated=false; AllowDevelopmentWithoutDevLicense=null.
- Capability probe output: Windows file symlink EPERM; Windows directory symlink EPERM.
- Snapshot/typecheck session 19502 ended with SNAPSHOT_CAPABILITY_GATE tests=0 typecheck=0.
- Required command: set BASE_HARNESS_REQUIRE_SYMLINK_TESTS=1, then bundled Bun test --timeout 15000 --only-failures --test-name-pattern 'symlink handling|nested symlinks|circular symlinks' test/snapshot/snapshot.test.ts.
- Required command printed REQUIRED_SYMLINK_GATE exit=1. The environment override was restored afterward.
- Companion: SNAPSHOT_SYMLINK_CAPABILITY_DIAGNOSTICS_2026-09-08.json.

## Residual Risk
- No actual symlink handling success was established on this Windows host.
- Promotion must run the required gate in a capable Windows environment; Linux results do not substitute for Windows requirements.
- Ordinary suite success with explicit skips is useful development feedback, not evidence that the missing platform capability passed.
- Full Host and post-isolation Core regression still remain.
- The earlier circular-link check's false-success risk is addressed, but its actual behavior is not exercised here.
- No repository Git operations or net_monitor.py modifications were made.

