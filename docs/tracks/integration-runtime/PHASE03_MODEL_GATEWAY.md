# Phase 03 — Model Gateway

Status: IMPLEMENTED; targeted tests added; real-provider live evaluation remains Phase 11 evidence.

## Problem / evidence

The pre-integration model boundary was a single `CommandModelAdapter` using `subprocess.run(..., shell=True)`. There was no provider registry, retry/fallback policy, normalized error vocabulary, usage telemetry, or deterministic provider/model configuration revision for resume.

## Contract

- `LLMController` remains the Kernel-facing decision parser; provider output still only proposes a `Decision`;
- providers are behind a `ModelGateway` and never receive state-commit/completion authority;
- provider credentials are resolved through Phase 02 `SecretResolver` and are not included in descriptors;
- retries occur only for provider failures marked retryable;
- fallbacks are explicit configured aliases;
- provider/model configuration produces a deterministic revision used by CLI-created runs for resume drift detection;
- native provider tool-calling capability is metadata only for now: tool execution still must normalize through Kernel decisions before it can be enabled.

## Implementation

- added provider-neutral request/response/usage/error contracts;
- added `ProviderRegistry`;
- added secure argv-based `CommandProvider` (`shell=False`);
- added standard-library OpenAI-compatible chat-completions provider, also registered as `openai` when an explicit endpoint is supplied;
- added bounded retry, ordered fallback, request/token/latency telemetry, and normalized failure kinds;
- added deterministic `ModelGateway.revision` that contains no resolved secret values;
- migrated legacy `CommandModelAdapter` to the Gateway;
- CLI now consumes configured `default_model`, optional fallback aliases from default-model `options.fallback_models`, or legacy `--model-command` override;
- CLI automatically records the gateway revision as `model_revision` unless explicitly overridden.

## Structural review

- `LLMController` decision validation and Runtime dispatch are unchanged;
- Gateway output cannot directly mutate `HarnessState`, execute a tool, promote a fact, or accept completion;
- fallback changes the model route only, not Kernel authority;
- resume gets a deterministic model revision from Gateway configuration;
- raw provider secrets are absent from Gateway descriptors/telemetry.

## Validation focus

`tests/test_integration_model_gateway.py` covers retryable failure, fallback, usage/request telemetry, descriptor secret hygiene, and command-provider wire compatibility.

## Remaining limitations

- Anthropic/Gemini/native SDK adapters are not yet implemented; provider registry is the extension boundary;
- the OpenAI-compatible adapter is non-streaming at the harness API even though capability metadata records provider support;
- native tool calling is not directly executed and must be normalized through the Tool Gateway in Phase 05/06;
- real API/rate-limit/provider-compatibility evaluation is deferred to real E2E.
