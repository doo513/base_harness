import json
import os
import shlex
import sys

from harness.config import ModelConfig
from harness.model_gateway import CommandProvider, ModelRequest


def _python_command(program: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(program)}"


def test_command_provider_runs_outside_parent_working_directory():
    program = (
        "import json,os; "
        "print(json.dumps({'kind':'complete','payload':{'reason':os.getcwd()}}))"
    )
    provider = CommandProvider(
        ModelConfig(provider="command", command=_python_command(program))
    )
    response = provider.complete(ModelRequest(system="s", user="u"))
    decision = json.loads(response.content)
    assert decision["payload"]["reason"] != os.getcwd()
    assert response.raw_metadata["cwd_policy"] == "temporary_directory"
    assert response.raw_metadata["host_isolation"] == "process_boundary_not_sandbox"


def test_command_provider_does_not_inherit_pythonpath_by_default(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/sensitive/path")
    provider = CommandProvider(
        ModelConfig(provider="command", command=_python_command('print("{}")'))
    )
    env = provider._environment()
    assert env is not None
    assert "PYTHONPATH" not in env
