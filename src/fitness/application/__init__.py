"""Application layer — use-cases and the ports they depend on.

Depends only on the domain and on its own ports (Protocols). Must never import from
``fitness.adapters`` or ``fitness.web`` — adapters implement these ports and are wired
in by the composition root.
"""
