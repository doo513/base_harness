from __future__ import annotations

from typing import Iterable

from prompt_toolkit.completion import Completion

from harness import tui_conversation as conversation
from harness import tui_visual as legacy
from harness.opencode_selection import (
    OpenCodeModelInfo,
    OpenCodeSelectionError,
    configure_opencode_model,
    list_opencode_models,
)


_ORIGINAL_MODELS = legacy._models
_ORIGINAL_COMPLETER = conversation._ConversationCompleter
_INSTALLED = False


def _model_sort_key(item: OpenCodeModelInfo):
    return (
        0 if item.explicitly_free is True else 1 if item.explicitly_free is None else 2,
        item.ref,
    )


def _render_catalog(items: Iterable[OpenCodeModelInfo]) -> list[OpenCodeModelInfo]:
    ordered = sorted(items, key=_model_sort_key)
    legacy._emit(("class:assistant", "OpenCode models"))
    explicitly_free = sum(item.explicitly_free is True for item in ordered)
    if explicitly_free:
        legacy._emit(
            ("class:muted", "  explicitly free models are shown first · "),
            ("class:good", f"{explicitly_free} free"),
        )
    else:
        legacy._print_note(
            "No model was explicitly marked free by the current catalog metadata; missing cost is not treated as free."
        )
    for index, item in enumerate(ordered, start=1):
        if item.explicitly_free is True:
            marker = "FREE"
            cls = "class:good"
        elif item.explicitly_free is False:
            marker = "paid"
            cls = "class:muted"
        else:
            marker = "cost ?"
            cls = "class:warn"
        context = f" · ctx {item.context_window}" if item.context_window else ""
        name = f" · {item.name}" if item.name and item.name != item.ref else ""
        legacy._emit(
            (cls, f"  {index:>2}. {item.ref}"),
            ("class:muted", f" · {marker}{context}{name}"),
        )
    return ordered


def _choose_from_session(state, session, argument: str) -> OpenCodeModelInfo | None:
    tokens = argument.strip().split()
    refresh = any(token in {"refresh", "--refresh"} for token in tokens[1:])
    requested_ref = next(
        (token for token in tokens if token.startswith("opencode/") and token != "opencode"),
        None,
    )
    try:
        items = list_opencode_models(
            binary="opencode",
            provider="opencode",
            refresh=refresh,
        )
    except OpenCodeSelectionError as exc:
        legacy._print_error(str(exc))
        return None

    ordered = _render_catalog(items)
    if requested_ref:
        selected = next((item for item in ordered if item.ref == requested_ref), None)
        if selected is None:
            legacy._print_error(f"OpenCode catalog does not contain {requested_ref}")
            return None
        return selected

    current_data = legacy._config_data(state.config)
    current_models = current_data.get("models") if isinstance(current_data.get("models"), dict) else {}
    current_route = current_models.get("opencode") if isinstance(current_models, dict) else None
    current_ref = current_route.get("model") if isinstance(current_route, dict) else None
    default_index = 1
    if isinstance(current_ref, str):
        for index, item in enumerate(ordered, start=1):
            if item.ref == current_ref:
                default_index = index
                break

    while True:
        raw = legacy._prompt_text(session, "OpenCode model number or provider/model", str(default_index))
        if raw in {item.ref for item in ordered}:
            return next(item for item in ordered if item.ref == raw)
        try:
            index = int(raw)
        except ValueError:
            legacy._print_error("Enter a displayed number or exact provider/model id.")
            continue
        if 1 <= index <= len(ordered):
            return ordered[index - 1]
        legacy._print_error("Model number is outside the displayed range.")


def _models_with_opencode(state, session, argument: str = "") -> None:
    requested = argument.strip()
    if requested == "opencode" or requested.startswith("opencode/") or requested.startswith("opencode "):
        selected = _choose_from_session(state, session, requested)
        if selected is None:
            return
        try:
            configure_opencode_model(
                state.config,
                model=selected,
                alias="opencode",
                binary="opencode",
                timeout_seconds=240,
                make_default=True,
            )
        except OpenCodeSelectionError as exc:
            legacy._print_error(f"OpenCode model was not saved: {exc}")
            return
        free_text = " · explicitly free" if selected.explicitly_free is True else ""
        legacy._print_good(f"Using OpenCode · {selected.ref}{free_text} · saved to TOML")
        return
    _ORIGINAL_MODELS(state, session, argument)


class _OpenCodeCompleter(_ORIGINAL_COMPLETER):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/model ") or text.startswith("/models ") or text.startswith("/change "):
            _, fragment = text.split(" ", 1)
            if "opencode".startswith(fragment) and "opencode" not in legacy._configured_models(self.state.config):
                yield Completion(
                    "opencode",
                    start_position=-len(fragment),
                    display_meta="Browse OpenCode model catalog",
                )
        yield from super().get_completions(document, complete_event)


def install_opencode_model_selector() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    legacy._models = _models_with_opencode
    conversation._ConversationCompleter = _OpenCodeCompleter
    conversation._COMMAND_DESCRIPTIONS["/model"] = "Switch model; use /model opencode to browse OpenCode"
    conversation._COMPAT_COMMAND_DESCRIPTIONS["/models"] = "Alias for /model; /models opencode browses OpenCode"
    _INSTALLED = True


def main(argv: list[str] | None = None) -> int:
    install_opencode_model_selector()
    return conversation.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
