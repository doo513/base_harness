# Terminal Planning Presentation and Kernel Admission (2026-09-08)

## Situation
The local repair fixture reached phase/outcome ready, while its public planningState remained executing. Root repair counters were zero despite one repaired child.

## Reason
KernelHost merged its internal planning state directly into public status. The Host completion callback also read that public field to allow verification. Merely changing the display would therefore alter completion admission.
Coordinator snapshot code separately confirms that top-level repairCount and metrics.repairs mirror the root verifier count; they are not total child repair usage.

## Action
- Added KernelHost.canVerifyRoot for internal planning admission.
- Bound the Host completion gate to that method rather than the public status field.
- Projected executing to idle only for ready/blocked/failure/interrupted phases, without changing internal execution admission.
- Kept phase/outcome, Ready eligibility, plan-only behavior, worker policies and root repair counters unchanged.
- Added terminal, readStatus, presentation-spoofing and plan-only tests.
- Ran KernelHost tests, KernelHost/Host typechecks and the actual local two-worker repair fixture.

## Result
- Targeted tests: **25 passed, 0 failed**, 193 assertions.
- KernelHost and Host typechecks: **passed**.
- Actual local fixture: **passed**, root Ready retained and planningState idle.
- Failed worker reused its session for one repair; independent worker was not repeated.
- No real model or OAuth account was used.

**The full KernelHost suite did not pass.** It stalled in the existing concurrent-execute test and was explicitly terminated after its process identity was checked. Its gate result is -1, not a pass. Targeted passing tests do not replace this failed full-suite gate.

## Evidence
Run: run-1a6bc4ce-d4bb-421b-b2f1-8772af0c2d90
Session: ses_f8108bbb4ffefUbFICy76a0M8M
Actual client exit: 0. Host intentionally terminated after completion: 143.
Companion JSON retains the passing scoped results and failed full-suite result.

The concurrent test starts an execute operation held by a promise, awaits rejection of a second execute, then releases the first in finally. Existing KernelHost.control queues the second behind the first; its RUN_ACTIVE check is reached only after that queue wait. The two waits form a cycle in this fixture. This control implementation was not changed by the presentation patch.

## Residual Risk
- Concurrent execute admission/serialization remains unresolved and needs a separate change. A likely direction is rejecting duplicate execute requests before queueing while retaining ordered domain/skill controls.
- Root-versus-child repair counters remain separate; consumers must not label root counters as total repairs.
- This integration establishes a scripted local path, not independent user stability or real-model repair competence.
- Startup remains variable: this fixture needed about 14.846 s for health and 2.157 s for the initial provider response. No performance improvement is claimed.
- No native TUI interaction or full cross-platform regression suite passed in this turn.
- No Git operations or net_monitor.py changes were made.
