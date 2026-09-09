# Prompt Admission and Snapshot Follow-up

## Situation

Four baseline failures concerned task running metadata, next-prompt composition, asynchronous file-part ordering, and missing output in an instant-tool snapshot fixture.

## Reason

- The shared session tool entrypoint discarded structured subagent_type before Kernel admission. Pre-contract delegation could not distinguish read-only exploration from implementation.
- Prompt tests assumed no Kernel policy content could precede user content or file diagnostics.
- The snapshot fixture attempted a shell mutation without an accepted contract and used a POSIX-style command. A missing output file was not sufficient evidence of a snapshot race.

## Action

- Forwarded the typed task subagent selector to the Kernel before plugin hooks.
- Allowed only explore delegation through the contract-presence check before acceptance; Kernel and Orchestration checks remain in place, and TaskTool still checks its own role and permissions.
- Added a regression case proving explore is allowed while general and unspecified delegation remain denied before contract acceptance.
- Updated prompt assertions to preserve exact user content and adjacent file-expansion ordering without assuming policy context is absent.
- Changed the snapshot fixture to accept the real contract before the first model step and use an instant structured write. It asserts no file exists before the loop, exact resulting bytes, completed write, and a diff naming the intended file. No extra earlier LLM/tool step was added to conceal the race.
- Adjusted the task metadata fixture to request explicit read-only exploration through a normal no-reply prompt.
- Retained all production completion and verification gates.

## Result

Combined run:
- 52 passed, 14 skipped, 2 failed, 1 unhandled error; 236 assertions, 68 tests across 3 files.
- Host typecheck passed with exit code 0.
- Message composition, file ordering, snapshot output/diff, and the new exploration admission check passed.
- Task running metadata still timed out. Busy/idle timing also failed in this run.
- The reported 6615.46-second elapsed duration is anomalous. Its cause was not established, and it is not used for performance conclusions.

Bounded isolated follow-up:
- Only the task metadata and busy/idle tests were selected in a separate process with a 60-second parent deadline.
- 1 passed, 1 failed, 57 filtered out; 17.57 seconds.
- Task metadata timeout reproduced; busy/idle passed.
- The parent watchdog did not fire and the process exited with code 1. Process-tree termination was therefore not exercised.

## Evidence

- Combined log: .tools/validation/prompt-admission-followup-1788852189721.log.
- Combined terminal: PROMPT_ADMISSION_GATE tests=1 typecheck=0, session 97784.
- Isolated stdout: .tools/validation/prompt-timeout-isolation-1788858985673.stdout.log.
- Isolated stderr: .tools/validation/prompt-timeout-isolation-1788858985673.stderr.log.
- Isolated wrapper session 12806 reported stopped=true, timedOut=false, exitCode=1.
- Companion: PROMPT_ADMISSION_SNAPSHOT_DIAGNOSTICS_2026-09-08.json.
- These are engineering diagnostics, not Harness Evidence or independent user validation.

## Residual Risk

- Task metadata remains unresolved. Automatic exploration may interact with the explicit scripted task response; this is a hypothesis, not a confirmed root cause.
- The next diagnostic should distinguish an errored task from absent running metadata and explicitly control automatic exploration for this fixture.
- A single isolated busy/idle pass does not establish timing stability.
- The combined unhandled error remains recorded; no complete focused or full-suite pass is claimed.
- The snapshot fixture uses a local scripted model and accepted contract, not a real-account or independent user evaluation.
- Prior compaction timing, Windows symlink, task schema snapshot, and removed plan-agent fixture failures remain outside this patch.
- No Git operations were performed; net_monitor.py was untouched.
