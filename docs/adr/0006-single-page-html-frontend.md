# ADR-0006: Single-Page HTML Frontend (No Framework)

**Status:** Accepted  
**Date:** 2026-06-04

## Context

The app needs a web UI for food logging, exercise tracking, dashboard, and AI chat. The backend is Python/FastAPI. The question is whether to use a JS framework (React, Vue, Svelte) or keep it simple.

## Decision

Single `index.html` with inline CSS and vanilla JavaScript. FastAPI serves it as a static file. Navigation is client-side page switching (show/hide divs). State is fetched from the API on each page visit.

## Consequences

- **Positive:** Zero build step, zero JS dependencies, instant page loads (no bundle), trivially deployable. The entire frontend is one file that any developer can read top-to-bottom.
- **Negative:** No component model — repetitive DOM construction in JS. No reactive data binding — manual `refreshData()` calls after mutations. Will not scale gracefully past ~1500 lines of JS.
- **Trade-off accepted:** This is a personal/dev tool, not a production SaaS. Simplicity and iteration speed matter more than scalability. If it outgrows vanilla JS, the API contract is stable and a framework frontend can be dropped in.
