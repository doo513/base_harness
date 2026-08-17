# Benchmark Fixtures

This directory is reserved for reproducible P0 benchmark task fixtures and run outputs.

A benchmark should compare the same task under at least two modes:

- `baseline`: model/session without the Base Harness meta loop
- `harness`: the same model/session with the Base Harness path enabled

Use `harness.core.benchmark.BenchmarkRecord` for normalized records. Keep benchmark task inputs stable and avoid changing the problem set between compared runs.

Recommended minimum fields are already represented in `BenchmarkRecord`: success, elapsed time, tool calls, files read, commands run, retries, verification attempts, context size, and final-result validity.

Do not commit secrets or machine-specific absolute paths in benchmark artifacts.
