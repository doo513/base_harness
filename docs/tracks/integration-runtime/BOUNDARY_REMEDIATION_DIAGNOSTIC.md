# Boundary Remediation Diagnostic

- source: 4ce38f12cd3054a4dae16c9612d947f33595700f
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
  File "/home/runner/work/base_harness/base_harness/scripts/apply_p2_memory.py", line 32, in <module>
    main()
  File "/home/runner/work/base_harness/base_harness/scripts/apply_p2_memory.py", line 21, in main
    source = lzma.decompress(base64.b64decode(encoded)).decode("utf-8")
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/lzma.py", line 343, in decompress
    res = decomp.decompress(data)
          ^^^^^^^^^^^^^^^^^^^^^^^
_lzma.LZMAError: Corrupt input data
```
