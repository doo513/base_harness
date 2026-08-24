from harness.config import ModelConfig
from harness.core.controller import LLMController
from harness.core.runtime import HarnessRuntime
from harness.model_gateway import ModelGateway
from harness.profiles.demo import DemoProfile


def test_manifest_binds_model_gateway_route_descriptor_timeout_seed_and_hash(tmp_path):
    options = {
        "seed": 7,
        "context_window": 8192,
        "reserved_output_tokens": 1024,
        "context_safety_margin_tokens": 512,
    }
    config = ModelConfig(
        provider="ollama",
        model="gemma-test",
        timeout_seconds=33,
        options=options,
    )
    gateway = ModelGateway(models={"local": config}, default_model="local")
    controller = LLMController(gateway)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime = HarnessRuntime(
        goal=DemoProfile().default_goal(),
        profile=DemoProfile(),
        controller=controller,
        run_dir=tmp_path / "run",
        workspace=workspace,
        model_revision=gateway.revision,
        task_revision="task-v1",
    )

    bound = runtime.manifest_body["config"]["model_gateway"]
    assert bound["revision"] == gateway.revision
    route = bound["descriptor"]["models"]["local"]
    assert route["timeout_seconds"] == 33
    assert route["options"]["seed"] == 7
    assert len(route["options_hash"]) == 64


def test_gateway_snapshots_mutable_model_options_at_construction():
    options = {"context_window": 8192}
    original = ModelConfig(provider="ollama", model="m", options=options)
    gateway = ModelGateway(models={"local": original}, default_model="local")
    revision = gateway.revision

    options["context_window"] = 999999
    original.options["context_window"] = 123

    assert gateway.models["local"].options["context_window"] == 8192
    assert gateway.revision == revision
