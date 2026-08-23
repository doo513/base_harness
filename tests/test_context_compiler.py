import copy
import json
from types import SimpleNamespace

from harness.core.context_compiler import (
    compile_context_for_model,
    estimate_tokens,
    resolve_model_context_budget,
)
from harness.core.controller import LLMController


class DescriptorModel:
    def __init__(self, *, provider="ollama", endpoint="http://127.0.0.1:11434", options=None, output=None):
        self.provider = provider
        self.endpoint = endpoint
        self.options = dict(options or {})
        self.output = output or '{"kind":"complete","payload":{"reason":"ok"}}'
        self.calls = []

    def descriptor(self):
        return {
            "schema_version": "model-gateway-v2",
            "default_model": "local",
            "models": {
                "local": {
                    "provider": self.provider,
                    "model": "local-test",
                    "endpoint": self.endpoint,
                    "options": dict(self.options),
                }
            },
        }

    def complete(self, *, system, user):
        self.calls.append({"system": system, "user": user})
        return self.output


def _large_context():
    evidence_a = "artifact://" + "a" * 64 + "_fact.json"
    evidence_b = "artifact://" + "b" * 64 + "_obs.json"
    retrieval_ref = "artifact://" + "c" * 64 + "_retrieval.txt"
    return {
        "schema_version": "context-projection-v2",
        "projection": {"policy": {"verbose": "p" * 2000}},
        "goal_contract": {
            "goal": "Create a localhost port detector.",
            "acceptance": ["The requested program exists and is testable."],
            "constraints": ["Stay inside the workspace."],
            "pinned_constraints": [],
            "task_id": "task-1",
        },
        "trusted": {
            "facts": {
                f"fact.{index}": {
                    "key": f"fact.{index}",
                    "authority": "trusted_tool",
                    "trust": "verified_fact",
                    "instruction_authority": "none",
                    "value": "x" * 1200,
                    "value_preview": {
                        "text": "x" * 900,
                        "original_chars": 1200,
                        "visible_chars": 900,
                        "truncated": True,
                    },
                    "evidence_refs": [evidence_a],
                }
                for index in range(20)
            },
            "superseded_fact_keys": [],
        },
        "untrusted": {
            "hypotheses": {
                f"hyp.{index}": {
                    "key": f"hyp.{index}",
                    "trust": "untrusted_speculation",
                    "instruction_authority": "none",
                    "value_preview": {"text": "h" * 700, "truncated": False},
                    "evidence_refs": [],
                }
                for index in range(10)
            },
            "refuted_hypotheses": {},
            "observations": [
                {
                    "source": "file.read",
                    "ok": True,
                    "latest_step": index,
                    "artifact_ref": evidence_b,
                    "preview": {"text": "o" * 900, "truncated": False},
                }
                for index in range(12)
            ],
            "unknowns": [{"text": "u" * 400} for _ in range(8)],
            "retrieval": [
                {
                    "item_id": f"retrieval-{index}",
                    "content_ref": retrieval_ref,
                    "source_id": "project-memory",
                    "source_revision": "r1",
                    "source_locator": "memory://item",
                    "preview": {"text": "r" * 800, "truncated": False},
                }
                for index in range(5)
            ],
        },
        "control": {
            "step": 10,
            "recent_failures": [
                {
                    "kind": "model_protocol",
                    "target": "actor",
                    "message": "m" * 800,
                    "repeat_count": index + 1,
                }
                for index in range(5)
            ],
            "recovery_directive": None,
            "strategy_generation": 2,
            "recovery_halted": False,
            "recovery_halt_reason": None,
            "progress": {"no_progress_streak": 3, "detail": "p" * 300},
        },
        "tools": {
            f"tool.{index}": {
                "description": "d" * 500,
                "side_effect": "read",
                "idempotent": True,
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            }
            for index in range(8)
        },
        "agent_workflow": {
            "schema_version": "agent-control-v1",
            "objective": "inspect and implement " * 20,
            "active_task_id": "t1",
            "tasks": [
                {
                    "id": f"t{index}",
                    "title": "task title " * 20,
                    "status": "pending",
                    "depends_on": [],
                }
                for index in range(10)
            ],
        },
        "active_context": {
            "facts": [
                {
                    "key": "fact.0",
                    "authority": "trusted_tool",
                    "value_preview": {
                        "text": "relevant fact " * 60,
                        "original_chars": 1200,
                        "visible_chars": 840,
                        "truncated": True,
                    },
                    "evidence_refs": [evidence_a],
                }
            ],
            "hypotheses": [
                {
                    "key": "hyp.0",
                    "value_preview": {"text": "relevant hypothesis " * 30},
                    "evidence_refs": [],
                }
            ],
            "observations": [
                {
                    "source": "file.read",
                    "step": 11,
                    "artifact_ref": evidence_b,
                    "preview": {"text": "relevant observation " * 40, "truncated": False},
                }
            ],
        },
        "project_memory": {
            "enabled": True,
            "trust": "untrusted_project_memory",
            "instruction_authority": "none",
            "read_protocol": "Stage-08 retrieval only",
        },
        "domain_contract": {
            "profile": "software",
            "authority": "harness_domain_contract",
            "workflow": {"text": "w" * 1000},
            "evaluation": {"text": "e" * 1000},
            "evaluation_truth_authority": "none",
            "evaluation_progress_authority": False,
            "evaluation_completion_authority": False,
        },
    }


def test_local_routes_get_conservative_context_budget_and_explicit_override():
    default_budget = resolve_model_context_budget(DescriptorModel())
    assert default_budget is not None
    assert default_budget.context_window == 4096
    assert default_budget.reserved_output_tokens == 1024
    assert default_budget.max_input_tokens < default_budget.context_window
    assert default_budget.source == "local_compat_default"

    explicit = resolve_model_context_budget(
        DescriptorModel(
            provider="lm-studio",
            endpoint="http://127.0.0.1:1234/v1",
            options={
                "context_window": 8192,
                "reserved_output_tokens": 768,
                "context_safety_margin_tokens": 256,
            },
        )
    )
    assert explicit is not None
    assert explicit.context_window == 8192
    assert explicit.reserved_output_tokens == 768
    assert explicit.safety_margin_tokens == 256
    assert explicit.source == "model_option"


def test_openai_compatible_local_ports_are_budgeted_without_provider_rename():
    budget = resolve_model_context_budget(
        DescriptorModel(
            provider="openai-compatible",
            endpoint="http://127.0.0.1:1234/v1",
        )
    )
    assert budget is not None
    assert budget.context_window == 4096


def test_context_compiler_folds_additive_context_and_preserves_authority_boundaries():
    model = DescriptorModel()
    context = _large_context()
    before = copy.deepcopy(context)

    result = compile_context_for_model(
        model=model,
        system=LLMController.SYSTEM,
        context=context,
    )

    assert result.mode == "selective"
    assert result.budget is not None
    assert result.compiled_estimated_input_tokens <= result.budget.max_input_tokens
    assert result.compiled_estimated_input_tokens < result.source_estimated_input_tokens
    assert result.context["schema_version"] == "working-context-v1"
    assert "active_context" not in result.context
    assert result.context["goal_contract"] == before["goal_contract"]
    assert set(result.context["tools"]) == set(before["tools"])
    assert "fact.0" in result.context["trusted"]["facts"]
    assert (
        result.context["trusted"]["facts"]["fact.0"]["evidence_refs"]
        == before["active_context"]["facts"][0]["evidence_refs"]
    )
    assert result.context["projection"]["raw_evidence_preserved"] is True
    assert result.context["projection"]["durable_state_mutated"] is False
    assert context == before


def test_remote_route_without_context_metadata_keeps_existing_projection():
    model = DescriptorModel(
        provider="openai-compatible",
        endpoint="https://provider.example/v1",
    )
    context = {"schema_version": "context-projection-v2", "goal_contract": {"goal": "x"}}

    result = compile_context_for_model(model=model, system="system", context=context)

    assert result.mode == "passthrough"
    assert result.budget is None
    assert result.context == context


def test_llm_controller_uses_compiled_context_without_duplicate_raw_goal():
    model = DescriptorModel()
    controller = LLMController(model)
    context = _large_context()
    state = SimpleNamespace(agent_control=SimpleNamespace(tasks={}))

    decision = controller.decide("raw-goal-object", state, context)

    assert decision.kind == "complete"
    assert len(model.calls) == 1
    payload = json.loads(model.calls[0]["user"])
    assert set(payload) == {"context"}
    assert payload["context"]["schema_version"] == "working-context-v1"
    assert payload["context"]["goal_contract"]["goal"] == context["goal_contract"]["goal"]
    assert controller.last_context_compile is not None
    assert controller.last_context_compile["mode"] == "selective"
    assert controller.last_context_compile["compiled_estimated_input_tokens"] <= (
        controller.last_context_compile["budget"]["max_input_tokens"]
    )


def test_controller_system_contract_is_small_enough_for_4k_local_routes():
    # Regression guard against silently re-growing static Actor instructions until
    # they consume most of a 4096-token local route.
    assert estimate_tokens(LLMController.SYSTEM) < 800