# Base Harness Plugin

This local plugin packages the five repository skills from `.agents/skills/` for reuse in Codex.

It does not publish, install, or trust hooks automatically. Validate the package from the repository root:

```bash
python3 scripts/validate_harness.py --plugin-only
```

