import pytest

from harness.core.context_compiler import ContextBudgetError
from harness.core.controller import LLMController
from harness.core.state import HarnessState


class _LocalModel:
    def __init__(self):
        self.calls = 0

    def descriptor(self):
        return {
            "default_model": "local",
            "models": {
                "local": {
                    "provider": "ollama",
                    "model": "local-test",
                    "endpoint": "http://127.0.0.1:11434",
                    "options": {},
                }
            },
        }

    def complete(self, *, system, user):
        self.calls += 1
        return '{"kind":"complete","payload":{"reason":"unexpected"}}'


def test_impossible_mandatory_context_fails_before_provider_request():
    model = _LocalModel()
    controller = LLMController(model)
    context = {
        "schema_version": "context-projection-v2",
        "goal_contract": {
            "goal": "g" * 20000,
            "acceptance": ["a" * 4000],
            "constraints": ["c" * 4000],
            "pinned_constraints": [],
            "task_id": "too-large",
        },
        "trusted": {"facts": {}, "superseded_fact_keys": []},
        "untrusted": {
            "hypotheses": {},
            "refuted_hypotheses": {},
            "observations": [],
            "unknowns": [],
            "retrieval": [],
        },
        "control": {
            "step": 0,
            "recent_failures": [],
            "recovery_directive": None,
            "strategy_generation": 0,
            "recovery_halted": False,
            "recovery_halt_reason": None,
            "progress": {},
        },
        "tools": {},
    }

    with pytest.raises(ContextBudgetError):
        controller.decide("ignored-raw-goal", HarnessState(), context)

    assert model.calls == 0
