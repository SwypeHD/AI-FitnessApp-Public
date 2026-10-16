# ADR-0001: Hexagonal (Ports & Adapters) Architecture

**Status:** Accepted  
**Date:** 2026-06-04

## Context

The app needs to support multiple LLM providers (Ollama/Gemma locally, Anthropic Claude via API), multiple persistence backends (JSON files now, potentially a database later), and must remain testable without network dependencies.

## Decision

Adopt hexagonal architecture. Domain logic and use cases live in `application/` and `domain/`, communicating with the outside world through protocol-based ports (`extraction.py`, `repositories.py`, `clock.py`). Concrete adapters (`adapters/llm/`, `adapters/persistence/`) implement those ports. A composition root (`config/composition.py`) wires adapters at startup.

## Consequences

- **Positive:** Swapping LLM providers is a config change, not a code rewrite. Tests use in-memory fakes without mocking libraries. Domain logic has zero import-time coupling to HTTP, file I/O, or any SDK.
- **Negative:** More files and indirection than a flat script. New developers must understand the port/adapter boundary before adding features.
- **Trade-off accepted:** The structural overhead is justified because the LLM landscape changes fast and we already have two providers.
