# Tool Spec

All harness tools return structured dictionaries and include a `truncated` field.

## File Tools

- `list_files(path, max_depth=4, ignore=None, budget=None)`
- `inspect_file(path, budget=None)`
- `grep_files(pattern, path, max_results=None, context_lines=2, ignore=None, budget=None)`
- `read_file_range(path, start_line, end_line, budget=None)`

File tools avoid reading binary files as text and include path, size, extension, and type hints where applicable. `grep_files` always ignores `.git`, `.codegraph`, `.harness_cache`, `__pycache__`, `.pytest_cache`, `node_modules`, `dist`, `build`, `.venv`, and `venv`; callers may pass additional ignore patterns. `read_file_range` reports both `truncated_by_budget` and `end_of_file_reached`.

## Archive Tools

- `inspect_archive(path, budget=None)`
- `safe_list_archive(path, budget=None)`

Archive tools list ZIP/TAR entries only, never extract by default, report total uncompressed size, largest entries, file count, and path traversal flags.

## Data Tools

- `inspect_csv(path, budget=None)`
- `inspect_json(path, budget=None)`
- `sample_rows(path, n=None, budget=None)`

Data tools return schema-like summaries and bounded samples. They do not dump full CSV or JSON content.
Large JSON files are inspected from a bounded prefix and marked `partial`. JSONL files are sampled line by line and marked partial when more lines exist beyond the sample.

## PDF and Web Tools

- `inspect_pdf(path, budget=None)`
- `search_pdf(path, query, budget=None)`
- `read_pdf_pages(path, pages, budget=None)`
- `search_web(query, max_results=None, budget=None)`
- `fetch_relevant_page(url, query=None, budget=None)`

PDF and web support is optional. Without configured support, these functions return structured unsupported results instead of fake data.

## Run Tools

- `run_python(script_path, args=None, timeout=30, budget=None)`
- `run_command(command, timeout=30, budget=None)`

Run tools enforce timeouts, truncate stdout/stderr, and block obvious destructive commands such as `rm -rf /`, `git reset --hard`, `git clean -fdx`, and `curl ... | sh`.
