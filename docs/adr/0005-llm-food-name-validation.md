# ADR-0005: LLM Food Name Validation Safety Net

**Status:** Accepted  
**Date:** 2026-06-16

## Context

Regex-based food name extraction fails on conversational phrasing. "Could you log 3 servings of chicken for me for dinner?" extracts "could you chicken me" after stopword removal misses edge cases. Adding more stopwords is whack-a-mole.

## Decision

After regex extraction, a small LLM (4B parameter model on Ollama) validates each extracted food name against the original input. The model receives only the raw input and extracted name, returning just the corrected food name. This runs before KB lookup so corrected names can match known foods. Results use `Provenance.LLM` (0.8 confidence) so they cannot override user-provided or KB-derived names.

## Alternatives Considered

- **More stopwords:** Diminishing returns; can't anticipate all conversational patterns.
- **Full LLM extraction as primary:** Violates deterministic-first principle (ADR-0002). Too slow and unreliable for the primary path.
- **NLP parser (spaCy):** Heavy dependency for a narrow problem. The 4B model is already running for gap-fill.

## Consequences

- **Positive:** Catches the long tail of conversational phrasing without degrading the deterministic path. Gracefully degrades (keeps regex result) if LLM is down.
- **Negative:** Adds one LLM round-trip per food item during logging. On local Ollama with a 4B model this is ~100-300ms.
- **Trade-off accepted:** Sub-second latency for correct food names. The DGX hardware makes this essentially free.
