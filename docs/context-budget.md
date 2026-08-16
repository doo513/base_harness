# Context Budget

The problem-responsive harness enforces small, source-applied limits before Codex reasoning.

## Defaults

```python
max_tool_result_chars = 12000
max_file_read_lines = 160
max_grep_results = 50
max_pdf_pages_per_read = 3
max_web_results = 5
max_passages_per_page = 5
max_csv_sample_rows = 50
max_archive_list_entries = 300
max_packet_snippets = 5
max_source_refs = 20
```

`harness/core/context_budget.py` exposes `truncate_text` and `limit_items`. Both return the limited value, a `truncated` flag, the original count or length, and the returned count or length.

Truncated values include a marker such as:

```text
[Truncated: 25 elements omitted. Showing first 2 and last 2]
```

Tiny limits still obey the limit even if the marker itself must be shortened.

## Rule

Apply limits at the source. For example, `read_file_range` stops after `max_file_read_lines` lines instead of reading a full file and slicing afterward.

Packets also enforce their own limits. `build_context_packet` keeps bounded snippets and source refs only; it does not embed full raw tool outputs.
