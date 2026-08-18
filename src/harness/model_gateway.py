from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic, sleep
from typing import Any, Callable, Mapping, Protocol
import hashlib
import json
import shlex
import subprocess
import urllib.error
import urllib.request

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
        for key in ("temperature", "max_tokens", "top_p"):
            if key in self.options:
                body[key] = self.options[key]
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key is not None:
            headers["Authorization"] = f"Bearer {self.api_key}"
        http_request = urllib.request.Request(self.endpoint, data=data, headers=headers, method="POST")
        started = monotonic()
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                request_id = response.headers.get("x-request-id")
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")[-2000:]
            except Exception:
                detail = ""
            retryable = exc.code == 429 or 500 <= exc.code < 600
            kind = "rate_limit" if exc.code == 429 else "http_error"
            raise ProviderError(
                f"provider HTTP {exc.code}: {detail}",
                kind=kind,
                retryable=retryable,
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"provider connection failed: {exc}", kind="network_error", retryable=True) from exc
        except TimeoutError as exc:
            raise ProviderError("provider request timed out", kind="timeout", retryable=True) from exc
        latency = monotonic() - started

        if not isinstance(payload, dict):
            raise ProviderError("provider response must be a JSON object", kind="invalid_response")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError("provider response has no choices", kind="invalid_response")
        first = choices[0]
        if not isinstance(first, dict) or not isinstance(first.get("message"), dict):
            raise ProviderError("provider choice has no message", kind="invalid_response")
        content = first["message"].get("content")
        if not isinstance(content, str):
            raise ProviderError("provider message content must be a string", kind="invalid_response")
        return ModelResponse(
            content=content,
            provider_id=self.provider_id,
            model_id=self.model,
            request_id=request_id or (payload.get("id") if isinstance(payload.get("id"), str) else None),
            usage=self._usage(payload.get("usage")),
            latency_seconds=latency,
            raw_metadata={"finish_reason": first.get("finish_reason")},
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
        request = ModelRequest(system=system, user=user)
        aliases = (self.default_model, *self.fallback_models)
        last_error: ProviderError | None = None
        for alias_index, alias in enumerate(aliases):
            if alias_index > 0:
                self._telemetry["fallbacks"] += 1
            provider = self._provider(alias)
            for attempt in range(self.max_attempts_per_model):
                self._telemetry["requests"] += 1
                try:
                    response = provider.complete(request)
                except ProviderError as exc:
                    self._telemetry["failures"] += 1
                    self._telemetry["last_error_kind"] = exc.kind
                    last_error = exc
                    if not exc.retryable or attempt + 1 >= self.max_attempts_per_model:
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
                return response.content
        if last_error is not None:
            raise ModelGatewayError(
                f"all configured model routes failed; last={last_error.kind}: {last_error}"
            ) from last_error
        raise ModelGatewayError("all configured model routes failed")

    def telemetry_snapshot(self) -> dict[str, Any]:
        return dict(self._telemetry)

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "model-gateway-v1",
            "default_model": self.default_model,
            "fallback_models": list(self.fallback_models),
            "max_attempts_per_model": self.max_attempts_per_model,
            "registered_providers": list(self.registry.providers()),
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
