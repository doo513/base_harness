# Integration Runtime CI Status

- Source commit: 39a9468839c7ef48ff58ab760d2b47fcebf0a400
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
    
>       decision = controller.decide("goal", state, {})
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_local_model_protocol_compat.py:102: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <harness.core.controller.LLMController object at 0x7fc3d6895950>
goal = 'goal', state = namespace(agent_control=namespace(tasks={}))
context = FailureContext(kind=<FailureKind.MODEL_PROTOCOL_ERROR: 'model_protocol_error'>, origin=<FailureOrigin.MODEL: 'model'>,...l_id=None, call_id=None, exit_code=None, stderr_digest=None, metadata={'protocol_error_kind': 'protocol_invalid_json'})

    def decide(self, goal, state, context):
        self.model_attempt_sequence += 1
        self.last_protocol_decode = None
        compiled = compile_context_for_model(
            model=self.model,
            system=self.SYSTEM,
            context=context,
        )
        self.last_context_compile = compiled.telemetry()
    
        user = json.dumps(
            {"context": compiled.context},
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )
        raw = self._complete(system=self.SYSTEM, user=user)
    
        # Configured ModelGateway routes already performed the only bounded
        # lexical repair and retry/fallback policy. Non-Gateway adapters retain
        # the compatibility parser but never receive Controller-owned retries.
        allow_lexical_repair = not bool(
            getattr(self.model, "normalizes_decision_protocol", False)
        )
        try:
            decoded = decode_decision_text(
                raw,
                allow_control_character_repair=allow_lexical_repair,
            )
        except DecisionProtocolError as exc:
            context = FailureContext(
                kind=FailureKind.MODEL_PROTOCOL_ERROR,
                origin=FailureOrigin.MODEL,
                phase=FailurePhase.PROTOCOL_VALIDATE,
                message=f"model decision protocol failed: {exc}",
                retryable=False,
                fallback_safe=False,
                metadata={"protocol_error_kind": exc.kind},
            )
>           raise ControllerBoundaryError(failure_context=context) from exc
E           harness.core.controller.ControllerBoundaryError: model decision protocol failed: decision JSON is invalid: Expecting value

src/harness/core/controller.py:243: ControllerBoundaryError
__________ test_task_auto_promotion_only_applies_before_a_plan_exists __________

    def test_task_auto_promotion_only_applies_before_a_plan_exists():
        raw_task = '{"kind":"task","payload":{"id":"task-01","status":"active","note":"inspect"}}'
    
        empty_state = SimpleNamespace(agent_control=SimpleNamespace(tasks={}))
        promoted = LLMController(_SequenceModel([raw_task])).decide("goal", empty_state, {})
>       assert promoted.kind == "plan"
E       AssertionError: assert 'task' == 'plan'
E         
E         - plan
E         + task

tests/test_local_model_protocol_compat.py:112: AssertionError
______ test_protocol_provider_error_becomes_model_protocol_boundary_error ______

    def test_protocol_provider_error_becomes_model_protocol_boundary_error():
        controller = LLMController(RaisingModel(ProviderFailure("protocol_invalid_json", True)))
        with pytest.raises(ControllerBoundaryError) as caught:
            controller._complete(system="s", user="u")
>       assert caught.value.failure_kind is FailureKind.MODEL_PROTOCOL_ERROR
E       AssertionError: assert <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> is <FailureKind.MODEL_PROTOCOL_ERROR: 'model_protocol_error'>
E        +  where <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> = ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: protocol_invalid_json').failure_kind
E        +    where ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: protocol_invalid_json') = <ExceptionInfo ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: protocol_invalid_json') tblen=2>.value
E        +  and   <FailureKind.MODEL_PROTOCOL_ERROR: 'model_protocol_error'> = FailureKind.MODEL_PROTOCOL_ERROR

tests/test_model_boundary_failure_taxonomy.py:27: AssertionError
__________ test_transport_provider_error_remains_model_provider_error __________

    def test_transport_provider_error_remains_model_provider_error():
        controller = LLMController(RaisingModel(ProviderFailure("timeout", True)))
        with pytest.raises(ControllerBoundaryError) as caught:
            controller._complete(system="s", user="u")
>       assert caught.value.failure_kind is FailureKind.MODEL_PROVIDER_ERROR
E       AssertionError: assert <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> is <FailureKind.MODEL_PROVIDER_ERROR: 'model_provider_error'>
E        +  where <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> = ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: timeout').failure_kind
E        +    where ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: timeout') = <ExceptionInfo ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: timeout') tblen=2>.value
E        +  and   <FailureKind.MODEL_PROVIDER_ERROR: 'model_provider_error'> = FailureKind.MODEL_PROVIDER_ERROR

tests/test_model_boundary_failure_taxonomy.py:36: AssertionError
_ test_embedded_command_adapter_protocol_error_overrides_outer_execution_error _

    def test_embedded_command_adapter_protocol_error_overrides_outer_execution_error():
        marker = encode_model_error(
            kind="protocol_schema",
            message="tool.tool must be non-empty",
            retryable=True,
        )
        outer = ProviderFailure("execution_error", False)
        outer.args = (f"model command failed (2): prefix\n{marker}\n",)
    
        controller = LLMController(RaisingModel(outer))
        with pytest.raises(ControllerBoundaryError) as caught:
            controller._complete(system="s", user="u")
    
>       assert caught.value.failure_kind is FailureKind.MODEL_PROTOCOL_ERROR
E       assert <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> is <FailureKind.MODEL_PROTOCOL_ERROR: 'model_protocol_error'>
E        +  where <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> = ControllerBoundaryError('unclassified model adapter error: ProviderFailure: model command failed (2): prefix\nHARNESS_MODEL_ERROR:{"kind":"protocol_schema","message":"tool.tool must be non-empty","retryable":true}\n').failure_kind
E        +    where ControllerBoundaryError('unclassified model adapter error: ProviderFailure: model command failed (2): prefix\nHARNESS_MODEL_ERROR:{"kind":"protocol_schema","message":"tool.tool must be non-empty","retryable":true}\n') = <ExceptionInfo ControllerBoundaryError('unclassified model adapter error: ProviderFailure: model command failed (2): p...x\nHARNESS_MODEL_ERROR:{"kind":"protocol_schema","message":"tool.tool must be non-empty","retryable":true}\n') tblen=2>.value
E        +  and   <FailureKind.MODEL_PROTOCOL_ERROR: 'model_protocol_error'> = FailureKind.MODEL_PROTOCOL_ERROR

tests/test_model_boundary_failure_taxonomy.py:54: AssertionError
_______________ test_provider_retry_requires_explicit_retry_safe _______________

    def test_provider_retry_requires_explicit_retry_safe():
        router = FailureRouter()
        unsafe = Failure(FailureKind.MODEL_PROVIDER_ERROR, "provider unavailable")
        safe = Failure(
            FailureKind.MODEL_PROVIDER_ERROR,
            "provider timed out",
            retry_safe=True,
        )
        assert router.route(unsafe) is RecoveryAction.OBSERVE
>       assert router.route(safe) is RecoveryAction.RETRY
E       AssertionError: assert <RecoveryAction.OBSERVE: 'observe'> is <RecoveryAction.RETRY: 'retry'>
E        +  where <RecoveryAction.OBSERVE: 'observe'> = route(Failure(kind=<FailureKind.MODEL_PROVIDER_ERROR: 'model_provider_error'>, message='provider timed out', action=None, retry_safe=True, signature_key=None, context=None))
E        +    where route = <harness.core.failures.FailureRouter object at 0x7fc3d677abd0>.route
E        +  and   <RecoveryAction.RETRY: 'retry'> = RecoveryAction.RETRY

tests/test_model_boundary_failure_taxonomy.py:84: AssertionError
=========================== short test summary info ============================
FAILED tests/test_integration_model_gateway.py::test_model_gateway_falls_back_without_granting_any_kernel_authority - harness.model_gateway.ModelGatewayFailure: model gateway failed: model_protocol_error: decision object must contain exactly kind and payload
FAILED tests/test_local_model_gateway_adapters.py::test_local_gateway_repairs_truncated_json_before_controller_sees_it - AssertionError: assert 'LOCAL MODEL PROTOCOL REPAIR' in 'user\n\nMODEL PROTOCOL REPAIR:\nThe previous answer failed with protocol_truncated. Return exactly one complete JSON ...g the Harness decision schema. Do not use markdown fences or commentary. Do not invent missing tool names or task IDs.'
 +  where 'user\n\nMODEL PROTOCOL REPAIR:\nThe previous answer failed with protocol_truncated. Return exactly one complete JSON ...g the Harness decision schema. Do not use markdown fences or commentary. Do not invent missing tool names or task IDs.' = ModelRequest(system='system', user='user\n\nMODEL PROTOCOL REPAIR:\nThe previous answer failed with protocol_truncated... the Harness decision schema. Do not use markdown fences or commentary. Do not invent missing tool names or task IDs.').user
FAILED tests/test_local_model_protocol_compat.py::test_controller_extracts_fenced_json_and_retries_one_empty_actor_response - harness.core.controller.ControllerBoundaryError: model decision protocol failed: decision JSON is invalid: Expecting value
FAILED tests/test_local_model_protocol_compat.py::test_task_auto_promotion_only_applies_before_a_plan_exists - AssertionError: assert 'task' == 'plan'
  
  - plan
  + task
FAILED tests/test_model_boundary_failure_taxonomy.py::test_protocol_provider_error_becomes_model_protocol_boundary_error - AssertionError: assert <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> is <FailureKind.MODEL_PROTOCOL_ERROR: 'model_protocol_error'>
 +  where <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> = ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: protocol_invalid_json').failure_kind
 +    where ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: protocol_invalid_json') = <ExceptionInfo ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: protocol_invalid_json') tblen=2>.value
 +  and   <FailureKind.MODEL_PROTOCOL_ERROR: 'model_protocol_error'> = FailureKind.MODEL_PROTOCOL_ERROR
FAILED tests/test_model_boundary_failure_taxonomy.py::test_transport_provider_error_remains_model_provider_error - AssertionError: assert <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> is <FailureKind.MODEL_PROVIDER_ERROR: 'model_provider_error'>
 +  where <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> = ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: timeout').failure_kind
 +    where ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: timeout') = <ExceptionInfo ControllerBoundaryError('unclassified model adapter error: ProviderFailure: provider failed: timeout') tblen=2>.value
 +  and   <FailureKind.MODEL_PROVIDER_ERROR: 'model_provider_error'> = FailureKind.MODEL_PROVIDER_ERROR
FAILED tests/test_model_boundary_failure_taxonomy.py::test_embedded_command_adapter_protocol_error_overrides_outer_execution_error - assert <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> is <FailureKind.MODEL_PROTOCOL_ERROR: 'model_protocol_error'>
 +  where <FailureKind.IMPLEMENTATION_ERROR: 'implementation_error'> = ControllerBoundaryError('unclassified model adapter error: ProviderFailure: model command failed (2): prefix\nHARNESS_MODEL_ERROR:{"kind":"protocol_schema","message":"tool.tool must be non-empty","retryable":true}\n').failure_kind
 +    where ControllerBoundaryError('unclassified model adapter error: ProviderFailure: model command failed (2): prefix\nHARNESS_MODEL_ERROR:{"kind":"protocol_schema","message":"tool.tool must be non-empty","retryable":true}\n') = <ExceptionInfo ControllerBoundaryError('unclassified model adapter error: ProviderFailure: model command failed (2): p...x\nHARNESS_MODEL_ERROR:{"kind":"protocol_schema","message":"tool.tool must be non-empty","retryable":true}\n') tblen=2>.value
 +  and   <FailureKind.MODEL_PROTOCOL_ERROR: 'model_protocol_error'> = FailureKind.MODEL_PROTOCOL_ERROR
FAILED tests/test_model_boundary_failure_taxonomy.py::test_provider_retry_requires_explicit_retry_safe - AssertionError: assert <RecoveryAction.OBSERVE: 'observe'> is <RecoveryAction.RETRY: 'retry'>
 +  where <RecoveryAction.OBSERVE: 'observe'> = route(Failure(kind=<FailureKind.MODEL_PROVIDER_ERROR: 'model_provider_error'>, message='provider timed out', action=None, retry_safe=True, signature_key=None, context=None))
 +    where route = <harness.core.failures.FailureRouter object at 0x7fc3d677abd0>.route
 +  and   <RecoveryAction.RETRY: 'retry'> = RecoveryAction.RETRY
8 failed, 381 passed, 7 skipped in 29.32s
```
