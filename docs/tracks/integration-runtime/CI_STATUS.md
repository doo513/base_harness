# Integration Runtime CI Status

- Source commit: 586e227e4b3b21985fc7ecc68fcd1c5a75dc5abc
- Branch: main
- Result: **FAIL**
- Runner: ubuntu-latest
- Python: 3.11
- Install gate: success

## Gate ledger

```text
compile                                          PASS
cli-module                                       PASS
tui-module                                       PASS
cli-console                                      PASS
tui-console                                      PASS
full-pytest                                      FAIL
core-freeze-audit                                PASS
stage03-resume                                   PASS
stage04-semantic                                 PASS
stage04-realworld                                PASS
stage05-recovery                                 PASS
stage05-adversarial                              PASS
stage05-terminal                                 PASS
stage05-crash-window                             PASS
stage05-strategy                                 PASS
stage05-effectiveness                            PASS
stage06-progress                                 PASS
stage06-adversarial                              PASS
stage06-resume                                   PASS
stage06-boundary                                 PASS
stage06-strategy                                 PASS
stage06-task-world                               PASS
stage07-context                                  PASS
stage07-adversarial                              PASS
stage07-resume                                   PASS
stage07-compat                                   PASS
stage07-trusted-context                          PASS
stage07-context-cost                             PASS
stage07-goal-bounds                              PASS
stage08-retrieval                                PASS
stage08-adversarial                              PASS
stage08-resume                                   PASS
stage08-cost                                     PASS
stage08-artifact-integrity                       PASS
verified-read-cost                               PASS
stage02-nested-submount                          PASS
stage02-mount-cost                               PASS
stage02-backend-binding                          PASS
stage02-binding-cost                             PASS
```

## Full pytest tail

```text
........................................................................ [ 23%]
....ssss..s.....................................................ss...... [ 46%]
........................................................................ [ 69%]
........................................................................ [ 92%]
...............F.........                                                [100%]
=================================== FAILURES ===================================
_______ test_visual_tui_task_spec_auto_detects_acceptance_and_fresh_run ________

tmp_path = PosixPath('/tmp/pytest-of-runner/pytest-0/test_visual_tui_task_spec_auto0')

    def test_visual_tui_task_spec_auto_detects_acceptance_and_fresh_run(tmp_path):
        (tmp_path / "tests").mkdir()
        state = AppState(workspace=str(tmp_path), mode="software")
        spec = _task_spec(state, "fix the project")
        assert spec.goal == "fix the project"
        assert spec.acceptance_commands
        assert spec.acceptance_commands[0].endswith("-m pytest -q")
>       assert spec.run_dir.startswith("runs") or spec.run_dir.startswith("./runs")
E       AssertionError: assert (False or False)
E        +  where False = <built-in method startswith of str object at 0x7fd1c09409d0>('runs')
E        +    where <built-in method startswith of str object at 0x7fd1c09409d0> = '/home/runner/.local/state/base_harness/runs/20260820-144055'.startswith
E        +      where '/home/runner/.local/state/base_harness/runs/20260820-144055' = RunLaunchSpec(config=None, workspace='/tmp/pytest-of-runner/pytest-0/test_visual_tui_task_spec_auto0', run_dir='/home/...oracle=False, sealed_oracle_root=None, require_oracle_isolation=False, require_complete_provenance=False, resume=False).run_dir
E        +  and   False = <built-in method startswith of str object at 0x7fd1c09409d0>('./runs')
E        +    where <built-in method startswith of str object at 0x7fd1c09409d0> = '/home/runner/.local/state/base_harness/runs/20260820-144055'.startswith
E        +      where '/home/runner/.local/state/base_harness/runs/20260820-144055' = RunLaunchSpec(config=None, workspace='/tmp/pytest-of-runner/pytest-0/test_visual_tui_task_spec_auto0', run_dir='/home/...oracle=False, sealed_oracle_root=None, require_oracle_isolation=False, require_complete_provenance=False, resume=False).run_dir

tests/test_tui_visual.py:65: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui_visual.py::test_visual_tui_task_spec_auto_detects_acceptance_and_fresh_run - AssertionError: assert (False or False)
 +  where False = <built-in method startswith of str object at 0x7fd1c09409d0>('runs')
 +    where <built-in method startswith of str object at 0x7fd1c09409d0> = '/home/runner/.local/state/base_harness/runs/20260820-144055'.startswith
 +      where '/home/runner/.local/state/base_harness/runs/20260820-144055' = RunLaunchSpec(config=None, workspace='/tmp/pytest-of-runner/pytest-0/test_visual_tui_task_spec_auto0', run_dir='/home/...oracle=False, sealed_oracle_root=None, require_oracle_isolation=False, require_complete_provenance=False, resume=False).run_dir
 +  and   False = <built-in method startswith of str object at 0x7fd1c09409d0>('./runs')
 +    where <built-in method startswith of str object at 0x7fd1c09409d0> = '/home/runner/.local/state/base_harness/runs/20260820-144055'.startswith
 +      where '/home/runner/.local/state/base_harness/runs/20260820-144055' = RunLaunchSpec(config=None, workspace='/tmp/pytest-of-runner/pytest-0/test_visual_tui_task_spec_auto0', run_dir='/home/...oracle=False, sealed_oracle_root=None, require_oracle_isolation=False, require_complete_provenance=False, resume=False).run_dir
1 failed, 305 passed, 7 skipped in 30.02s
```
