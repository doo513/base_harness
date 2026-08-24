# Integration Runtime CI Status

- Source commit: 015b801c7becb63bb6969e40bd877c8b699e9d19
- Branch: develop
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
.F...................................................................... [ 18%]
...............ssss..s.................................................. [ 36%]
...........................................................ss........... [ 54%]
........................................................................ [ 73%]
........................................................................ [ 91%]
..................................                                       [100%]
=================================== FAILURES ===================================
_____ test_run_summary_separates_context_protocol_and_failure_observations _____

    def test_run_summary_separates_context_protocol_and_failure_observations():
        records = [
            _event(
                "model.context_compile",
                {
                    "level": 2,
                    "source_estimated_input_tokens": 4000,
                    "compiled_estimated_input_tokens": 2000,
                    "estimated_reduction_ratio": 0.5,
                    "budget": {"max_input_tokens": 3000},
                },
            ),
            _event(
                "model.protocol_decode",
                {
                    "kind": "tool",
                    "lexical_repaired": True,
                    "lexical_repair_kind": "raw_control_character",
                },
            ),
>           _event("failure", kind="actor_workflow_error"),
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        ]
E       TypeError: _event() got multiple values for argument 'kind'

tests/test_context_ablation_report.py:31: TypeError
=========================== short test summary info ============================
FAILED tests/test_context_ablation_report.py::test_run_summary_separates_context_protocol_and_failure_observations - TypeError: _event() got multiple values for argument 'kind'
1 failed, 386 passed, 7 skipped in 30.17s
```
