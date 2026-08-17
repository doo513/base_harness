# Base Harness

Base Harness is a small single-agent MVP for turning a user request and local problem files into a bounded context packet. It keeps the implementation local and deterministic: intake, task classification, safe inspections, context budgeting, packet building, and compact trace records.

## What Is Included

- `harness/core/intake.py` for request intake and provided-file summaries.
- `harness/core/task_classifier.py` and `harness/core/tool_router.py` for heuristic task labels and initial tool choices.
- `harness/core/workflow.py` for the end-to-end intake workflow.
- `harness/core/context_budget.py` for shared limits on tool output, snippets, source refs, and samples.
- `harness/core/packet.py` for compact context packets with summaries, snippets, source refs, unknowns, and next actions.
- `harness/core/trace.py` for small JSONL trace records.
- `harness/tools/` for bounded local file, archive, data, PDF, web, and command helpers.
- `tests/` for unit and workflow coverage.
- `scripts/validate_harness.py` for repository validation.

The MVP stays local and deterministic. It does not include a vector database, managed worker runtime, fake MCP server, or external orchestration layer.

## Closed-Loop Meta Layer

The repository also contains a deterministic meta layer for the next harness stages:

- `harness/core/contracts.py`: loop stages, success criteria, typed evidence, actions, observations, and verification results.
- `harness/core/verification.py`: completion checks based on verified evidence rather than evidence presence alone.
- `harness/core/execution.py`: normalization from existing tool results into loop observations without equating tool success with semantic success.
- `harness/core/orchestrator.py`: injectable `Context -> Reason -> Act -> Observe -> Verify` loop around `run_intake_workflow()`.
- `harness/core/benchmark.py`: baseline/harness benchmark records and comparison summaries.

The orchestrator deliberately does not embed an LLM provider or unrestricted command runner. A reasoner, executor, and optional semantic verifier are injected explicitly, so the meta layer remains deterministic and testable while later stages can connect real providers safely.

The development priority and rationale are recorded in `docs/base-harness-priority-roadmap.md`.

## Day 1 Commands

Validate the harness:

```bash
python3 -m compileall harness
python3 -m unittest discover -s tests
python3 scripts/validate_harness.py --strict
```

Run the problem-responsive workflow from Python:

```python
from harness.core.workflow import run_intake_workflow

result = run_intake_workflow(
    "Inspect the problem statement and input format",
    workspace_path=".",
    provided_files=["problem.md", "input.jsonl"],
)

packet = result["packet"]
trace_path = result["trace_path"]
```

## Architecture

The workflow is:

```text
request + optional files
  -> intake
  -> task classification
  -> initial tool selection
  -> safe bounded local discovery
  -> context packet
  -> compact trace JSONL
```

Tools apply limits before returning data. Files are listed with default cache/build directories ignored, request-term grep results are capped, text reads are line-bounded, CSV/JSON/JSONL inspection returns schema-like samples, archives are listed without extraction, and PDF/web helpers return structured unsupported results unless real support is configured. Command tools are available as explicit calls, but the intake workflow does not run experiment commands automatically.

The packet contains only summaries, bounded snippets, source refs, unknowns, and next actions. It does not embed full raw tool outputs.
