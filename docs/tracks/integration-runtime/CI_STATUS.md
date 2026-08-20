# Integration Runtime CI Status

- Source commit: fa4c859a4f4738205d387675c0820a7e47908d7a
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
INTERNALERROR>     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
INTERNALERROR>            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 167, in _multicall
INTERNALERROR>     raise exception
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
INTERNALERROR>     teardown.throw(exception)
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/logging.py", line 816, in pytest_runtestloop
INTERNALERROR>     return (yield)  # Run all the tests.
INTERNALERROR>             ^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
INTERNALERROR>     teardown.throw(exception)
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/terminal.py", line 708, in pytest_runtestloop
INTERNALERROR>     result = yield
INTERNALERROR>              ^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 121, in _multicall
INTERNALERROR>     res = hook_impl.function(*args)
INTERNALERROR>           ^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/main.py", line 408, in pytest_runtestloop
INTERNALERROR>     item.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_hooks.py", line 512, in __call__
INTERNALERROR>     return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
INTERNALERROR>            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_manager.py", line 120, in _hookexec
INTERNALERROR>     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
INTERNALERROR>            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 167, in _multicall
INTERNALERROR>     raise exception
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
INTERNALERROR>     teardown.throw(exception)
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/warnings.py", line 90, in pytest_runtest_protocol
INTERNALERROR>     return (yield)
INTERNALERROR>             ^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
INTERNALERROR>     teardown.throw(exception)
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/assertion/__init__.py", line 205, in pytest_runtest_protocol
INTERNALERROR>     return (yield)
INTERNALERROR>             ^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
INTERNALERROR>     teardown.throw(exception)
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/unittest.py", line 612, in pytest_runtest_protocol
INTERNALERROR>     return (yield)
INTERNALERROR>             ^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
INTERNALERROR>     teardown.throw(exception)
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/faulthandler.py", line 102, in pytest_runtest_protocol
INTERNALERROR>     return (yield)
INTERNALERROR>             ^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 121, in _multicall
INTERNALERROR>     res = hook_impl.function(*args)
INTERNALERROR>           ^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/runner.py", line 118, in pytest_runtest_protocol
INTERNALERROR>     runtestprotocol(item, nextitem=nextitem)
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/runner.py", line 139, in runtestprotocol
INTERNALERROR>     reports.append(call_and_report(item, "call", log))
INTERNALERROR>                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/runner.py", line 254, in call_and_report
INTERNALERROR>     report: TestReport = ihook.pytest_runtest_makereport(item=item, call=call)
INTERNALERROR>                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_hooks.py", line 512, in __call__
INTERNALERROR>     return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
INTERNALERROR>            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_manager.py", line 120, in _hookexec
INTERNALERROR>     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
INTERNALERROR>            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 167, in _multicall
INTERNALERROR>     raise exception
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
INTERNALERROR>     teardown.throw(exception)
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/tmpdir.py", line 347, in pytest_runtest_makereport
INTERNALERROR>     rep = yield
INTERNALERROR>           ^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
INTERNALERROR>     teardown.throw(exception)
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/skipping.py", line 280, in pytest_runtest_makereport
INTERNALERROR>     rep = yield
INTERNALERROR>           ^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 121, in _multicall
INTERNALERROR>     res = hook_impl.function(*args)
INTERNALERROR>           ^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/runner.py", line 385, in pytest_runtest_makereport
INTERNALERROR>     return TestReport.from_item_and_call(item, call)
INTERNALERROR>            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/reports.py", line 438, in from_item_and_call
INTERNALERROR>     longrepr = _format_failed_longrepr(item, call, excinfo)
INTERNALERROR>                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/reports.py", line 263, in _format_failed_longrepr
INTERNALERROR>     longrepr = item.repr_failure(excinfo)
INTERNALERROR>                ^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/python.py", line 1749, in repr_failure
INTERNALERROR>     return self._repr_failure_py(excinfo, style=style)
INTERNALERROR>            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/nodes.py", line 444, in _repr_failure_py
INTERNALERROR>     abspath = Path(os.getcwd()) != self.config.invocation_params.dir
INTERNALERROR>               ^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/pathlib.py", line 873, in __new__
INTERNALERROR>     raise NotImplementedError("cannot instantiate %r on your system"
INTERNALERROR> NotImplementedError: cannot instantiate 'WindowsPath' on your system
Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.11.16/x64/bin/pytest", line 6, in <module>
    sys.exit(_console_main())
             ^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/config/__init__.py", line 253, in _console_main
    code = _main(prog=_get_prog_name(sys.argv))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/config/__init__.py", line 229, in _main
    ret: ExitCode | int = config.hook.pytest_cmdline_main(config=config)
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 167, in _multicall
    raise exception
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
          ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/main.py", line 377, in pytest_cmdline_main
    return wrap_session(config, _main)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/main.py", line 365, in wrap_session
    config.hook.pytest_sessionfinish(
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 167, in _multicall
    raise exception
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
    teardown.throw(exception)
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/logging.py", line 888, in pytest_sessionfinish
    return (yield)
            ^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
    teardown.throw(exception)
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/terminal.py", line 961, in pytest_sessionfinish
    result = yield
             ^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 139, in _multicall
    teardown.throw(exception)
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/warnings.py", line 119, in pytest_sessionfinish
    return (yield)
            ^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
          ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/cacheprovider.py", line 469, in pytest_sessionfinish
    config.cache.set("cache/nodeids", sorted(self.cached_nodeids))
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/cacheprovider.py", line 216, in set
    path = self._getvaluepath(key)
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/site-packages/_pytest/cacheprovider.py", line 185, in _getvaluepath
    return self._cachedir.joinpath(self._CACHE_PREFIX_VALUES, Path(key))
                                                              ^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/pathlib.py", line 873, in __new__
    raise NotImplementedError("cannot instantiate %r on your system"
NotImplementedError: cannot instantiate 'WindowsPath' on your system
```
