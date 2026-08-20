# Windows TUI / Artifact Integrity Incident Report — 2026-08-20

Status: remediation in progress

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

Use a dedicated secret-only `PromptSession` with no conversation history. Normal conversation prompts never switch into password mode.

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

### Remediation

Keep the existing descriptor-relative verified-read implementation on platforms that support it. Add a Windows/path-based verified-read implementation that:

1. resolves the opaque content-addressed artifact basename under the already-resolved artifact root;
2. rejects paths escaping the root;
3. rejects missing files, non-regular files, and symlink artifacts;
4. opens the resolved artifact directly in binary mode;
5. hashes the exact bytes returned;
6. compares the digest with the digest encoded in the artifact reference.

This restores cross-platform operation without weakening the content-address integrity check.

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

This does not directly cause the Windows `PermissionError`, but it weakens the intended separation between actor-controlled workspace content and kernel-owned run/evidence state. It also makes later strict-layout adoption harder.

### Remediation

The default TUI run root is moved outside the current project:

- Windows: `%LOCALAPPDATA%\\base_harness\\runs` (fallback: user-local state directory)
- POSIX: `$XDG_STATE_HOME/base_harness/runs` or `~/.local/state/base_harness/runs`

An explicitly supplied run directory remains supported. Security policy remains kernel-owned; this change only makes the safe topology the default UX.

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

The important distinction is that the model/tool path had already advanced beyond planning. This incident therefore must not be classified as an Ollama/model inability to access the local workspace.

## Expected verification

Remediation is considered complete only when all of the following pass:

- ordinary prompt is visible after a secret prompt;
- secret prompt remains masked and is not placed in conversation history;
- Windows/path-based artifact verified-read accepts a valid content-addressed artifact;
- tampered artifact bytes are rejected;
- symlink/non-regular artifact paths are rejected where the platform exposes those concepts;
- default TUI run directory does not overlap a project workspace;
- existing POSIX descriptor-relative artifact verification tests continue to pass;
- full integration/runtime CI remains green.
