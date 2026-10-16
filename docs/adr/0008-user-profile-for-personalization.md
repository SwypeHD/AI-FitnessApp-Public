# ADR-0008: Expanded User Profile for Personalized Recommendations

**Status:** Accepted  
**Date:** 2026-06-16

## Context

The AI assistant gives generic fitness advice. To make exercise and nutrition recommendations meaningful, it needs to know the user's physical stats, fitness goals, experience level, and limitations.

## Decision

Expand `UserProfile` beyond name/weight/targets to include: age, gender, height, fitness goal, activity level, experience level, and injuries/limitations. All fields are optional (zero/empty defaults). The profile is injected into chat grounding text so the LLM can tailor recommendations. A dedicated Profile tab in the UI separates personal/fitness data from app configuration (Settings).

## Alternatives Considered

- **Chat-only profiling (AI asks questions):** Good UX but unreliable extraction. Hard to persist structured data from free-form answers. Could be added as a layer on top of the form-based profile.
- **Keep everything in Settings:** Conflates app configuration with personal data. Settings should be for things like LLM provider and data directory.

## Consequences

- **Positive:** The LLM has rich context for personalized advice. Profile fields are structured and directly editable. Grounding text is deterministic — no LLM interpretation of user stats.
- **Negative:** More fields to maintain. Users may not fill in all fields immediately.
- **Trade-off accepted:** Optional fields degrade gracefully (grounding text omits empty fields). The form ensures data quality; a future conversational profiling flow can update the same model.
