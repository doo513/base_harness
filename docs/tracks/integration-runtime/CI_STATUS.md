# Integration Runtime CI Status

- Source commit: 5d2f10002a5cd3fe4d6dc9fe12aebcdbc719d141
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
........................................................................ [ 18%]
...............ssss..s...............F.................................. [ 36%]
.............................................................ss......... [ 54%]
........................................................................ [ 72%]
........................................................................ [ 90%]
....................................                                     [100%]
=================================== FAILURES ===================================
_______________ test_provider_retry_requires_explicit_retry_safe _______________

    def test_provider_retry_requires_explicit_retry_safe():
        router = FailureRouter()
        unsafe = Failure(FailureKind.MODEL_PROVIDER_ERROR, "provider unavailable")
        safe = Failure(
            FailureKind.MODEL_PROVIDER_ERROR,
            "provider timed out",
            retry_safe=True,
        )
        assert router.route(unsafe) is RecoveryAction.OBSERVE
>       assert router.route(safe) is RecoveryAction.RETRY
E       AssertionError: assert <RecoveryAction.OBSERVE: 'observe'> is <RecoveryAction.RETRY: 'retry'>
E        +  where <RecoveryAction.OBSERVE: 'observe'> = route(Failure(kind=<FailureKind.MODEL_PROVIDER_ERROR: 'model_provider_error'>, message='provider timed out', action=None, retry_safe=True, signature_key=None, context=None))
E        +    where route = <harness.core.failures.FailureRouter object at 0x7f8cff752c90>.route
E        +  and   <RecoveryAction.RETRY: 'retry'> = RecoveryAction.RETRY

tests/test_model_boundary_failure_taxonomy.py:84: AssertionError
=========================== short test summary info ============================
FAILED tests/test_model_boundary_failure_taxonomy.py::test_provider_retry_requires_explicit_retry_safe - AssertionError: assert <RecoveryAction.OBSERVE: 'observe'> is <RecoveryAction.RETRY: 'retry'>
 +  where <RecoveryAction.OBSERVE: 'observe'> = route(Failure(kind=<FailureKind.MODEL_PROVIDER_ERROR: 'model_provider_error'>, message='provider timed out', action=None, retry_safe=True, signature_key=None, context=None))
 +    where route = <harness.core.failures.FailureRouter object at 0x7f8cff752c90>.route
 +  and   <RecoveryAction.RETRY: 'retry'> = RecoveryAction.RETRY
1 failed, 388 passed, 7 skipped in 29.37s
```
