# Full Host Regression with Resource Diagnostics

## Situation
The prior complete Host run failed ACP initialize and shell-to-loop resume. The next complete run enabled existing bounded fixture/body traces and ACP memory snapshots without raising deadlines or changing assertions.

## Reason
Shorter ACP, discovery-only and LLM-before-ACP runs had passed. Resource observations were needed from the actual failing full-run context instead of assuming that import structure or memory pressure explained it.

## Action
Ran the complete suite once and waited on the same process until exit. Queried recent Windows power/time event identifiers after an unusually long initial gap; the scoped query returned no matching records, which does not establish the gap's cause.
After the complete test process ended, ran an isolated real CLI ACP initialize probe with memory snapshots, no prompt and zero model calls.

## Result
Full Host: exit 1; 3278 passed, 60 skipped, 1 todo, 1 failed; 3340 tests across 253 files; 45 snapshots; 8867 assertions.
Only failure: ACP config-option case, actually request:initialize, elapsed 15046 ms, no protocol output observed. The last captured child marker was runtime.import_start at process uptime 1130 ms.
The shell-resume test reached its final assertion marker at body +6545 ms and did not fail in this run.

At ACP launch, test-parent RSS was 1259827200 bytes and system free memory was 1540816896 bytes. At timeout, these were 1259941888 and 1017307136 bytes. Total physical memory was 16440479744 bytes.
The independent post-run probe initialized successfully, issued zero model calls and stopped its child. Its system free memory at successful observation was 775217152 bytes, lower than the failed full-run observation. Its parent RSS was 62021632 bytes. Child runtime import completed at process uptime 3690 ms.

## Evidence
All observations are developer diagnostics, not Harness Evidence or independent practical acceptance.
Reported full-suite duration was 6077.29 seconds. The first runner marker was already at process uptime 4268747 ms; this unexplained initial gap makes the total unsuitable as a startup performance benchmark.
The successful probe with less free system memory contradicts treating a simple free-memory threshold as a sufficient explanation. The probe differs from the full test context, so it does not establish a unique alternative cause.
Machine-readable results: HOST_RESOURCE_REGRESSION_DIAGNOSTICS_2026-09-09.json.

## Residual Risk
ACP initialize remains unresolved. Shell-resume passed once in a full run but its previous intermittent timeout is not declared fixed.
Cumulative process state, parent event-loop scheduling, inherited configuration and transport observation remain hypotheses, not findings.
No complete suite was restarted after this run. Future investigation should compare the exact test launch and protocol observation paths before another long rerun.
Windows native capability skips, real OAuth/provider usage and independent user stability remain unverified.
No production code, user settings, credentials, net_monitor.py, repository commit or push changed during this validation turn.

