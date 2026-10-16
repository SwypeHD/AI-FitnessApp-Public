"""Ports — the hexagon boundary, expressed as ``typing.Protocol`` interfaces.

Structural typing means adapters need not inherit from these; test fakes implement
them trivially. The application depends on these abstractions, never on concrete
adapters.
"""
