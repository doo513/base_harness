import os

import pytest

from harness.core.controller import ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.tools import ActionRuntime, SideEffect, ToolCall, ToolSpec, make_shell_tool
from harness.core.workspace import WorkspaceContract
from harness.core.workspace_tools import make_workspace_read_tools
from harness.profiles.software import SoftwareProfile


def test_declared_input_schema_rejects_call_before_handler_runs():
    called = []
    spec = ToolSpec(
        name="structured",
        description="structured test tool",
        handler=lambda value: called.append(value) or {"ok": True},
        side_effect=SideEffect.NONE,
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
    )
    runtime = ActionRuntime({"structured": spec})
    result = runtime.execute(ToolCall("structured", {"wrong": "x"}))
    assert result.ok is False
    assert "input schema validation failed" in result.error
    assert called == []


def test_declared_output_schema_rejects_mismatched_result():
    spec = ToolSpec(
        name="structured",
        description="structured test tool",
        handler=lambda: "wrong",
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={"type": "object"},
    )
    result = ActionRuntime({"structured": spec}).execute(ToolCall("structured", {}))
    assert result.ok is False
    assert "output schema validation failed" in result.error


def test_shell_tool_declares_model_visible_argument_contract(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    spec = make_shell_tool(workspace)
    assert spec.input_schema["required"] == ["command"]
    result = ActionRuntime({"shell": spec}).execute(ToolCall("shell", {"command": "true", "extra": 1}))
    assert result.ok is False
    assert "unsupported properties" in result.error


def test_workspace_read_tools_are_bounded_to_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    contract = WorkspaceContract.build(workspace)
    tools = make_workspace_read_tools(contract)
    runtime = ActionRuntime(tools)

    read = runtime.execute(ToolCall("file.read", {"path": "a.txt"}))
    assert read.ok is True
    assert read.output["text"] == "alpha\nbeta\n"

    search = runtime.execute(ToolCall("file.search", {"query": "beta"}))
    assert search.ok is True
    assert search.output["matches"][0]["path"] == "a.txt"

    escaped = runtime.execute(ToolCall("file.read", {"path": "../outside.txt"}))
    assert escaped.ok is False

    if hasattr(os, "symlink"):
        link = workspace / "escape-link"
        try:
            link.symlink_to(outside)
        except OSError:
            return
        symlink_escape = runtime.execute(ToolCall("file.read", {"path": "escape-link"}))
        assert symlink_escape.ok is False


def test_runtime_model_context_exposes_schema_for_sandbox_tool(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace=workspace,
    )
    shell = runtime._context()["tools"]["shell"]
    assert shell["input_schema"]["required"] == ["command"]
    assert shell["output_schema"]["type"] == "object"
