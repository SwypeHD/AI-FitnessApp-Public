# ADR-0007: JSONL Interaction Logging for Development

**Status:** Accepted  
**Date:** 2026-06-16

## Context

Regex extraction and LLM responses need debugging in development. When a user reports "it logged the wrong food name," we need to see the exact input, extraction result, and response without reproducing the conversation.

## Decision

Every `/messages` request/response pair is logged to `data/interactions/YYYY-MM-DD.jsonl`. One line per interaction, including timestamp, input text, response status, message, and notes. Logging is initialized at startup and is a no-op if the log directory isn't configured.

## Consequences

- **Positive:** Full audit trail for debugging extraction quality. Easy to grep/analyze with standard tools. Daily rotation keeps files manageable.
- **Negative:** Writes to disk on every request. Not suitable for production at scale without rotation/cleanup.
- **Trade-off accepted:** This is a development-stage tool. The data is invaluable for improving extraction rules and LLM prompts.
