# Integration Runtime CI Status

- Source commit: 616d15c491c16ddaab70eb213090866894cff3e4
- Branch: develop
- Result: **FAIL**
- Runner: ubuntu-latest
- Python: 3.11
- Install gate: success

## Gate ledger

```text
compile                                          FAIL
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
___________ ERROR collecting tests/test_integration_model_gateway.py ___________
/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/python.py:508: in importtestmodule
    mod = import_path(
/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/pathlib.py:596: in import_path
    importlib.import_module(module_name)
/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1204: in _gcd_import
    ???
<frozen importlib._bootstrap>:1176: in _find_and_load
    ???
<frozen importlib._bootstrap>:1147: in _find_and_load_unlocked
    ???
<frozen importlib._bootstrap>:690: in _load_unlocked
    ???
/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/assertion/rewrite.py:179: in exec_module
    source_stat, co = _rewrite_test(fn, self.config)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/assertion/rewrite.py:348: in _rewrite_test
    tree = ast.parse(source, filename=strfn)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/ast.py:50: in parse
    return compile(source, filename, mode, flags,
E     File "/home/runner/work/base_harness/base_harness/tests/test_integration_model_gateway.py", line 197
E       command=f"{shlex.quote(sys.executable)} -c {shlex.quote('print(\"{}\")')}",
E                                                                                 ^
E   SyntaxError: f-string expression part cannot include a backslash
=========================== short test summary info ============================
ERROR tests/test_integration_model_gateway.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 1.09s
```
