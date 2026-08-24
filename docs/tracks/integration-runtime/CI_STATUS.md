# Integration Runtime CI Status

- Source commit: aa82ec2d6d918b40c7aa0267797ffbc51276f3b3
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

==================================== ERRORS ====================================
__________ ERROR collecting tests/test_local_model_protocol_compat.py __________
ImportError while importing test module '/home/runner/work/base_harness/base_harness/tests/test_local_model_protocol_compat.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_local_model_protocol_compat.py:8: in <module>
    from harness.core.controller import LLMController, _extract_json_object
E   ImportError: cannot import name '_extract_json_object' from 'harness.core.controller' (/home/runner/work/base_harness/base_harness/src/harness/core/controller.py)
=========================== short test summary info ============================
ERROR tests/test_local_model_protocol_compat.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.57s
```
