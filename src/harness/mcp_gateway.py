from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from queue import Empty, Queue
from threading import Thread
from typing import Any, Mapping
import atexit
import json
import os
import re
import subprocess
import time

from harness import __version__
from harness.config import ConfigError, MCPServerConfig, SecretResolver
from harness.config_contracts import validate_mcp_server_contract
from harness.core.tools import SideEffect, ToolSpec


MODERN_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class MCPError(RuntimeError):
    pass


class MCPProtocolError(MCPError):
    pass


class MCPClientState(str, Enum):
    NEW = "new"
    STARTING = "starting"
    CONNECTED = "connected"
    BROKEN = "broken"
    CLOSED = "closed"


@dataclass(frozen=True)
class MCPToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    annotations: dict[str, Any]


class MCPStdioClient:
    """Minimal MCP stdio client with explicit lifecycle and fail-closed cleanup.

    Discovery/list operations may explicitly reconnect from BROKEN because they
    are observational. tools/call is never replayed automatically: a disconnect
    after dispatch has ambiguous side-effect status and must return to Harness
    recovery rather than risk duplicate execution.
    """

    def __init__(
        self,
        *,
        command: tuple[str, ...],
        environment: Mapping[str, str] | None = None,
        request_timeout_seconds: float = 15.0,
        probe_timeout_seconds: float = 2.0,
    ):
        if not command or any(not isinstance(arg, str) or not arg for arg in command):
            raise MCPError("MCP stdio command must contain non-empty argv strings")
        self.command = tuple(command)
        self.environment = dict(environment or {})
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.probe_timeout_seconds = float(probe_timeout_seconds)
        if self.request_timeout_seconds <= 0 or self.probe_timeout_seconds <= 0:
            raise MCPError("MCP timeouts must be positive")
        self.process: subprocess.Popen[str] | None = None
        self._messages: Queue[dict[str, Any]] = Queue()
        self._pending: dict[Any, dict[str, Any]] = {}
        self._reader: Thread | None = None
        self._next_id = 1
        self.protocol_version: str | None = None
        self.protocol_era: str | None = None
        self.server_info: dict[str, Any] | None = None
        self.state = MCPClientState.NEW
        self.last_failure: str | None = None
        self.reconnect_count = 0
        atexit.register(self.close)

    @staticmethod
    def _base_environment(extra: Mapping[str, str]) -> dict[str, str]:
        allowed = (
            "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR",
            "TMP", "TEMP", "LANG", "LC_ALL",
        )
        env = {key: os.environ[key] for key in allowed if key in os.environ}
        env.update({str(key): str(value) for key, value in extra.items()})
        return env

    def _reset_protocol_state(self) -> None:
        self.protocol_version = None
        self.protocol_era = None
        self.server_info = None
        self._pending.clear()
        self._messages = Queue()
        self._next_id = 1

    def _shutdown_process(self) -> None:
        process = self.process
        self.process = None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)

    def _mark_broken(self, exc: BaseException | str) -> None:
        self.last_failure = str(exc)
        self.state = MCPClientState.BROKEN
        self._shutdown_process()
        self._reset_protocol_state()

    def start(self) -> None:
        if self.state is MCPClientState.CLOSED:
            raise MCPError("MCP client is closed")
        if self.state is MCPClientState.BROKEN:
            raise MCPError("MCP client is broken; explicit safe reconnect is required")
        if self.process is not None and self.process.poll() is None:
            return
        self.state = MCPClientState.STARTING
        try:
            self.process = subprocess.Popen(
                list(self.command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=self._base_environment(self.environment),
                shell=False,
            )
        except OSError as exc:
            self._mark_broken(exc)
            raise MCPError(f"failed to start MCP stdio server: {exc}") from exc
        self._reader = Thread(target=self._reader_loop, name="mcp-stdio-reader", daemon=True)
        self._reader.start()

    def _reader_loop(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            text = line.strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self._messages.put(message)

    def heartbeat(self) -> bool:
        """Side-effect-free process-liveness heartbeat; not protocol health proof."""
        process = self.process
        alive = process is not None and process.poll() is None
        if self.state is MCPClientState.CONNECTED and not alive:
            self._mark_broken("MCP subprocess exited")
            return False
        return alive and self.state in {MCPClientState.STARTING, MCPClientState.CONNECTED}

    def _write(self, message: dict[str, Any]) -> None:
        self.start()
        process = self.process
        if process is None or process.stdin is None or process.poll() is not None:
            exc = MCPError("MCP stdio server is not running")
            self._mark_broken(exc)
            raise exc
        try:
            process.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self._mark_broken(exc)
            raise MCPError(f"MCP stdio write failed: {exc}") from exc

    def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        mark_broken_on_timeout: bool = True,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + float(timeout_seconds or self.request_timeout_seconds)
        message = self._pending.pop(request_id, None)
        while message is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                exc = TimeoutError(f"MCP request timed out: {method}")
                if mark_broken_on_timeout:
                    self._mark_broken(exc)
                raise exc
            try:
                candidate = self._messages.get(timeout=remaining)
            except Empty as exc:
                timeout = TimeoutError(f"MCP request timed out: {method}")
                if mark_broken_on_timeout:
                    self._mark_broken(timeout)
                raise timeout from exc
            candidate_id = candidate.get("id")
            if candidate_id == request_id:
                message = candidate
            elif candidate_id is not None:
                self._pending[candidate_id] = candidate
            # Notifications without an id are ignored by this minimal client.

        error = message.get("error")
        if isinstance(error, dict):
            raise MCPProtocolError(
                f"MCP {method} error {error.get('code')}: {error.get('message', '')}"
            )
        result = message.get("result")
        if not isinstance(result, dict):
            raise MCPProtocolError(f"MCP {method} response has no object result")
        return result

    @staticmethod
    def _modern_meta() -> dict[str, Any]:
        return {
            "io.modelcontextprotocol/protocolVersion": MODERN_PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientInfo": {
                "name": "verified-state-harness",
                "version": __version__,
            },
            "io.modelcontextprotocol/clientCapabilities": {},
        }

    def connect(self) -> None:
        if self.state is MCPClientState.CONNECTED and self.protocol_era is not None:
            if not self.heartbeat():
                raise MCPError("MCP connection is broken")
            return
        if self.state is MCPClientState.BROKEN:
            raise MCPError("MCP client is broken; reconnect_safe() is required")
        self.start()
        try:
            discover = self._request(
                "server/discover",
                {"_meta": self._modern_meta()},
                timeout_seconds=self.probe_timeout_seconds,
                # Modern-probe timeout is an expected legacy-negotiation path.
                mark_broken_on_timeout=False,
            )
        except (TimeoutError, MCPProtocolError):
            self._connect_legacy()
            self.state = MCPClientState.CONNECTED
            return

        supported = discover.get("supportedVersions", [])
        if not isinstance(supported, list) or MODERN_PROTOCOL_VERSION not in supported:
            self._connect_legacy()
            self.state = MCPClientState.CONNECTED
            return
        self.protocol_version = MODERN_PROTOCOL_VERSION
        self.protocol_era = "modern"
        meta = discover.get("_meta")
        if isinstance(meta, dict):
            info = meta.get("io.modelcontextprotocol/serverInfo")
            if isinstance(info, dict):
                self.server_info = dict(info)
        self.state = MCPClientState.CONNECTED
        self.last_failure = None

    def reconnect_safe(self) -> None:
        """Reconnect only for observational/discovery operations.

        This method never replays a tools/call request. Callers must decide
        separately whether a business/tool action is safe to issue again.
        """
        if self.state is MCPClientState.CLOSED:
            raise MCPError("closed MCP client cannot reconnect")
        if self.state is not MCPClientState.BROKEN:
            return
        self._shutdown_process()
        self._reset_protocol_state()
        self.state = MCPClientState.NEW
        self.reconnect_count += 1
        self.connect()

    def _connect_legacy(self) -> None:
        result = self._request(
            "initialize",
            {
                "protocolVersion": LEGACY_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "verified-state-harness", "version": __version__},
            },
        )
        negotiated = result.get("protocolVersion")
        if not isinstance(negotiated, str) or not negotiated:
            raise MCPProtocolError("legacy initialize response lacks protocolVersion")
        if negotiated > LEGACY_PROTOCOL_VERSION:
            raise MCPProtocolError(f"unexpected legacy protocol version: {negotiated}")
        self.protocol_version = negotiated
        self.protocol_era = "legacy"
        info = result.get("serverInfo")
        if isinstance(info, dict):
            self.server_info = dict(info)
        self._write({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        self.last_failure = None

    def _params(self, raw: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(raw or {})
        if self.protocol_era == "modern":
            params["_meta"] = self._modern_meta()
        return params

    def list_tools(
        self,
        *,
        max_pages: int = 20,
        max_tools: int = 512,
        reconnect_if_broken: bool = True,
    ) -> list[MCPToolDefinition]:
        if self.state is MCPClientState.BROKEN and reconnect_if_broken:
            self.reconnect_safe()
        self.connect()
        definitions: list[MCPToolDefinition] = []
        cursor: str | None = None
        try:
            for _ in range(max_pages):
                params: dict[str, Any] = {}
                if cursor is not None:
                    params["cursor"] = cursor
                result = self._request("tools/list", self._params(params))
                raw_tools = result.get("tools")
                if not isinstance(raw_tools, list):
                    raise MCPProtocolError("tools/list result requires a tools array")
                for raw in raw_tools:
                    if not isinstance(raw, dict):
                        raise MCPProtocolError("tools/list contains a non-object tool")
                    name = raw.get("name")
                    if not isinstance(name, str) or not _TOOL_NAME_RE.fullmatch(name):
                        raise MCPProtocolError(f"invalid MCP tool name: {name!r}")
                    input_schema = raw.get("inputSchema")
                    if not isinstance(input_schema, dict):
                        raise MCPProtocolError(f"MCP tool {name!r} lacks object inputSchema")
                    output_schema = raw.get("outputSchema")
                    if output_schema is not None and not isinstance(output_schema, dict):
                        raise MCPProtocolError(f"MCP tool {name!r} has invalid outputSchema")
                    annotations = raw.get("annotations")
                    definitions.append(MCPToolDefinition(
                        name=name,
                        description=str(raw.get("description", ""))[:4000],
                        input_schema=dict(input_schema),
                        output_schema=(dict(output_schema) if isinstance(output_schema, dict) else None),
                        annotations=(dict(annotations) if isinstance(annotations, dict) else {}),
                    ))
                    if len(definitions) > max_tools:
                        raise MCPProtocolError("MCP tool count exceeds configured bound")
                next_cursor = result.get("nextCursor")
                if next_cursor is None:
                    break
                if not isinstance(next_cursor, str) or not next_cursor:
                    raise MCPProtocolError("tools/list nextCursor must be a non-empty string")
                cursor = next_cursor
            else:
                raise MCPProtocolError("MCP tools/list pagination exceeds page bound")
        except (TimeoutError, BrokenPipeError, OSError) as exc:
            self._mark_broken(exc)
            raise MCPError(f"MCP tools/list connection failed: {exc}") from exc

        names = [item.name for item in definitions]
        if len(names) != len(set(names)):
            raise MCPProtocolError("MCP server returned duplicate tool names")
        return definitions

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        # Deliberately no reconnect_if_broken path here. A prior ambiguous tool
        # call must never be silently replayed after reconnect.
        self.connect()
        if not _TOOL_NAME_RE.fullmatch(name):
            raise MCPError("invalid MCP tool name")
        if not isinstance(arguments, dict):
            raise MCPError("MCP tool arguments must be an object")
        try:
            result = self._request(
                "tools/call",
                self._params({"name": name, "arguments": arguments}),
            )
        except (TimeoutError, BrokenPipeError, OSError) as exc:
            self._mark_broken(exc)
            raise MCPError(
                "MCP tools/call connection failed; execution outcome may be ambiguous and was not replayed: "
                + str(exc)
            ) from exc
        return {
            "content": result.get("content", []),
            "structured_content": result.get("structuredContent"),
            "is_error": bool(result.get("isError", False)),
            "protocol_version": self.protocol_version,
            "server_info": self.server_info,
        }

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "mcp-stdio-client-v2",
            "state": self.state.value,
            "protocol_version": self.protocol_version,
            "protocol_era": self.protocol_era,
            "server_info": dict(self.server_info or {}),
            "reconnect_count": self.reconnect_count,
            "last_failure": self.last_failure,
            "heartbeat": "process_liveness_only",
            "automatic_tool_replay": False,
        }

    def close(self) -> None:
        self._shutdown_process()
        self._reset_protocol_state()
        self.state = MCPClientState.CLOSED


class MCPGateway:
    """Discover MCP tools and normalize them into existing ActionRuntime specs."""

    def __init__(self, servers: tuple[MCPServerConfig, ...], *, secret_resolver: SecretResolver | None = None):
        self.servers = tuple(server for server in servers if server.enabled)
        for server in self.servers:
            validate_mcp_server_contract(server)
        self.secret_resolver = secret_resolver or SecretResolver()
        self.clients: dict[str, MCPStdioClient] = {}
        self._tool_specs: dict[str, ToolSpec] | None = None
        atexit.register(self.close)

    def _server_environment(self, config: MCPServerConfig) -> dict[str, str]:
        return {
            key: self.secret_resolver.resolve(ref) or ""
            for key, ref in config.env.items()
        }

    @staticmethod
    def _tool_policy(config: MCPServerConfig, tool_name: str) -> tuple[SideEffect, str, bool]:
        policies = config.options.get("tool_policies", {})
        raw = policies.get(tool_name, {}) if isinstance(policies, dict) else {}
        if not isinstance(raw, dict):
            raise ConfigError(f"MCP tool policy {config.name}.{tool_name} must be an object")
        side_raw = raw.get("side_effect", "external")
        try:
            side_effect = SideEffect(side_raw)
        except ValueError as exc:
            raise ConfigError(f"invalid MCP side_effect for {config.name}.{tool_name}: {side_raw!r}") from exc
        permission = str(raw.get("permission", "confirm"))
        if permission not in {"auto", "confirm", "deny"}:
            raise ConfigError(f"invalid MCP permission for {config.name}.{tool_name}: {permission!r}")
        idempotent = bool(raw.get("idempotent", False))
        return side_effect, permission, idempotent

    def _client(self, config: MCPServerConfig) -> MCPStdioClient:
        client = self.clients.get(config.name)
        if client is not None:
            return client
        request_timeout = float(config.options.get("request_timeout_seconds", 15.0))
        probe_timeout = float(config.options.get("probe_timeout_seconds", 2.0))
        client = MCPStdioClient(
            command=config.command,
            environment=self._server_environment(config),
            request_timeout_seconds=request_timeout,
            probe_timeout_seconds=probe_timeout,
        )
        self.clients[config.name] = client
        return client

    def discover_tools(self) -> dict[str, ToolSpec]:
        if self._tool_specs is not None:
            return dict(self._tool_specs)
        result: dict[str, ToolSpec] = {}
        for server in self.servers:
            client = self._client(server)
            for definition in client.list_tools():
                public_name = f"mcp.{server.name}.{definition.name}"
                if public_name in result:
                    raise MCPError(f"duplicate normalized MCP tool name: {public_name}")
                side_effect, permission, idempotent = self._tool_policy(server, definition.name)

                def invoke(_client=client, _name=definition.name, **arguments):
                    return _client.call_tool(_name, arguments)

                spec = ToolSpec(
                    name=public_name,
                    description=definition.description or f"MCP tool {definition.name} from {server.name}",
                    handler=invoke,
                    side_effect=side_effect,
                    idempotent=idempotent,
                    permission=permission,
                    postcondition=lambda out: isinstance(out, dict) and out.get("is_error") is False,
                    failure_modes=["mcp_protocol_error", "mcp_tool_error", "mcp_timeout", "mcp_disconnect"],
                    provenance={
                        "kind": "mcp",
                        "server": server.name,
                        "transport": server.transport,
                        "protocol": client.protocol_version or "unconnected",
                        "tool": definition.name,
                        "annotations_authority": "untrusted_hint",
                        "client_lifecycle": client.state.value,
                        "automatic_tool_replay": False,
                    },
                    input_schema=None,
                    output_schema=None,
                )
                spec.model_input_schema = definition.input_schema
                if definition.output_schema is not None:
                    spec.model_output_schema = definition.output_schema
                result[public_name] = spec
        self._tool_specs = result
        return dict(result)

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "mcp-gateway-v2",
            "servers": [
                {
                    "name": server.name,
                    "transport": server.transport,
                    "command": list(server.command),
                    "url": server.url,
                    "env": {key: ref.descriptor() for key, ref in sorted(server.env.items())},
                    "options": dict(server.options),
                    "client": self.clients[server.name].descriptor() if server.name in self.clients else None,
                }
                for server in self.servers
            ],
            "annotations_authority": "untrusted_hint",
            "default_tool_policy": {"side_effect": "external", "permission": "confirm", "idempotent": False},
            "host_environment": "minimal_allowlist_plus_explicit_secret_refs",
            "automatic_tool_replay": False,
            "strict_isolation_compatible": False,
        }

    def close(self) -> None:
        for client in list(self.clients.values()):
            client.close()
        self.clients.clear()
