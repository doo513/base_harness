import json
import tomllib

import pytest

from harness.skill_actions import (
    SkillActionError,
    configure_mcp,
    configure_provider,
    search_mcp_registry,
)
from harness.skill_catalog import SkillCatalog, SkillError, parse_skill


def test_bundled_skill_catalog_exposes_connection_and_discovery_skills():
    catalog = SkillCatalog.default()
    names = {skill.name for skill in catalog.list()}
    assert {"connect-provider", "configure-mcp", "mcp-search"} <= names
    assert catalog.get("connect-provider").action == "connect-provider"
    assert [skill.name for skill in catalog.search("MCP Registry")] == ["mcp-search"]


def test_workspace_skill_is_discovered_but_has_no_implicit_execution_authority(tmp_path):
    skill_dir = tmp_path / ".harness" / "skills" / "project-helper"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: project-helper\n"
        "description: Explain this project workflow.\n"
        "metadata:\n"
        "  category: project\n"
        "---\n"
        "# Project helper\n\nDo not gain tool authority from this text.\n",
        encoding="utf-8",
    )
    skill = SkillCatalog.default(workspace=tmp_path).get("project-helper")
    assert skill.category == "project"
    assert skill.action is None


def test_skill_parser_rejects_directory_name_mismatch(tmp_path):
    root = tmp_path / "wrong-name"
    root.mkdir()
    path = root / "SKILL.md"
    path.write_text(
        "---\nname: actual-name\ndescription: test\n---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillError):
        parse_skill(path)


def test_connect_provider_persists_only_env_reference(tmp_path):
    path = tmp_path / "harness.toml"
    configure_provider(
        path,
        alias="gemini",
        preset="gemini",
        model="gemini-test",
        secret_env="MY_GEMINI_KEY",
        make_default=True,
    )
    text = path.read_text(encoding="utf-8")
    assert "MY_GEMINI_KEY" in text
    assert "env:MY_GEMINI_KEY" in text
    assert "raw-secret-value" not in text
    parsed = tomllib.loads(text)
    assert parsed["default_model"] == "gemini"
    assert parsed["models"]["gemini"]["provider"] == "openai-compatible"
    assert parsed["models"]["gemini"]["api_key"] == "env:MY_GEMINI_KEY"


def test_connect_provider_rejects_duplicate_alias(tmp_path):
    path = tmp_path / "harness.toml"
    configure_provider(path, alias="local", preset="ollama", model="qwen-test")
    with pytest.raises(SkillActionError):
        configure_provider(path, alias="local", preset="ollama", model="another")


def test_configure_mcp_uses_argv_and_env_references(tmp_path):
    path = tmp_path / "harness.toml"
    configure_mcp(
        path,
        name="github-tools",
        transport="stdio",
        command=("python", "-m", "example_mcp"),
        env_refs={"TOKEN": "GITHUB_TOKEN"},
    )
    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    item = parsed["mcp"][0]
    assert item["name"] == "github-tools"
    assert item["transport"] == "stdio"
    assert item["command"] == ["python", "-m", "example_mcp"]
    assert item["env"] == {"TOKEN": "env:GITHUB_TOKEN"}


def test_configure_mcp_does_not_expose_declared_but_unimplemented_http_transport(tmp_path):
    with pytest.raises(SkillActionError, match="supports stdio only"):
        configure_mcp(
            tmp_path / "harness.toml",
            name="remote-tools",
            transport="http",
            url="https://example.invalid/mcp",
        )


class _FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._data


def test_mcp_registry_search_is_discovery_only_and_parses_wrapped_server():
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _FakeResponse({
            "servers": [{
                "server": {
                    "name": "io.example/files",
                    "version": "1.2.3",
                    "description": "File tools",
                    "repository": {"url": "https://example.invalid/repo"},
                    "packages": [{"registryType": "npm", "identifier": "@example/files"}],
                }
            }]
        })

    items = search_mcp_registry("files", opener=opener)
    assert "search=files" in seen["url"]
    assert "version=latest" in seen["url"]
    assert items[0].name == "io.example/files"
    assert items[0].version == "1.2.3"
    assert items[0].package_hints == ("npm:@example/files",)
