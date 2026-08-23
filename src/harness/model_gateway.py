from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic, sleep
from typing import Any, Callable, Mapping, Protocol
import hashlib
import json
import re
import shlex
import subprocess
import urllib.error
import urllib.request
from urllib.parse import urlparse

from harness.config import ConfigError, ModelConfig, SecretResolver


class ModelGatewayError(RuntimeError):
    pass


class ProviderError(ModelGatewayError):
    def __init__(self, message: str, *, kind: str = "provider_error", retryable: bool = False):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


@dataclass(frozen=True)
class ProviderCapabilities:
    structured_output: bool = False
    native_tool_calling: bool = False
    streaming: bool = False
    vision: bool = False
    reasoning: bool = False

    def dump(self) -> dict[str, bool]:
        return {
            "structured_output": self.structured_output,
            "native_tool_calling": self.native_tool_calling,
            "streaming": self.streaming,
            "vision": self.vision,
            "reasoning": self.reasoning,
        }


@dataclass(frozen=True)
class ModelRequest:
    system: str
    user: str


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def dump(self) -> dict[str, int | None]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class ModelResponse:
    content: str
    provider_id: str
    model_id: str | None
    request_id: str | None = None
    usage: ModelUsage = field(default_factory=ModelUsage)
    latency_seconds: float = 0.0
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class ModelProvider(Protocol):
    provider_id: str
    capabilities: ProviderCapabilities

    def complete(self, request: ModelRequest) -> ModelResponse: ...


_DECISION_KINDS = (
    "plan", "task", "propose", "verify_claim", "tool", "retrieve", "refute", "complete"
)

_DECISION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "payload"],
    "properties": {
        "kind": {"type": "string", "enum": list(_DECISION_KINDS)},
        "payload": {"type": "object"},
    },
}


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else text


def _looks_truncated_json(text: str, exc: json.JSONDecodeError) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    if stripped.count("{") > stripped.count("}") or stripped.count("[") > stripped.count("]"):
        return True
    return exc.pos >= max(0, len(stripped) - 2)


def _canonical_decision_json(content: str) -> str:
    text = _strip_json_fence(content)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        kind = "protocol_truncated" if _looks_truncated_json(text, exc) else "protocol_invalid_json"
        raise ProviderError(
            f"local model returned invalid decision JSON: {exc.msg}",
            kind=kind,
            retryable=True,
        ) from exc

    if not isinstance(obj, dict):
        raise ProviderError("decision must be a JSON object", kind="protocol_schema", retryable=True)
    if set(obj) != {"kind", "payload"}:
        raise ProviderError(
            "decision object must contain exactly kind and payload",
            kind="protocol_schema",
            retryable=True,
        )
    kind = obj.get("kind")
    payload = obj.get("payload")
    if kind not in _DECISION_KINDS or not isinstance(payload, dict):
        raise ProviderError("decision kind/payload violates harness protocol", kind="protocol_schema", retryable=True)

    if kind == "tool":
        tool = payload.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            raise ProviderError("tool.tool must be a non-empty string", kind="protocol_schema", retryable=True)
        if not isinstance(payload.get("args", {}), dict):
            raise ProviderError("tool.args must be an object", kind="protocol_schema", retryable=True)
    elif kind == "plan":
        objective = payload.get("objective")
        tasks = payload.get("tasks")
        if not isinstance(objective, str) or not objective.strip() or not isinstance(tasks, list) or not tasks:
            raise ProviderError("plan requires non-empty objective and tasks", kind="protocol_schema", retryable=True)
    elif kind in {"verify_claim", "refute"}:
        key = payload.get("key")
        if not isinstance(key, str) or not key.strip():
            raise ProviderError(f"{kind}.key must be a non-empty string", kind="protocol_schema", retryable=True)
    elif kind == "retrieve":
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ProviderError("retrieve.query must be a non-empty string", kind="protocol_schema", retryable=True)

    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _repair_request(request: ModelRequest, error_kind: str) -> ModelRequest:
    suffix = (
        "\n\nLOCAL MODEL PROTOCOL REPAIR:\n"
        f"The previous answer failed with {error_kind}. "
        "Return exactly one complete JSON object matching the harness decision schema. "
        "Do not use markdown fences or commentary. Never emit an empty tool name."
    )
    return ModelRequest(system=request.system, user=request.user + suffix)


def _http_json(
    endpoint: str,
    *,
    body: dict[str, Any],
    timeout_seconds: float,
    api_key: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            request_id = response.headers.get("x-request-id")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")[-2000:]
        except Exception:
            detail = ""
        retryable = exc.code == 429 or 500 <= exc.code < 600
        kind = "rate_limit" if exc.code == 429 else "http_error"
        raise ProviderError(f"provider HTTP {exc.code}: {detail}", kind=kind, retryable=retryable) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"provider connection failed: {exc}", kind="network_error", retryable=True) from exc
    except TimeoutError as exc:
        raise ProviderError("provider request timed out", kind="timeout", retryable=True) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError(f"provider response is not valid JSON: {exc}", kind="invalid_response") from exc
    if not isinstance(payload, dict):
        raise ProviderError("provider response must be a JSON object", kind="invalid_response")
    return payload, request_id


class CommandProvider:
    provider_id = "command"
    capabilities = ProviderCapabilities(structured_output=True)

    def __init__(self, config: ModelConfig):
        if config.provider != "command" or not config.command:
            raise ConfigError("CommandProvider requires a command model config")
        argv = shlex.split(config.command)
        if not argv:
            raise ConfigError("command model argv must not be empty")
        self.argv = argv
        self.timeout_seconds = float(config.timeout_seconds)

    def complete(self, request: ModelRequest) -> ModelResponse:
        started = monotonic()
        try:
            proc = subprocess.run(
                self.argv,
                input=json.dumps({"system": request.system, "user": request.user}, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError("model command timed out", kind="timeout", retryable=True) from exc
        except OSError as exc:
            raise ProviderError(f"model command failed to start: {exc}", kind="execution_error") from exc
        latency = monotonic() - started
        if proc.returncode != 0:
            raise ProviderError(
                f"model command failed ({proc.returncode}): {proc.stderr[-2000:]}",
                kind="execution_error",
            )
        return ModelResponse(
            content=proc.stdout.strip(),
            provider_id=self.provider_id,
            model_id=None,
            latency_seconds=latency,
            raw_metadata={"returncode": proc.returncode},
        )


class OpenAICompatibleProvider:
    provider_id = "openai-compatible"
    capabilities = ProviderCapabilities(
        structured_output=True,
        native_tool_calling=True,
        streaming=True,
    )

    def __init__(self, config: ModelConfig, *, secret_resolver: SecretResolver):
        if config.provider not in {"openai-compatible", "openai"}:
            raise ConfigError("OpenAICompatibleProvider requires openai/openai-compatible config")
        if not config.model:
            raise ConfigError("OpenAI-compatible provider requires model")
        if not config.endpoint:
            raise ConfigError("OpenAI-compatible provider requires endpoint")
        self.model = config.model
        self.endpoint = config.endpoint.rstrip("/")
        if not self.endpoint.endswith("/chat/completions"):
            self.endpoint += "/chat/completions"
        self.api_key = secret_resolver.resolve(config.api_key)
        self.timeout_seconds = float(config.timeout_seconds)
        self.options = dict(config.options)
        try:
            parsed = urlparse(self.endpoint)
            endpoint_port = parsed.port
        except ValueError:
            endpoint_port = None
        self.ollama_compat = bool(self.options.get("ollama_compat")) or endpoint_port == 11434

    @staticmethod
    def _usage(raw: Any) -> ModelUsage:
        if not isinstance(raw, dict):
            return ModelUsage()
        prompt = raw.get("prompt_tokens")
        completion = raw.get("completion_tokens")
        total = raw.get("total_tokens")
        return ModelUsage(
            input_tokens=prompt if isinstance(prompt, int) else None,
            output_tokens=completion if isinstance(completion, int) else None,
            total_tokens=total if isinstance(total, int) else None,
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
        }
        for key in ("temperature", "max_tokens", "top_p", "reasoning_effort"):
            if key in self.options:
                body[key] = self.options[key]
        response_format = self.options.get("response_format")
        if isinstance(response_format, dict):
            body["response_format"] = dict(response_format)
        elif self.options.get("json_mode") is True:
            body["response_format"] = {"type": "json_object"}

        if self.ollama_compat:
            body.setdefault("reasoning_effort", "none")
            if self.options.get("json_mode") is not False:
                body.setdefault("response_format", {"type": "json_object"})

        started = monotonic()
        payload, request_id = _http_json(
            self.endpoint,
            body=body,
            timeout_seconds=self.timeout_seconds,
            api_key=self.api_key,
        )
        latency = monotonic() - started
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError("provider response has no choices", kind="invalid_response")
        first = choices[0]
        if not isinstance(first, dict) or not isinstance(first.get("message"), dict):
            raise ProviderError("provider choice has no message", kind="invalid_response")
        msg_dict = first["message"]
        content = msg_dict.get("content")
        if not content and isinstance(msg_dict.get("reasoning_content"), str):
            content = msg_dict["reasoning_content"]
        if not content and isinstance(msg_dict.get("text"), str):
            content = msg_dict["text"]
        if not isinstance(content, str) or not content.strip():
            reasoning_present = isinstance(msg_dict.get("reasoning"), str) and bool(msg_dict.get("reasoning", "").strip())
            detail = "; reasoning was present but final content was empty" if reasoning_present else ""
            raise ProviderError(
                "provider returned empty assistant content" + detail,
                kind="empty_response",
                retryable=True,
            )
        return ModelResponse(
            content=content,
            provider_id=self.provider_id,
            model_id=self.model,
            request_id=request_id or (payload.get("id") if isinstance(payload.get("id"), str) else None),
            usage=self._usage(payload.get("usage")),
            latency_seconds=latency,
            raw_metadata={
                "finish_reason": first.get("finish_reason"),
                "reasoning_present": isinstance(msg_dict.get("reasoning"), str) and bool(msg_dict.get("reasoning", "").strip()),
            },
        )


class OllamaProvider:
    provider_id = "ollama"
    capabilities = ProviderCapabilities(structured_output=True, streaming=True, reasoning=True)
    protocol_enforced = True

    def __init__(self, config: ModelConfig, *, secret_resolver: SecretResolver):
        if config.provider != "ollama" or not config.model:
            raise ConfigError("OllamaProvider requires provider='ollama' and model")
        endpoint = (config.endpoint or "http://127.0.0.1:11434").rstrip("/")
        self.endpoint = endpoint if endpoint.endswith("/api/chat") else endpoint + "/api/chat"
        self.model = config.model
        self.timeout_seconds = float(config.timeout_seconds)
        self.options = dict(config.options)

    def complete(self, request: ModelRequest) -> ModelResponse:
        generation_options: dict[str, Any] = {"temperature": self.options.get("temperature", 0)}
        if "top_p" in self.options:
            generation_options["top_p"] = self.options["top_p"]
        if "num_predict" in self.options:
            generation_options["num_predict"] = self.options["num_predict"]
        elif "max_tokens" in self.options:
            generation_options["num_predict"] = self.options["max_tokens"]

        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
            "format": _DECISION_JSON_SCHEMA,
            "options": generation_options,
        }
        if self.options.get("think", False) is False:
            body["think"] = False

        started = monotonic()
        payload, _ = _http_json(self.endpoint, body=body, timeout_seconds=self.timeout_seconds)
        latency = monotonic() - started
        message = payload.get("message")
        if not isinstance(message, dict):
            raise ProviderError("Ollama response has no message", kind="invalid_response")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("Ollama returned empty assistant content", kind="empty_response", retryable=True)
        prompt = payload.get("prompt_eval_count")
        completion = payload.get("eval_count")
        usage = ModelUsage(
            input_tokens=prompt if isinstance(prompt, int) else None,
            output_tokens=completion if isinstance(completion, int) else None,
            total_tokens=(prompt + completion) if isinstance(prompt, int) and isinstance(completion, int) else None,
        )
        return ModelResponse(
            content=content,
            provider_id=self.provider_id,
            model_id=self.model,
            usage=usage,
            latency_seconds=latency,
            raw_metadata={"done_reason": payload.get("done_reason"), "structured_output": "json_schema"},
        )


class LMStudioProvider:
    provider_id = "lm-studio"
    capabilities = ProviderCapabilities(structured_output=True, native_tool_calling=True, streaming=True)
    protocol_enforced = True

    def __init__(self, config: ModelConfig, *, secret_resolver: SecretResolver):
        if config.provider != "lm-studio" or not config.model:
            raise ConfigError("LMStudioProvider requires provider='lm-studio' and model")
        endpoint = (config.endpoint or "http://127.0.0.1:1234/v1").rstrip("/")
        self.endpoint = endpoint if endpoint.endswith("/chat/completions") else endpoint + "/chat/completions"
        self.model = config.model
        self.api_key = secret_resolver.resolve(config.api_key)
        self.timeout_seconds = float(config.timeout_seconds)
        self.options = dict(config.options)

    def complete(self, request: ModelRequest) -> ModelResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
            "temperature": self.options.get("temperature", 0),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "harness_decision",
                    "strict": True,
                    "schema": _DECISION_JSON_SCHEMA,
                },
            },
        }
        if "max_tokens" in self.options:
            body["max_tokens"] = self.options["max_tokens"]
        if "top_p" in self.options:
            body["top_p"] = self.options["top_p"]

        started = monotonic()
        payload, request_id = _http_json(
            self.endpoint,
            body=body,
            timeout_seconds=self.timeout_seconds,
            api_key=self.api_key,
        )
        latency = monotonic() - started
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError("LM Studio response has no choices", kind="invalid_response")
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        if not isinstance(message, dict):
            raise ProviderError("LM Studio choice has no message", kind="invalid_response")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("LM Studio returned empty assistant content", kind="empty_response", retryable=True)
        return ModelResponse(
            content=content,
            provider_id=self.provider_id,
            model_id=self.model,
            request_id=request_id or (payload.get("id") if isinstance(payload.get("id"), str) else None),
            usage=OpenAICompatibleProvider._usage(payload.get("usage")),
            latency_seconds=latency,
            raw_metadata={"finish_reason": first.get("finish_reason"), "structured_output": "json_schema"},
        )


ProviderFactory = Callable[[ModelConfig, SecretResolver], ModelProvider]


class ProviderRegistry:
    def __init__(self):
        self._factories: dict[str, ProviderFactory] = {}

    @classmethod
    def default(cls) -> "ProviderRegistry":
        registry = cls()
        registry.register("command", lambda config, resolver: CommandProvider(config))
        registry.register("openai-compatible", lambda config, resolver: OpenAICompatibleProvider(config, secret_resolver=resolver))
        registry.register("openai", lambda config, resolver: OpenAICompatibleProvider(config, secret_resolver=resolver))
        registry.register("ollama", lambda config, resolver: OllamaProvider(config, secret_resolver=resolver))
        registry.register("lm-studio", lambda config, resolver: LMStudioProvider(config, secret_resolver=resolver))
        return registry

    def register(self, provider_id: str, factory: ProviderFactory) -> None:
        key = provider_id.strip().lower()
        if not key or key in self._factories:
            raise ModelGatewayError(f"provider already registered or invalid: {provider_id!r}")
        self._factories[key] = factory

    def create(self, config: ModelConfig, resolver: SecretResolver) -> ModelProvider:
        factory = self._factories.get(config.provider)
        if factory is None:
            raise ModelGatewayError(f"unknown model provider: {config.provider}")
        return factory(config, resolver)

    def providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


class ModelGateway:
    """Provider-neutral model boundary compatible with LLMController.ModelAdapter."""

    def __init__(
        self,
        *,
        models: Mapping[str, ModelConfig],
        default_model: str,
        fallback_models: tuple[str, ...] = (),
        secret_resolver: SecretResolver | None = None,
        registry: ProviderRegistry | None = None,
        max_attempts_per_model: int = 2,
        retry_backoff_seconds: float = 0.25,
    ):
        self.models = dict(models)
        if default_model not in self.models:
            raise ModelGatewayError(f"default model alias is not configured: {default_model}")
        unknown_fallbacks = [name for name in fallback_models if name not in self.models]
        if unknown_fallbacks:
            raise ModelGatewayError("unknown fallback model aliases: " + ", ".join(unknown_fallbacks))
        if max_attempts_per_model < 1:
            raise ModelGatewayError("max_attempts_per_model must be at least 1")
        if retry_backoff_seconds < 0:
            raise ModelGatewayError("retry_backoff_seconds must be non-negative")
        self.default_model = default_model
        self.fallback_models = tuple(name for name in fallback_models if name != default_model)
        self.secret_resolver = secret_resolver or SecretResolver()
        self.registry = registry or ProviderRegistry.default()
        self.max_attempts_per_model = int(max_attempts_per_model)
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        self._providers: dict[str, ModelProvider] = {}
        self._telemetry = {
            "requests": 0,
            "failures": 0,
            "fallbacks": 0,
            "protocol_repairs": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_seconds": 0.0,
            "last_provider": None,
            "last_model": None,
            "last_request_id": None,
            "last_error_kind": None,
        }

    @classmethod
    def single_command(cls, command: str, *, timeout_seconds: float = 120.0) -> "ModelGateway":
        return cls(
            models={"command": ModelConfig(provider="command", command=command, timeout_seconds=timeout_seconds)},
            default_model="command",
            max_attempts_per_model=1,
        )

    def _provider(self, alias: str) -> ModelProvider:
        provider = self._providers.get(alias)
        if provider is None:
            provider = self.registry.create(self.models[alias], self.secret_resolver)
            self._providers[alias] = provider
        return provider

    def complete(self, *, system: str, user: str) -> str:
        base_request = ModelRequest(system=system, user=user)
        aliases = (self.default_model, *self.fallback_models)
        last_error: ProviderError | None = None
        for alias_index, alias in enumerate(aliases):
            if alias_index > 0:
                self._telemetry["fallbacks"] += 1
            provider = self._provider(alias)
            protocol_enforced = bool(getattr(provider, "protocol_enforced", False))
            request = base_request
            for attempt in range(self.max_attempts_per_model):
                self._telemetry["requests"] += 1
                try:
                    response = provider.complete(request)
                    content = _canonical_decision_json(response.content) if protocol_enforced else response.content
                except ProviderError as exc:
                    self._telemetry["failures"] += 1
                    self._telemetry["last_error_kind"] = exc.kind
                    last_error = exc
                    if protocol_enforced and exc.kind.startswith("protocol_") and attempt + 1 < self.max_attempts_per_model:
                        self._telemetry["protocol_repairs"] += 1
                        request = _repair_request(base_request, exc.kind)
                    elif not exc.retryable or attempt + 1 >= self.max_attempts_per_model:
                        break
                    if self.retry_backoff_seconds:
                        sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue

                self._telemetry["latency_seconds"] += float(response.latency_seconds)
                self._telemetry["last_provider"] = response.provider_id
                self._telemetry["last_model"] = response.model_id
                self._telemetry["last_request_id"] = response.request_id
                self._telemetry["last_error_kind"] = None
                if response.usage.input_tokens is not None:
                    self._telemetry["input_tokens"] += response.usage.input_tokens
                if response.usage.output_tokens is not None:
                    self._telemetry["output_tokens"] += response.usage.output_tokens
                if response.usage.total_tokens is not None:
                    self._telemetry["total_tokens"] += response.usage.total_tokens
                return content

        if last_error is not None:
            raise ModelGatewayError(
                f"all configured model routes failed; last={last_error.kind}: {last_error}"
            ) from last_error
        raise ModelGatewayError("all configured model routes failed")

    def telemetry_snapshot(self) -> dict[str, Any]:
        return dict(self._telemetry)

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "model-gateway-v2",
            "default_model": self.default_model,
            "fallback_models": list(self.fallback_models),
            "max_attempts_per_model": self.max_attempts_per_model,
            "registered_providers": list(self.registry.providers()),
            "local_protocol": {
                "providers": ["ollama", "lm-studio"],
                "structured_output": "decision-json-schema",
                "repair_scope": "gateway-only-one-retry-within-model-attempt-budget",
            },
            "models": {
                alias: {
                    "provider": config.provider,
                    "model": config.model,
                    "endpoint": config.endpoint,
                    "api_key": config.api_key.descriptor() if config.api_key else None,
                    "timeout_seconds": config.timeout_seconds,
                    "options": dict(config.options),
                }
                for alias, config in sorted(self.models.items())
            },
        }

    @property
    def revision(self) -> str:
        payload = json.dumps(
            self.descriptor(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return "model-gateway:" + hashlib.sha256(payload).hexdigest()