---
type: Concept
title: Local LLM provider
description: A Hermes model provider backed by a local or self-hosted OpenAI-compatible endpoint, such as Ollama, vLLM, SGLang, or a DGX Spark model service. Provider setup is remote host state
resource: repo://hermes-workspace/knowledge/concepts/local-llm-provider.md
tags: [hermes, concept]
timestamp: 2026-06-27T00:00:00+09:00
source_path: CONTEXT.md
---

# Local LLM provider

A Hermes model provider backed by a local or self-hosted OpenAI-compatible endpoint, such as Ollama, vLLM, SGLang, or a DGX Spark model service. Provider setup is remote host state and should be verified through endpoint reachability, exact model name, API compatibility mode, context length, and tool/reasoning parser settings where applicable.
_Avoid_: committing provider config dumps, exposing model servers externally by default, assuming the control host loopback is visible from a separate Hermes host
