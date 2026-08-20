---
name: connect-provider
description: Configure an LLM provider route in harness.toml using a provider preset, model, endpoint, and environment-secret reference. Use when connecting Gemini, OpenAI, OpenAI-compatible APIs, or local Ollama.
compatibility: Verified-State Harness TUI; raw API keys are never written to TOML.
metadata:
  harness-action: connect-provider
  category: connection
---
# Connect provider

Use this skill when the user needs to add or change a model connection.

The skill writes provider/model/endpoint configuration to `harness.toml` and stores only an `env:VARIABLE_NAME` reference for secrets. It does not persist the secret value itself.

Supported presets currently match the Model Gateway capabilities:

- Gemini through Google's OpenAI-compatible endpoint
- OpenAI
- Generic OpenAI-compatible endpoint
- Local Ollama

If the referenced environment variable is not available, configure it in the operating system, shell, CI, or external secret manager before starting the run.
