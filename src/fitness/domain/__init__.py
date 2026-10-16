"""Pure domain layer.

Depends on the standard library only — no frameworks, no IO, no ports.
Entities and value objects are immutable (frozen dataclasses); builders are the
only mutable accumulators and exist to assemble immutable entities across turns.
"""
