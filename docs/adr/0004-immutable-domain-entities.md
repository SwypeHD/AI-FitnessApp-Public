# ADR-0004: Immutable Domain Entities

**Status:** Accepted  
**Date:** 2026-06-04

## Context

Meal and Food entities are persisted, queried, and displayed. Mutable entities risk accidental state corruption when shared across use cases or passed to view layers.

## Decision

Domain entities (`Meal`, `Food`) use `@dataclass(frozen=True)`. Mutations produce new instances. Mutable `CandidateFood` / `CandidateMeal` are used during extraction/reconciliation, then frozen into domain entities via builders at persistence time.

## Consequences

- **Positive:** Once a Meal is saved, no code path can silently mutate it. Thread safety is trivial. Equality and hashing work correctly.
- **Negative:** Edit operations (move, delete) require reconstructing the entire meal aggregate. The builder pattern adds a translation step.
- **Trade-off accepted:** Reconstruction cost is negligible for meal-sized aggregates (1-10 foods).
