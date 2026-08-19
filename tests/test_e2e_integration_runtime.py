import json
import shlex
import sys

import pytest

from harness.core.budget import Budget
from harness.core.controller import LLMController
from harness.core.runtime import HarnessRuntime
from harness.model_gateway import ModelGateway
from harness.profiles.hackathon import HackathonProfile
from harness.profiles.software import SoftwareProfile


def _actor_command(target_name: str) -> str:
    program = f"""
import json, sys
wire = json.load(sys.stdin)
user = json.loads(wire['user'])
step = int(user['context']['control']['step'])
if step == 0:
    out = {{'kind':'plan','payload':{{'objective':'deliver verified target','tasks':[{{'id':'implement','title':'create target artifact','depends_on':[]}}]}}}}
elif step == 1:
    out = {{'kind':'task','payload':{{'id':'implement','status':'active'}}}}
elif step == 2:
    out = {{'kind':'tool','payload':{{'tool':'shell','args':{{'command':'printf fixed > {target_name}'}}}}}}
else:
    out = {{'kind':'complete','payload':{{'reason':'target created; request harness-side acceptance'}}}}
print(json.dumps(out))
"""
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(program)}"


def _acceptance_command(target_name: str) -> str:
    program = f"from pathlib import Path; assert Path({target_name!r}).read_text() == 'fixed'"
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(program)}"


@pytest.mark.parametrize("profile_name", ["software", "hackathon"])
def test_full_local_model_to_oracle_execution_path(tmp_path, profile_name):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target_name = f"{profile_name}-result.txt"
    acceptance = [_acceptance_command(target_name)]
    if profile_name == "software":
        profile = SoftwareProfile(workspace=workspace, acceptance_commands=acceptance)
    else:
        profile = HackathonProfile(workspace=workspace, acceptance_commands=acceptance)

    gateway = ModelGateway.single_command(_actor_command(target_name))
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=LLMController(gateway),
        run_dir=tmp_path / "run",
        workspace=workspace,
        budget=Budget(hard_max_steps=8),
        task_revision=f"e2e-{profile_name}-v1",
        model_revision=gateway.revision,
    )
    state = runtime.run()

    assert state.completed is True
    assert (workspace / target_name).read_text() == "fixed"
    assert state.agent_control.objective == "deliver verified target"
    assert runtime.metrics["tool_calls"] == 1
    assert runtime.metrics["completion_requests"] == 1
    assert runtime.metrics["oracle_checks"] == 1
    assert len(state.observations) == 1
    assert state.observations[0].source == "shell"
    assert state.observations[0].artifact_ref in state.evidence_refs
