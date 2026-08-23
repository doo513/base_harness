from harness.core.context_compiler import compile_context_for_model
from harness.core.controller import LLMController


class _LocalModel:
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


def test_4k_compaction_preserves_all_verified_fact_identities():
    facts = {
        f"fact.{index}": {
            "key": f"fact.{index}",
            "status": "verified",
            "authority": "trusted_tool",
            "trust": "verified_fact",
            "instruction_authority": "none",
            "value": "x" * 1200,
            "value_hash": "f" * 64,
            "value_preview": {
                "text": "x" * 900,
                "original_chars": 1200,
                "visible_chars": 900,
                "truncated": True,
            },
            "evidence_refs": ["artifact://" + "a" * 64 + "_fact.json"],
        }
        for index in range(20)
    }
    context = {
        "schema_version": "context-projection-v2",
        "goal_contract": {
            "goal": "Implement the requested program.",
            "acceptance": ["Program exists and is testable."],
            "constraints": ["Stay inside the workspace."],
            "pinned_constraints": [],
            "task_id": "ctx-facts",
        },
        "trusted": {"facts": facts, "superseded_fact_keys": ["old.fact"]},
        "untrusted": {
            "hypotheses": {},
            "refuted_hypotheses": {},
            "observations": [],
            "unknowns": [],
            "retrieval": [],
        },
        "control": {
            "step": 3,
            "recent_failures": [],
            "recovery_directive": None,
            "strategy_generation": 0,
            "recovery_halted": False,
            "recovery_halt_reason": None,
            "progress": {"no_progress_streak": 0},
        },
        "tools": {
            "file.read": {
                "description": "Read a workspace file.",
                "side_effect": "read",
                "idempotent": True,
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        },
        "active_context": {
            "facts": [
                {
                    "key": "fact.0",
                    "authority": "trusted_tool",
                    "value_preview": {
                        "text": "current relevant fact",
                        "original_chars": 21,
                        "visible_chars": 21,
                        "truncated": False,
                    },
                    "evidence_refs": ["artifact://" + "a" * 64 + "_fact.json"],
                }
            ],
            "hypotheses": [],
            "observations": [],
        },
    }

    result = compile_context_for_model(
        model=_LocalModel(),
        system=LLMController.SYSTEM,
        context=context,
    )

    assert result.mode == "selective"
    assert result.budget is not None
    assert result.compiled_estimated_input_tokens <= result.budget.max_input_tokens
    assert set(result.context["trusted"]["facts"]) == set(facts)
    assert result.context["trusted"]["superseded_fact_keys"] == ["old.fact"]
    assert result.context["trusted"]["facts"]["fact.0"]["value_preview"]["text"]
