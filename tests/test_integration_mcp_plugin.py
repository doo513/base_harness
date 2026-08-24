import json
import sys
import textwrap
import types

import pytest

from harness.config import ConfigError, MCPServerConfig, PluginConfig, harness_config_from_mapping
from harness.core.tools import ActionRuntime, SideEffect, ToolCall, ToolSpec
from harness.mcp_gateway import (
    MCPClientState,
    MCPError,
    MCPGateway,
    MCPStdioClient,
    MODERN_PROTOCOL_VERSION,
)
from harness.plugin_gateway import PluginError, PluginGateway
from harness.profile_composition import ProfileCompositionError, augment_profile_tools
from harness.profiles.software import SoftwareProfile


def _modern_server_script() -> str:
    return textwrap.dedent(
        f"""
        import json, sys
        MODERN = {MODERN_PROTOCOL_VERSION!r}
        for line in sys.stdin:
            msg = json.loads(line)
            method = msg.get('method')
            if method == 'server/discover':
                out = {{'jsonrpc':'2.0','id':msg['id'],'result':{{'supportedVersions':[MODERN], '_meta':{{'io.modelcontextprotocol/serverInfo':{{'name':'fake-modern','version':'1'}}}}}}}}
            elif method == 'tools/list':
                out = {{'jsonrpc':'2.0','id':msg['id'],'result':{{'tools':[{{
                    'name':'echo',
                    'description':'Echo input',
                    'inputSchema':{{'type':'object','properties':{{'text':{{'type':'string'}}}},'required':['text'],'additionalProperties':False}},
                    'annotations':{{'readOnlyHint':True,'destructiveHint':False}}
                }}]}}}}
            elif method == 'tools/call':
                text = msg.get('params',{{}}).get('arguments',{{}}).get('text','')
                out = {{'jsonrpc':'2.0','id':msg['id'],'result':{{'content':[{{'type':'text','text':text}}], 'structuredContent':{{'echo':text}}, 'isError':False}}}}
            else:
                if 'id' not in msg:
                    continue
                out = {{'jsonrpc':'2.0','id':msg['id'],'error':{{'code':-32601,'message':'not found'}}}}
            print(json.dumps(out), flush=True)
        """
    )


def _legacy_server_script() -> str:
    return textwrap.dedent(
        """
        import json, sys
        for line in sys.stdin:
            msg = json.loads(line)
            method = msg.get('method')
            if method == 'server/discover':
                continue
            if method == 'initialize':
                out = {'jsonrpc':'2.0','id':msg['id'],'result':{'protocolVersion':'2025-11-25','capabilities':{'tools':{}},'serverInfo':{'name':'fake-legacy','version':'1'}}}
            elif method == 'tools/list':
                out = {'jsonrpc':'2.0','id':msg['id'],'result':{'tools':[{'name':'echo','description':'Echo','inputSchema':{'type':'object'}}]}}
            else:
                if 'id' not in msg:
                    continue
                out = {'jsonrpc':'2.0','id':msg['id'],'error':{'code':-32601,'message':'not found'}}
            print(json.dumps(out), flush=True)
        """
    )


def test_mcp_modern_discovery_preserves_schema_and_uses_operator_policy():
    server = MCPServerConfig(
        name="fake",
        transport="stdio",
        command=(sys.executable, "-u", "-c", _modern_server_script()),
        options={
            "probe_timeout_seconds": 0.5,
            "request_timeout_seconds": 1.0,
            "tool_policies": {
                "echo": {"side_effect": "read", "permission": "auto", "idempotent": True}
            },
        },
    )
    gateway = MCPGateway((server,))
    try:
        tools = gateway.discover_tools()
        spec = tools["mcp.fake.echo"]
        assert spec.side_effect == SideEffect.READ
        assert spec.permission == "auto"
        assert spec.idempotent is True
        assert spec.input_schema is None
        assert spec.model_input_schema["required"] == ["text"]
        assert spec.provenance["annotations_authority"] == "untrusted_hint"

        result = ActionRuntime(tools).execute(ToolCall("mcp.fake.echo", {"text": "hello"}))
        assert result.ok is True
        assert result.output["structured_content"] == {"echo": "hello"}
        assert result.output["protocol_version"] == MODERN_PROTOCOL_VERSION
        client = gateway.clients["fake"]
        assert client.state is MCPClientState.CONNECTED
        assert client.heartbeat() is True
    finally:
        gateway.close()


def test_mcp_annotations_cannot_self_authorize_default_tool():
    server = MCPServerConfig(
        name="fake",
        transport="stdio",
        command=(sys.executable, "-u", "-c", _modern_server_script()),
        options={"probe_timeout_seconds": 0.5, "request_timeout_seconds": 1.0},
    )
    gateway = MCPGateway((server,))
    try:
        spec = gateway.discover_tools()["mcp.fake.echo"]
        assert spec.side_effect == SideEffect.EXTERNAL
        assert spec.permission == "confirm"
        result = ActionRuntime({spec.name: spec}).execute(ToolCall(spec.name, {"text": "x"}))
        assert result.ok is False
        assert result.approval_required is True
    finally:
        gateway.close()


def test_mcp_stdio_falls_back_to_legacy_initialize():
    client = MCPStdioClient(
        command=(sys.executable, "-u", "-c", _legacy_server_script()),
        request_timeout_seconds=1.0,
        probe_timeout_seconds=0.05,
    )
    try:
        tools = client.list_tools()
        assert client.protocol_era == "legacy"
        assert client.protocol_version == "2025-11-25"
        assert client.state is MCPClientState.CONNECTED
        assert tools[0].name == "echo"
    finally:
        client.close()
    assert client.state is MCPClientState.CLOSED


def test_mcp_broken_state_requires_safe_reconnect_and_never_replays_tool_call():
    client = MCPStdioClient(
        command=(sys.executable, "-u", "-c", _modern_server_script()),
        request_timeout_seconds=0.2,
        probe_timeout_seconds=0.1,
    )
    client._mark_broken("synthetic disconnect")
    with pytest.raises(MCPError, match="reconnect"):
        client.call_tool("echo", {"text": "x"})
    assert client.state is MCPClientState.BROKEN
    client.reconnect_safe()
    assert client.state is MCPClientState.CONNECTED
    assert client.reconnect_count == 1
    client.close()


def test_mcp_config_rejects_declared_but_unimplemented_transport_before_start():
    server = MCPServerConfig(name="remote", transport="http", url="https://example.invalid/mcp")
    with pytest.raises(ConfigError, match="not implemented"):
        MCPGateway((server,))


def test_plugin_gateway_only_loads_explicit_enabled_module(monkeypatch):
    module = types.ModuleType("fake_harness_plugin")
    module.harness_plugin = lambda *, options: {
        "name": "fake",
        "version": "1.0",
        "tools": {
            "echo": ToolSpec(
                name="echo",
                description="Echo",
                handler=lambda text: {"text": text},
                side_effect=SideEffect.READ,
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
            )
        },
    }
    monkeypatch.setitem(sys.modules, "fake_harness_plugin", module)

    disabled = PluginGateway((PluginConfig(name="fake", module="fake_harness_plugin", enabled=False),))
    assert disabled.discover_tools() == {}

    enabled = PluginGateway((PluginConfig(name="fake", module="fake_harness_plugin"),))
    tools = enabled.discover_tools()
    assert "plugin.fake.echo" in tools
    result = ActionRuntime(tools).execute(ToolCall("plugin.fake.echo", {"text": "ok"}))
    assert result.ok is True
    assert result.output == {"text": "ok"}
    assert enabled.descriptor()["host_process_import"] is True
    assert enabled.descriptor()["strict_isolation_compatible"] is False


def test_plugin_options_require_static_contract_before_factory_consumes_them(monkeypatch):
    seen = []
    module = types.ModuleType("contracted_plugin")
    module.harness_plugin_contract = lambda: {"allowed_options": ["mode"]}
    module.harness_plugin = lambda *, options: seen.append(dict(options)) or {
        "name": "contracted",
        "version": "1",
    }
    monkeypatch.setitem(sys.modules, "contracted_plugin", module)

    gateway = PluginGateway((
        PluginConfig(name="contracted", module="contracted_plugin", options={"mode": "safe"}),
    ))
    gateway.discover_tools()
    assert seen == [{"mode": "safe"}]

    bad = PluginGateway((
        PluginConfig(name="contracted", module="contracted_plugin", options={"surprise": True}),
    ))
    with pytest.raises(PluginError, match="unsupported plugin options"):
        bad.discover_tools()
    assert seen == [{"mode": "safe"}]


def test_plugin_manifest_identity_and_profile_composition_fail_closed(monkeypatch, tmp_path):
    module = types.ModuleType("bad_harness_plugin")
    module.harness_plugin = lambda *, options: {"name": "other", "version": "1"}
    monkeypatch.setitem(sys.modules, "bad_harness_plugin", module)
    with pytest.raises(PluginError):
        PluginGateway((PluginConfig(name="expected", module="bad_harness_plugin"),)).discover_tools()

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    original_type = type(profile)
    extra = ToolSpec(
        name="extra",
        description="extra",
        handler=lambda: {},
        side_effect=SideEffect.READ,
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={"type": "object"},
    )
    composed = augment_profile_tools(profile, {"extra": extra})
    assert type(composed) is original_type
    assert type(profile) is original_type
    assert "extra" not in profile.tools()
    assert "input_schema_hash" in composed.tools()["extra"].provenance

    leaked = composed.tools()["extra"]
    leaked.provenance["tamper"] = True
    assert "tamper" not in composed.tools()["extra"].provenance

    another = SoftwareProfile(workspace=workspace, acceptance_commands=["false"])
    with pytest.raises(ProfileCompositionError):
        augment_profile_tools(another, {"shell": extra})


def test_config_rejects_unknown_extension_keys_and_non_boolean_enable():
    with pytest.raises(ConfigError):
        harness_config_from_mapping({
            "mcp": [{"name": "x", "transport": "stdio", "command": ["x"], "enabled": "yes"}]
        })
    with pytest.raises(ConfigError):
        harness_config_from_mapping({
            "plugins": [{"name": "x", "module": "m", "surprise": True}]
        })
