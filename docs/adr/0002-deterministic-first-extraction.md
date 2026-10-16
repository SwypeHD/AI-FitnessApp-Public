# ADR-0002: Deterministic-First Extraction (LLM as Untrusted Advisor)

**Status:** Accepted  
**Date:** 2026-06-04

## Context

LLMs hallucinate numbers, invent foods, and fail unpredictably. Users need reliable food logging that works even when the model is down.

## Decision

Rule-based extraction runs first and is authoritative. A static food knowledge base fills macros/calories for known foods. The LLM is called **only** when fields are still missing after deterministic + KB passes. LLM results carry `Provenance.LLM` (lowest priority) and cannot override `USER`, `DETERMINISTIC`, or `KNOWLEDGE_BASE` values.

## Consequences

- **Positive:** App works fully offline / LLM-down. Known foods (eggs, chicken, rice) get exact KB nutrition. Hallucinated macro values can never override real data.
- **Negative:** Unknown foods with no KB entry and no LLM end up in a clarification loop asking the user for macros manually.
- **Trade-off accepted:** Accuracy over convenience. A wrong calorie count silently logged is worse than asking the user one question.
