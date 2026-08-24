from types import SimpleNamespace
import tomllib

import pytest

from harness.opencode_selection import (
    OpenCodeModelInfo,
    OpenCodeSelectionError,
    choose_opencode_model,
    configure_opencode_model,
    list_opencode_models,
    parse_opencode_models_verbose,
)


def _catalog_text():
    return '''opencode/free-model
{
  "name": "Free Model",
  "limit": {"context": 131072, "input": 120000, "output": 8192},
  "cost": {"input": 0, "output": 0}
}
opencode/paid-model
{
  "name": "Paid Model",
  "limit": {"context": 32768, "output": 4096},
  "cost": {"input": 1.5, "output": 4.0}
}
opencode/unknown-cost
{
  "name": "Unknown Cost",
  "limit": {"context": 65536}
}
'''


def test_parse_verbose_catalog_preserves_limits_and_only_marks_explicit_zero_cost_free():
    items = {item.ref: item for item in parse_opencode_models_verbose(_catalog_text())}

    free = items["opencode/free-model"]
    assert free.explicitly_free is True
    assert free.context_window == 131072
    assert free.input_limit == 120000
    assert free.output_limit == 8192
    assert free.cost_input == 0.0
    assert free.cost_output == 0.0

    paid = items["opencode/paid-model"]
    assert paid.explicitly_free is False
    assert paid.context_window == 32768

    unknown = items["opencode/unknown-cost"]
    assert unknown.explicitly_free is None
    assert unknown.cost_input is None
    assert unknown.cost_output is None


def test_list_models_uses_provider_verbose_refresh_and_shell_false(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=_catalog_text(), stderr="")

    monkeypatch.setattr("harness.opencode_selection.subprocess.run", fake_run)
    items = list_opencode_models(
        binary="opencode-test",
        provider="opencode",
        refresh=True,
        timeout_seconds=12,
    )

    assert [item.ref for item in items] == [
        "opencode/free-model",
        "opencode/paid-model",
        "opencode/unknown-cost",
    ]
    assert captured["argv"] == [
        "opencode-test", "models", "opencode", "--verbose", "--refresh"
    ]
    assert captured["shell"] is False
    assert captured["timeout"] == 12.0


def _free_model(ref="opencode/free-model"):
    provider, model_id = ref.split("/", 1)
    return OpenCodeModelInfo(
        ref=ref,
        provider=provider,
        model_id=model_id,
        name="Free Model",
        context_window=131072,
        input_limit=120000,
        output_limit=8192,
        cost_input=0.0,
        cost_output=0.0,
        explicitly_free=True,
        metadata={},
    )


def test_configure_selected_model_pins_model_and_catalog_metadata(tmp_path):
    path = tmp_path / "harness.toml"
    configure_opencode_model(
        path,
        model=_free_model(),
        alias="opencode",
        binary="opencode",
        agent="plan",
        timeout_seconds=240,
        make_default=True,
    )

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    route = data["models"]["opencode"]
    options = route["options"]

    assert data["default_model"] == "opencode"
    assert route["provider"] == "command"
    assert route["model"] == "opencode/free-model"
    assert "harness.opencode_adapter" in route["command"]
    assert "opencode/free-model" in route["command"]
    assert options["adapter"] == "opencode"
    assert options["context_window"] == 131072
    assert options["catalog_explicitly_free"] is True
    assert options["catalog_cost_input"] == 0.0
    assert options["catalog_cost_output"] == 0.0


def test_reselecting_opencode_model_replaces_same_route_without_duplicate_tables(tmp_path):
    path = tmp_path / "harness.toml"
    configure_opencode_model(path, model=_free_model("opencode/first"))
    configure_opencode_model(path, model=_free_model("opencode/second"))

    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert data["models"]["opencode"]["model"] == "opencode/second"
    assert text.count("[models.opencode]") == 1
    assert text.count("[models.opencode.options]") == 1
    assert "opencode/first" not in text


def test_open_code_alias_collision_with_non_adapter_route_fails_closed(tmp_path):
    path = tmp_path / "harness.toml"
    path.write_text(
        'default_model = "opencode"\n\n'
        '[models.opencode]\n'
        'provider = "openai-compatible"\n'
        'model = "other"\n'
        'endpoint = "https://example.invalid/v1"\n',
        encoding="utf-8",
    )

    with pytest.raises(OpenCodeSelectionError, match="non-OpenCode route"):
        configure_opencode_model(path, model=_free_model())


def test_choose_model_accepts_number_and_orders_explicit_free_first(capsys):
    items = parse_opencode_models_verbose(_catalog_text())
    answers = iter(["1"])
    selected = choose_opencode_model(items, prompt=lambda _: next(answers))

    assert selected.ref == "opencode/free-model"
    shown = capsys.readouterr().out
    assert "opencode/free-model" in shown
    assert "free" in shown
