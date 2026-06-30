# Architecture

Base Harness is a single-agent, local-first MVP. Its job is to reduce raw user inputs and local files into a compact context packet before reasoning.

## Core Modules

- `harness/core/intake.py`: normalizes the user request, summarizes provided file paths, reports missing inputs, and recommends first tools.
- `harness/core/task_classifier.py`: assigns heuristic labels such as `file_analysis`, `data_inspection`, `archive_inspection`, `pdf_analysis`, `web_research`, `experiment`, `verification`, and `problem_adapter`.
- `harness/core/tool_router.py`: maps labels to initial tool names.
- `harness/core/workflow.py`: runs intake, classification, tool selection, bounded read-only discovery, packet building, and trace appends in one call.
- `harness/core/context_budget.py`: defines limits for tool result text, file lines, grep matches, samples, packet snippets, and source refs.
- `harness/core/packet.py`: builds a compact packet from tool summaries, bounded snippets, source refs, unknowns, and next actions.
- `harness/core/trace.py`: appends compact JSONL records with timestamps, status, duration, warnings, and truncation/support flags.

## Tool Modules

- `harness/tools/file_tools.py`: lists files, inspects metadata, greps with ignored directories, and reads line ranges without binary text reads.
- `harness/tools/data_tools.py`: inspects CSV, small JSON, large JSON prefixes, and JSONL samples without dumping full content.
- `harness/tools/archive_tools.py`: lists ZIP/TAR entries without extraction and flags traversal names.
- `harness/tools/pdf_tools.py`: returns structured unsupported results when PDF extraction is not configured.
- `harness/tools/web_tools.py`: returns structured unsupported results when search/fetch providers are not configured.
- `harness/tools/run_tools.py`: executes bounded commands and blocks obvious destructive shell forms.

## Flow

```text
user request + optional local files
  -> run_intake_workflow
  -> intake_request
  -> classify_task
  -> tools_for_tasks
  -> safe bounded inspections
  -> build_context_packet
  -> append_trace
```

The workflow performs local metadata and content-reduction steps, request-term grep, and configured/unsupported search checks. It does not spawn managed agents, create a vector store, run an MCP server, fabricate web results, fake PDF parsing, or automatically execute experiment commands.

## Packet And Trace

The context packet is the reasoning handoff. It includes:

- `task`
- `objective`
- `summary`
- bounded `source_refs`
- bounded `snippets`
- `unknowns`
- `next_actions`
- `truncated`

Trace JSONL is intentionally small. It records what was attempted and whether it completed, but it does not preserve raw full tool outputs.
