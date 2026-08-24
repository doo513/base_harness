# Integration Runtime CI Status

- Source commit: a257d5ba9b825e62ab9874352da155bb8d3859be
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
................................................F....................... [ 18%]
...................ssss..s.............................................. [ 36%]
................................................................ss...... [ 54%]
........................................................................ [ 72%]
........................................................................ [ 90%]
.......................................                                  [100%]
=================================== FAILURES ===================================
______ test_plugin_manifest_identity_and_profile_composition_fail_closed _______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7fe3bef829d0>
tmp_path = PosixPath('/tmp/pytest-of-runner/pytest-0/test_plugin_manifest_identity_0')

    def test_plugin_manifest_identity_and_profile_composition_fail_closed(monkeypatch, tmp_path):
        module = types.ModuleType("bad_harness_plugin")
        module.harness_plugin = lambda *, options: {"name": "other", "version": "1"}
        monkeypatch.setitem(sys.modules, "bad_harness_plugin", module)
        with pytest.raises(PluginError):
            PluginGateway((PluginConfig(name="expected", module="bad_harness_plugin"),)).discover_tools()
    
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
        original_type = type(profile)
        extra = ToolSpec(
            name="extra",
            description="extra",
            handler=lambda: {},
            side_effect=SideEffect.READ,
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"type": "object"},
        )
        augment_profile_tools(profile, {"extra": extra})
        assert type(profile) is original_type
>       assert "input_schema_hash" in profile.tools()["extra"].provenance
                                      ^^^^^^^^^^^^^^^^^^^^^^^^
E       KeyError: 'extra'

tests/test_integration_mcp_plugin.py:188: KeyError
=========================== short test summary info ============================
FAILED tests/test_integration_mcp_plugin.py::test_plugin_manifest_identity_and_profile_composition_fail_closed - KeyError: 'extra'
1 failed, 391 passed, 7 skipped in 29.12s
```
