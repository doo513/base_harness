# Verification

Verification is command-driven. A passing scaffold must prove both happy and failure paths.

## Strict Check

```bash
python3 scripts/validate_harness.py --strict
```

The strict check validates required paths, JSON/TOML parseability, repository metadata, state invariants, and hook fixture behavior.

## Harness Checks

```bash
python3 -m compileall harness
python3 -m unittest discover -s tests
```

These checks cover the implemented single-agent harness modules, bounded tools, packet building, trace records, and the end-to-end intake workflow.

## Hook Checks

Happy path:

```bash
python3 .codex/hooks/stop_guard.py --state tests/fixtures/task-state-valid.json
python3 .codex/hooks/user_prompt_submit.py --payload tests/fixtures/user-prompt-safe.json
python3 .codex/hooks/pre_tool_policy.py --payload tests/fixtures/hook-payload-safe.json
```

Failure path:

```bash
python3 .codex/hooks/stop_guard.py --state tests/fixtures/task-state-block-stop.json
python3 .codex/hooks/user_prompt_submit.py --payload tests/fixtures/user-prompt-secret.json
python3 .codex/hooks/pre_tool_policy.py --payload tests/fixtures/hook-payload-destructive.json
```

Expected failure tokens are `BLOCK_STOP`, `BLOCK_PROMPT`, and `BLOCK_TOOL`.
The successful Stop hook prints JSON on stdout, as required by Codex.

The PreToolUse fixtures use Codex-shaped payloads with `tool_name` and `tool_input.command`. `tests/fixtures/hook-payload-destructive-variants.json` covers wrapper, compound, and nested shell forms that the strict validator must reject.

## Trace

Workflow trace records are written as compact JSONL through `harness/core/trace.py`. They are for local debugging and handoff only; they are not an audit log and should not contain raw full tool outputs.
