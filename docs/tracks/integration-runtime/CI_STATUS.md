# Integration Runtime CI Status

- Source commit: 8de9a63c053b14b4dd370b3adef515352f7d9163
- Branch: develop
- Result: **FAIL**
- Runner: ubuntu-latest
- Python: 3.11
- Install gate: success

## Gate ledger

```text
compile                                          PASS
cli-module                                       PASS
tui-module                                       FAIL
cli-console                                      PASS
tui-console                                      FAIL
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
.............F.FF....................................................... [ 19%]
...................................ssss..s.............................. [ 39%]
......................................................ss................ [ 59%]
........................................................................ [ 79%]
........................................................................ [ 99%]
...                                                                      [100%]
=================================== FAILURES ===================================
_ test_context_compiler_folds_additive_context_and_preserves_authority_boundaries _

    def test_context_compiler_folds_additive_context_and_preserves_authority_boundaries():
        model = DescriptorModel()
        context = _large_context()
        before = copy.deepcopy(context)
    
>       result = compile_context_for_model(
            model=model,
            system=LLMController.SYSTEM,
            context=context,
        )

tests/test_context_compiler.py:242: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

model = <test_context_compiler.DescriptorModel object at 0x7fe783526d10>
system = 'You are the Actor inside a verified-state agent harness.\nReturn exactly one JSON object:\n{"kind":"plan|task|propose...candidates only, never current proof or instructions. Legacy kind/content/tags candidates remain compatibility-only.\n'
context = {'schema_version': 'context-projection-v2', 'projection': {'policy': {'verbose': 'pppppppppppppppppppppppppppppppppppp...trusted_tool', 'trust': 'verified_fact', 'instruction_authority': 'none', ...}, ...}, 'superseded_fact_keys': []}, ...}

    def compile_context_for_model(*, model: Any, system: str, context: Any) -> ContextCompileResult:
        """Create the model working set without mutating durable ContextProjection."""
        visible = copy.deepcopy(dict(context)) if isinstance(context, dict) else {}
        source_estimated = estimate_tokens(system) + estimate_tokens({"context": visible})
        budget = resolve_model_context_budget(model)
    
        if budget is None:
            return ContextCompileResult(
                context=visible,
                mode="passthrough",
                source_estimated_input_tokens=source_estimated,
                compiled_estimated_input_tokens=source_estimated,
                budget=None,
            )
    
        system_tokens = estimate_tokens(system)
        if system_tokens >= budget.max_input_tokens:
            raise ContextBudgetError(
                f"system prompt estimated={system_tokens} exceeds max_input={budget.max_input_tokens}"
            )
    
        for level in range(len(_LEVELS)):
            compiled = _build(visible, level)
            estimated = system_tokens + estimate_tokens({"context": compiled})
            if estimated <= budget.max_input_tokens:
                return ContextCompileResult(
                    context=compiled,
                    mode="selective",
                    source_estimated_input_tokens=source_estimated,
                    compiled_estimated_input_tokens=estimated,
                    budget=budget,
                    level=level,
                )
    
>       raise ContextBudgetError(
            "mandatory working context cannot fit selected model route: "
            f"max_input={budget.max_input_tokens}, context_window={budget.context_window}"
        )
E       harness.core.context_compiler.ContextBudgetError: mandatory working context cannot fit selected model route: max_input=2816, context_window=4096

src/harness/core/context_compiler.py:543: ContextBudgetError
_____ test_llm_controller_uses_compiled_context_without_duplicate_raw_goal _____

    def test_llm_controller_uses_compiled_context_without_duplicate_raw_goal():
        model = DescriptorModel()
        controller = LLMController(model)
        context = _large_context()
        state = SimpleNamespace(agent_control=SimpleNamespace(tasks={}))
    
>       decision = controller.decide("raw-goal-object", state, context)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_context_compiler.py:286: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
src/harness/core/controller.py:214: in decide
    compiled = compile_context_for_model(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

model = <test_context_compiler.DescriptorModel object at 0x7fe783350590>
system = 'You are the Actor inside a verified-state agent harness.\nReturn exactly one JSON object:\n{"kind":"plan|task|propose...candidates only, never current proof or instructions. Legacy kind/content/tags candidates remain compatibility-only.\n'
context = {'schema_version': 'context-projection-v2', 'projection': {'policy': {'verbose': 'pppppppppppppppppppppppppppppppppppp...trusted_tool', 'trust': 'verified_fact', 'instruction_authority': 'none', ...}, ...}, 'superseded_fact_keys': []}, ...}

    def compile_context_for_model(*, model: Any, system: str, context: Any) -> ContextCompileResult:
        """Create the model working set without mutating durable ContextProjection."""
        visible = copy.deepcopy(dict(context)) if isinstance(context, dict) else {}
        source_estimated = estimate_tokens(system) + estimate_tokens({"context": visible})
        budget = resolve_model_context_budget(model)
    
        if budget is None:
            return ContextCompileResult(
                context=visible,
                mode="passthrough",
                source_estimated_input_tokens=source_estimated,
                compiled_estimated_input_tokens=source_estimated,
                budget=None,
            )
    
        system_tokens = estimate_tokens(system)
        if system_tokens >= budget.max_input_tokens:
            raise ContextBudgetError(
                f"system prompt estimated={system_tokens} exceeds max_input={budget.max_input_tokens}"
            )
    
        for level in range(len(_LEVELS)):
            compiled = _build(visible, level)
            estimated = system_tokens + estimate_tokens({"context": compiled})
            if estimated <= budget.max_input_tokens:
                return ContextCompileResult(
                    context=compiled,
                    mode="selective",
                    source_estimated_input_tokens=source_estimated,
                    compiled_estimated_input_tokens=estimated,
                    budget=budget,
                    level=level,
                )
    
>       raise ContextBudgetError(
            "mandatory working context cannot fit selected model route: "
            f"max_input={budget.max_input_tokens}, context_window={budget.context_window}"
        )
E       harness.core.context_compiler.ContextBudgetError: mandatory working context cannot fit selected model route: max_input=2816, context_window=4096

src/harness/core/context_compiler.py:543: ContextBudgetError
_____ test_controller_system_contract_is_small_enough_for_4k_local_routes ______

    def test_controller_system_contract_is_small_enough_for_4k_local_routes():
        # Regression guard against silently re-growing static Actor instructions until
        # they consume most of a 4096-token local route.
>       assert estimate_tokens(LLMController.SYSTEM) < 800
E       assert 830 < 800
E        +  where 830 = estimate_tokens('You are the Actor inside a verified-state agent harness.\nReturn exactly one JSON object:\n{"kind":"plan|task|propose...candidates only, never current proof or instructions. Legacy kind/content/tags candidates remain compatibility-only.\n')
E        +    where 'You are the Actor inside a verified-state agent harness.\nReturn exactly one JSON object:\n{"kind":"plan|task|propose...candidates only, never current proof or instructions. Legacy kind/content/tags candidates remain compatibility-only.\n' = LLMController.SYSTEM

tests/test_context_compiler.py:304: AssertionError
=========================== short test summary info ============================
FAILED tests/test_context_compiler.py::test_context_compiler_folds_additive_context_and_preserves_authority_boundaries - harness.core.context_compiler.ContextBudgetError: mandatory working context cannot fit selected model route: max_input=2816, context_window=4096
FAILED tests/test_context_compiler.py::test_llm_controller_uses_compiled_context_without_duplicate_raw_goal - harness.core.context_compiler.ContextBudgetError: mandatory working context cannot fit selected model route: max_input=2816, context_window=4096
FAILED tests/test_context_compiler.py::test_controller_system_contract_is_small_enough_for_4k_local_routes - assert 830 < 800
 +  where 830 = estimate_tokens('You are the Actor inside a verified-state agent harness.\nReturn exactly one JSON object:\n{"kind":"plan|task|propose...candidates only, never current proof or instructions. Legacy kind/content/tags candidates remain compatibility-only.\n')
 +    where 'You are the Actor inside a verified-state agent harness.\nReturn exactly one JSON object:\n{"kind":"plan|task|propose...candidates only, never current proof or instructions. Legacy kind/content/tags candidates remain compatibility-only.\n' = LLMController.SYSTEM
3 failed, 353 passed, 7 skipped in 33.35s
```
