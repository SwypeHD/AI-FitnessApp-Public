# ADR-0003: FieldValue Provenance System

**Status:** Accepted  
**Date:** 2026-06-04

## Context

Multiple sources produce overlapping data for the same food: the user's text, regex extraction, the knowledge base, and the LLM. We need a principled way to decide which value wins when they conflict.

## Decision

Every extracted field is wrapped in a `FieldValue(value, provenance, confidence)`. Provenance is an ordered enum: `USER > DETERMINISTIC > KNOWLEDGE_BASE > LLM > DEFAULT`. The `offer()` method on `CandidateFood` accepts a new value only if its provenance is equal or higher than the current holder's. This makes merge order irrelevant — the highest-authority source always wins.

## Consequences

- **Positive:** Reconciliation is declarative and testable. No fragile if/else chains deciding "should the LLM's calories beat the KB's?" The answer is always encoded in the provenance rank.
- **Negative:** Adding a new provenance tier requires updating the enum and reasoning about where it sits in the hierarchy.
- **Trade-off accepted:** The rigidity is a feature — it prevents accidental authority escalation.
