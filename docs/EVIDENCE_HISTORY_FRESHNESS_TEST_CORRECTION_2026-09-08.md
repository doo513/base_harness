# Evidence History Freshness Test Correction (2026-09-08)

## Situation
The disputed-history regression previously expected an execution-verifier observation to be reusable without configuring freshnessSeconds. The earlier selected Python gate recorded 64 passes and one failure.

## Reason
A successful current verification is not unconditional permission to reuse that observation in another context. Existing policy requires a known workspace revision and an explicit freshness window for historical execution evidence. The fixture already supplies a known revision but omitted freshness.

## Action
- Parameterized the existing disputed-history test with an absent freshness window and a positive 3600-second window.
- Asserted that the initial stored case is active.
- Required an empty historical-method set when freshness is absent.
- Required the pass method when active evidence has the explicit fresh window.
- Preserved the assertion that adding a soft counterexample makes the case disputed and excludes historical methods in both cases.
- Did not change verifier production code, independence requirements, current verification rules or storage formats.

## Result
- Both Python files passed: 66 tests, zero failures, 10.89 seconds.
- The earlier failed positive precondition is corrected without accepting freshness-free historical reuse.
- Current verification still succeeds in both cases; historical reuse is evaluated separately.

## Evidence
Command from the repository root, with PYTHONPATH=src:
.tools/verifier/Scripts/python.exe -m pytest tests/test_verified_sidecar.py tests/test_restored_verification_boundary.py -q

Exit code: 0.
The companion JSON records the cases and selected gate scope.
Earlier reports retain the historical failed run; this report resolves only its disputed-history freshness fixture issue.

## Residual Risk
- The test uses a deterministic synthetic execution verifier. It does not establish live-model quality or full application stability.
- These are two Python test files, not the entire repository suite.
- The 3600-second window is a test input, not a new application default.
- Other recorded platform, startup and unrelated test risks remain open.
- Git and net_monitor.py were untouched; no commit, push or release promotion occurred.
