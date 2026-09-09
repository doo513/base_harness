# Concurrent Execute Admission Repair (2026-09-08)

## Situation
The preceding full KernelHost test run stalled: a first execute waited on a held handoff, while a second execute queued behind it. The fixture released the first only after the second had been rejected.

## Reason
RUN_ACTIVE was checked inside the serialized operation, too late to reject a duplicate execute before waiting. Session control ordering is still required for domain and skill changes, so removing the queue altogether would introduce another race.

## Action
- Added a per-session reservation for planning.execute before any await or queue insertion.
- Reject duplicates immediately with the existing typed RUN_ACTIVE error.
- Release the reservation in finally after success or failure.
- Retain the existing queue and validation for non-execute controls.
- Kept the original same-tick concurrency test and added explicitly held-execution, other-session and failed-validation retry coverage.
- Ran the full KernelHost suite with a 10-second per-test timeout, then KernelHost and Host typechecks.

## Result
- KernelHost suite: **86 passed, 0 failed**, 463 assertions across 10 files, 4.49 seconds.
- Previously stalled concurrent execute test: passed.
- Ordered domain/skill control regression: passed.
- KernelHost typecheck: exit 0.
- Host typecheck: exit 0.
- Combined command: exit 0.

This supersedes the previous interrupted KernelHost gate for the current revision. It does not erase that failure record or establish application-wide readiness.

## Evidence
Companion JSON records validation scope and results. Test output confirms immediate rejection while the first execution is held, continued independence of another session, and successful execution after a rejected plan-ID request.

## Residual Risk
Admission reservations live in one KernelHost process. Existing durable plan-consumption checks remain responsible for cross-Host replay prevention; they were not redesigned.
These are local regression tests, not independent user validation. Real-provider/TUI stability, startup variance and earlier unrelated pending failures remain open.
No Git operation, real model call or net_monitor.py change occurred.
