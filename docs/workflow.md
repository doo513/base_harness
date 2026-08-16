# Problem-Responsive Workflow

Use this flow when a task includes a problem statement, attached files, archives, data, PDFs, logs, or web references.

1. Call `run_intake_workflow(user_request, workspace_path=".", provided_files=None)`.
2. The workflow runs `intake_request`, `classify_task`, and `tools_for_tasks`.
3. It performs safe bounded inspections: workspace listing, request-term grep for file-analysis tasks, provided-file metadata, line-range reads for text, data/archive/PDF checks where relevant, PDF search support checks, and structured unsupported web results when providers are missing.
4. It builds a compact packet with `build_context_packet`.
5. It appends compact trace records to `.harness_trace.jsonl`.
6. Reason from the packet, not from raw full files or tool outputs.

The workflow connects grep and search because they are bounded discovery tools. It does not automatically run `run_python` or `run_command` for `experiment` and `verification` labels; those tools remain selected next actions for the caller to invoke with an explicit bounded command.

Do not paste entire repositories, PDFs, web pages, CSVs, JSON files, archives, or logs into reasoning context. Use metadata, filtering, bounded snippets, source refs, and truncation markers.
