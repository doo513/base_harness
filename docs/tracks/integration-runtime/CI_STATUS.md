# Integration Runtime CI Status

- Source commit: 76ebcf6a6862f60a260bf653c621be07d06b22c2
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
........................................................................ [ 93%]
.........F...........                                                    [100%]
=================================== FAILURES ===================================
_______________ test_change_command_autocomplete_exposes_aliases _______________

tmp_path = PosixPath('/tmp/pytest-of-runner/pytest-0/test_change_command_autocomple0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7f4c02aaee90>

    def test_change_command_autocomplete_exposes_aliases(tmp_path, monkeypatch):
        config = tmp_path / "harness.toml"
        configure_provider(config, alias="alpha", preset="ollama", model="model-a")
        configure_provider(config, alias="beta", preset="ollama", model="model-b", make_default=False)
        monkeypatch.setattr(legacy, "_discover_local_ollama_models", lambda endpoint="http://127.0.0.1:11434": [])
    
        state = legacy.AppState(workspace=str(tmp_path), config=str(config))
        completer = _ConversationCompleter(state)
    
        command_items = list(completer.get_completions(
            Document(text="/cha", cursor_position=4),
            CompleteEvent(completion_requested=True),
        ))
>       assert any(item.text == "/change" for item in command_items)
E       assert False
E        +  where False = any(<generator object test_change_command_autocomplete_exposes_aliases.<locals>.<genexpr> at 0x7f4c0430c790>)

tests/test_tui_model_change.py:43: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui_model_change.py::test_change_command_autocomplete_exposes_aliases - assert False
 +  where False = any(<generator object test_change_command_autocomplete_exposes_aliases.<locals>.<genexpr> at 0x7f4c0430c790>)
1 failed, 301 passed, 7 skipped in 29.38s
```
