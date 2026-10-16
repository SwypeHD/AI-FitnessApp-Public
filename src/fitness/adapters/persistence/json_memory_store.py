"""JSON file implementation of the coach memory store.

Single file at ``<data_dir>/coach_memory.json``; same atomic-write pattern as the
other JSON stores.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path

from fitness.domain.coach_memory import CoachMemory

MAX_MEMORIES = 50


class JsonMemoryStore:
    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "coach_memory.json"

    def list_all(self) -> list[CoachMemory]:
        if not self._path.exists():
            return []
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                records = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return []
        out: list[CoachMemory] = []
        for r in records:
            try:
                out.append(CoachMemory(
                    text=r["text"],
                    created=date.fromisoformat(r["created"]),
                ))
            except (KeyError, ValueError):
                continue  # skip malformed rows rather than losing the whole file
        return out

    def add(self, memory: CoachMemory) -> bool:
        """Store a memory. Returns False if an equivalent one already exists."""
        existing = self.list_all()
        norm = memory.text.strip().lower()
        if any(m.text.strip().lower() == norm for m in existing):
            return False
        existing.append(memory)
        # Keep the newest; unbounded growth would crowd the system prompt.
        self._write(existing[-MAX_MEMORIES:])
        return True

    def remove_matching(self, term: str) -> list[CoachMemory]:
        """Delete memories containing ``term``. Returns what was removed."""
        existing = self.list_all()
        removed = [m for m in existing if m.matches(term)]
        if removed:
            self._write([m for m in existing if not m.matches(term)])
        return removed

    def clear(self) -> int:
        count = len(self.list_all())
        self._write([])
        return count

    def _write(self, memories: list[CoachMemory]) -> None:
        records = [{"text": m.text, "created": m.created.isoformat()} for m in memories]
        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(records, fh, indent=2)
            os.replace(tmp, self._path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
