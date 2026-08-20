# Windows TUI / Artifact Integrity Incident Report — 2026-08-20

Status: remediation implemented; repository CI PASS; native Windows replay recommended

## Summary

A Windows TUI run reached the tool-execution phase successfully but stopped during deterministic progress accounting. The run also exposed a separate TUI input-state leak after entering an API key.

Observed symptoms:

```text
Plan    ...
✕ Issue  progress evidence integrity failure: progress evidence artifact cannot be verified:
         artifact root cannot be opened: [Errno 13] Permission denied: 'C:\\...\\runs\\...\\artifacts'
↻ Retry  checkpoint_stop
● Tool   directory.list · .

❯ ************
```

These failures are Harness/TUI compatibility defects, not evidence that the selected LLM lacked filesystem/tool access.

## Incident A — secret prompt state leaked into normal conversation input

### Symptom

After an API key was entered, later normal `❯` prompts rendered user text as `********`.

### Root cause

The conversational TUI reused the same `prompt_toolkit.PromptSession` for both normal user input and secret input. `_prompt_secret()` invoked that long-lived session with `is_password=True`. The prompt configuration remained attached to the session and affected subsequent prompts.

### Impact

- normal task text became visually masked;
- the UI incorrectly looked as if the conversation itself were treated as a secret;
- usability and debuggability degraded;
- using the same long-lived session for secret and normal input created an unnecessary coupling between credential handling and conversation history.

### Remediation

`_prompt_secret()` now creates a dedicated short-lived password `PromptSession` and deliberately does not use the caller's long-lived conversation session. Normal conversation prompts therefore never switch into password mode.

Regression coverage verifies that the supplied conversation session is not invoked by secret input and that the isolated session uses `is_password=True`.

### Security property retained

Raw API-key values remain session-only and are not persisted to `harness.toml`.

## Incident B — Windows artifact verified-read path used POSIX directory-fd semantics

### Symptom

A successful `directory.list` tool observation was persisted, but progress accounting failed when it tried to re-read and verify the observation artifact:

```text
progress evidence artifact cannot be verified:
artifact root cannot be opened: [Errno 13] Permission denied: '...\\artifacts'
```

### Root cause

`ArtifactStore.verified_read_bytes_from_root()` used the POSIX hardening pattern:

```text
open artifact directory -> obtain dir_fd
open basename relative to dir_fd
reject symlinks where supported
fstat regular file
read exact bytes
hash exact bytes
```

Opening a directory as a file descriptor and using `dir_fd` is not portable to Windows. On Windows the directory open can fail with `PermissionError` even though the directory itself is accessible.

### Impact

The actual tool call succeeded and produced one observation, but Stage-06 progress accounting could not verify the content-addressed evidence and correctly failed closed. The run therefore stopped before verified completion.

The important classification is:

```text
tool execution             succeeded
observation persistence    succeeded
progress evidence re-read  failed on platform compatibility
```

This was not an Ollama/tool-access failure.

### Remediation

The POSIX descriptor-relative implementation remains unchanged for non-Windows platforms. Windows selects a portable verified-read implementation that:

1. resolves the opaque content-addressed artifact basename under the already-resolved artifact root;
2. rejects paths escaping the root;
3. rejects missing files, non-regular files, and symlink artifacts;
4. opens the resolved regular artifact directly in binary mode;
5. validates the opened handle as a regular file;
6. hashes the exact bytes returned;
7. compares the digest with the SHA-256 digest encoded in the artifact reference.

This restores the content-address integrity property on Windows. It does **not** claim that Windows provides the exact same descriptor-relative `O_NOFOLLOW` primitive used by the POSIX implementation; that platform difference is explicit in code and documentation.

Regression coverage directly exercises the portable verified-read helper and verifies both valid content and tamper rejection.

## Incident C — default TUI run state overlapped the actor workspace

### Symptom

The run directory was created as:

```text
C:\\...\\base_harness\\runs\\<timestamp>
```

while the actor workspace was:

```text
C:\\...\\base_harness
```

### Root cause

The TUI historically used `./runs/<timestamp>` as its default state location. With `strict_layout=False`, the security topology validator did not reject this overlap.

### Impact

This did not directly cause the Windows `PermissionError`, but it weakened the intended separation between actor-controlled workspace content and kernel-owned run/evidence state. It also made later strict-layout adoption harder.

### Remediation

The default TUI run root is now outside the current project:

- Windows: `%LOCALAPPDATA%\\base_harness\\runs` with a user-local fallback;
- POSIX: `$XDG_STATE_HOME/base_harness/runs` or `~/.local/state/base_harness/runs`;
- explicit override: `HARNESS_RUN_ROOT`.

An explicitly supplied run directory remains supported. Security policy remains kernel-owned; this change only makes the safer topology the default UX.

Regression coverage verifies that `_default_new_run_dir()` is rooted in the external user-state directory rather than the project workspace.

## Causal interpretation of the observed run

```text
LLM produced plan
  -> Harness accepted plan
  -> actor requested directory.list
  -> directory.list succeeded
  -> observation artifact was persisted
  -> progress controller attempted deterministic artifact verification
  -> Windows directory-fd open failed
  -> IntegrityError
  -> fail-closed recovery selected checkpoint_stop
  -> run stopped before completion
```

The model/tool path had already advanced beyond planning. This incident therefore must not be classified as a model inability to access the local workspace.

## Remediation commits

The remediation was split so each causal change remains auditable:

- `ad884738` — Windows portable artifact verified-read path
- `6ba2da2` — external default TUI run-state root
- `e23637a` — isolated secret prompt session
- `586e227` — portable artifact/secret-session regression coverage
- `9b0461e` — update the pre-existing run-dir regression expectation
- `fad9274` — update the TUI implementation document with causes and resulting behavior

## Verification result

Repository integration CI for source commit `fad92741e94e39600d3b916e0cdb173c7e56f0a1`:

```text
Result: PASS
306 passed, 7 skipped

compile                    PASS
cli/tui module + console   PASS
core-freeze-audit          PASS
Stage 02                   PASS
Stage 03                   PASS
Stage 04                   PASS
Stage 05                   PASS
Stage 06                   PASS
Stage 07                   PASS
Stage 08                   PASS
```

This is important because the artifact change touches shared core persistence/integrity code rather than only presentation code. Stage-03 resume, Stage-06 progress, and Stage-08 artifact-integrity gates remained green.

### Verification boundary

The repository CI runner for this result is `ubuntu-latest`. Therefore the evidence proves:

- the POSIX hardened path did not regress;
- the portable Windows-compatible helper is covered directly;
- content tampering is still rejected;
- TUI run-root behavior and secret-session isolation are covered;
- all existing core/stage regression gates remain green.

It does **not** substitute for one real Windows replay of the original failing scenario. A native Windows rerun is recommended to close the incident operationally:

```text
1. git pull origin main
2. reinstall editable package if needed
3. start verified-harness-tui
4. enter/switch an API-key model and confirm the next normal prompt is not masked
5. run a task that causes directory.list/file.read
6. confirm progress accounting continues past the first evidence artifact
7. confirm the run directory is under the user-local base_harness state root, not the project
```

If that replay succeeds, the original incident can be considered closed on the affected host.
