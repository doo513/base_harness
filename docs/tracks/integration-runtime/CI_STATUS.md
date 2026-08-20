# Integration Runtime CI Status

- Source commit: 5398f4b6f17fb028e8eb0f3ac5f2ab5cd87130ba
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
....ssss..s.................................................ss.......... [ 47%]
........................................................................ [ 71%]
........................................................................ [ 95%]
...........F..                                                           [100%]
=================================== FAILURES ===================================
__________ test_visual_tui_synthesizes_acceptance_for_report_request ___________

tmp_path = PosixPath('/tmp/pytest-of-runner/pytest-0/test_visual_tui_synthesizes_ac0')

    def test_visual_tui_synthesizes_acceptance_for_report_request(tmp_path):
        state = AppState(workspace=str(tmp_path), mode="software")
        spec = _task_spec(state, "이 프로젝트를 분석해서 보고서를 작성해줘")
>       assert spec.acceptance_commands
E       AssertionError: assert ()
E        +  where () = RunLaunchSpec(config=None, workspace='/tmp/pytest-of-runner/pytest-0/test_visual_tui_synthesizes_ac0', run_dir='runs/2...oracle=False, sealed_oracle_root=None, require_oracle_isolation=False, require_complete_provenance=False, resume=False).acceptance_commands

tests/test_tui_visual.py:81: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui_visual.py::test_visual_tui_synthesizes_acceptance_for_report_request - AssertionError: assert ()
 +  where () = RunLaunchSpec(config=None, workspace='/tmp/pytest-of-runner/pytest-0/test_visual_tui_synthesizes_ac0', run_dir='runs/2...oracle=False, sealed_oracle_root=None, require_oracle_isolation=False, require_complete_provenance=False, resume=False).acceptance_commands
1 failed, 294 passed, 7 skipped in 25.64s
```
