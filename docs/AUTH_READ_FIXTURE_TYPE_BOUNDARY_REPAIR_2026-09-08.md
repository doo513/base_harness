# Auth Read-Fixture Type Boundary Repair (2026-09-08)

## Situation
The preceding missing-auth-store optimization passed runtime diagnostics, but its new filesystem mock failed Host typechecking with TS2352. It directly asserted two methods as the entire FSUtil.Interface.

## Reason
A partial object is not a full filesystem service. Silencing the mismatch with an unknown cast or weakening tests would hide the test boundary defect rather than correct it.

## Action
- Typed the two mocked read methods with satisfies Pick<FSUtil.Interface, "existsSafe" | "readJson">.
- Composed those overrides over the real complete filesystem service through a closed Effect layer.
- Overrode writeJson to reject unexpected writes in the read-only fixture.
- Kept all six new test cases, existing assertions, production authentication code and verification policy unchanged.

## Result
- Auth read fixtures, existing Auth tests and public provider metadata tests: 16 passed, 0 failed, 59 assertions.
- Host typecheck: exit 0.
- Combined command: exit 0.
- The introduced TS2352 is resolved.

## Evidence
Bun 1.3.14 executed the following from runtime/packages/base-harness:
- bun test --timeout 10000 ./test/auth/store-loading.test.ts ./test/auth/auth.test.ts ./test/provider/public-info-projection.test.ts
- bun run typecheck

The companion JSON records the gate outcomes. Earlier reports correctly retain the historical failed typecheck; this report supersedes their unresolved-TS2352 status only.
Production runtime code did not change in this repair. The previously recorded Host and native TUI diagnostics are not represented as new runs.

## Residual Risk
- This targeted gate does not prove full-product completion, live OAuth compatibility or general user stability.
- Other previously recorded suite failures, startup variability and platform gaps remain outside this repair.
- No Git command, commit, push or change to net_monitor.py was made.
