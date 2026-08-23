# Boundary Remediation Diagnostic

- source: 5060a262759886dbaabe03d8c1c59ddd325f5153
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
  File "/home/runner/work/base_harness/base_harness/scripts/apply_p2_memory.py", line 29, in <module>
    main()
  File "/home/runner/work/base_harness/base_harness/scripts/apply_p2_memory.py", line 18, in main
    source = lzma.decompress(base64.b64decode(encoded)).decode("utf-8")
                             ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/base64.py", line 88, in b64decode
    return binascii.a2b_base64(s, strict_mode=validate)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
binascii.Error: Incorrect padding
```
