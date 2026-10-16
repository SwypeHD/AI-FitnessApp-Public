# ADR-0009: Exercise Regimen with Living Calendar

**Status:** Accepted  
**Date:** 2026-06-16

## Context

Users need structured workout plans, not just ad-hoc exercise logging. A "Push Pull Legs" lifter shouldn't have to remember which day they're on — the app should track that. But real life means missed days, schedule conflicts, and plan changes.

## Decision

Three-layer model:

1. **Saved Plans (templates)** — Reusable workout templates like PPL, Upper/Lower. Each defines a 7-day rotation with exercises, sets, and reps per day. Preset plans are built-in; custom plans can be added. Plans are never lost when switching.

2. **Active Calendar (living schedule)** — An instance of a plan mapped to real dates. The calendar generates 28 days of entries from the rotation. Two manual controls adjust the schedule:
   - **Skip Day**: mark today as skipped, advance the rotation (tomorrow is the next workout)
   - **Push Back**: today's workout slides to tomorrow, everything shifts one day

3. **Exercise Log (what happened)** — Existing exercise logging stays unchanged. The calendar is what you *should* do; the log is what you *did*.

Calendar shifts are **manual only** — the user decides whether to skip or push back. The system does not auto-detect missed days.

## Alternatives Considered

- **Automatic shift detection** (midnight passes with no log → push back): Deferred. Adds complexity around partial completions and timezone edge cases. The manual model is simpler and gives the user control. Could be added later as an opt-in.
- **Full periodization** (deload weeks, progressive overload): Out of scope for now. The plan template model supports it structurally (just make a 28-day rotation) but no UI or AI support yet.
- **Diet plan templates** (same saved-template → active-schedule pattern for meal planning): Same architecture would work. Noted as a future direction.

## Consequences

- **Positive:** Users always know what to do today. Switching plans is instant and non-destructive. Skip/push-back handles real life without losing the rotation.
- **Negative:** Manual shift control means the user must actively manage missed days. Calendar state is per-device (JSON file, not synced).
