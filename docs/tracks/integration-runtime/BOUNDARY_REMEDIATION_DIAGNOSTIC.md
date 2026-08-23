# Boundary Remediation Diagnostic

- source: a76e676090746ff9718cba126d4808e252d26d4f
- stage: apply
- outcome: failure

## Proposed diff stat before reset
```text
```

## Apply log
```text
Traceback (most recent call last):
  File "/home/runner/work/base_harness/base_harness/scripts/apply_boundary_deep_remediation.py", line 17, in <module>
    main()
  File "/home/runner/work/base_harness/base_harness/scripts/apply_boundary_deep_remediation.py", line 13, in main
    runpy.run_path(str(applicator), run_name="__main__")
  File "<frozen runpy>", line 291, in run_path
  File "<frozen runpy>", line 98, in _run_module_code
  File "<frozen runpy>", line 88, in _run_code
  File "/home/runner/work/base_harness/base_harness/scripts/apply_p2_memory.py", line 65, in <module>
    main()
  File "/home/runner/work/base_harness/base_harness/scripts/apply_p2_memory.py", line 59, in main
    source = _decode_source(parts)
             ^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/base_harness/base_harness/scripts/apply_p2_memory.py", line 49, in _decode_source
    raise RuntimeError(
RuntimeError: P2 payload single-symbol recovery exhausted without matching source SHA-256
```
