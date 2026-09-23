# Base Harness Workbench

A small, standard-library operator console for diagnosing Harness/AGY environment boundaries, previewing a run, starting one explicitly requested run, and observing lifecycle status.

## Quick start

From the Base Harness repository root:

```powershell
python tools\harness-workbench\workbench.py --diagnose --harness-root .
python tools\harness-workbench\workbench.py --status --harness-root . --log-file .agy-run-harness-monitor.log
python tools\harness-workbench\workbench.py --watch --harness-root . --log-file .agy-run-harness-monitor.log
```

To open the Tkinter interface, run `tools/harness-workbench/run-workbench.bat` on Windows or `python tools/harness-workbench/workbench.py --gui --harness-root .`.

## Modes

- `--diagnose`: OS, Python, Bun, AGY, proxy and TLS diagnostics.
- `--preview`: prints the proposed Harness command without starting it.
- `--status`: reads one Host status snapshot or JSONL log.
- `--watch`: refreshes status until Ctrl+C; `--json --watch` emits JSON Lines.
- `--start`: launches one configured Base Harness run. `--follow` keeps the Workbench attached until the child exits.
- `--gui`: diagnostics, run form, preview, live status and event view.

No mode kills a process or retries a failed Run. The tool does not create Evidence or Ready.

See [사용법.md](사용법.md) for Korean instructions and [examples/실사용_예시_2026-09-23.md](examples/실사용_예시_2026-09-23.md) for an observed Windows workflow, including the actual Harness error the monitor surfaced.
