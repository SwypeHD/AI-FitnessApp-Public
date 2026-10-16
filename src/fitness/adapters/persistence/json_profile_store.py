"""JSON file implementation of ProfileStore."""

from __future__ import annotations

import json
from pathlib import Path

from fitness.application.user_profile import UserProfile


class JsonProfileStore:
    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / "profile.json"
        Path(data_dir).mkdir(parents=True, exist_ok=True)

    def load(self) -> UserProfile:
        if not self._path.exists():
            return UserProfile()
        with self._path.open("r", encoding="utf-8") as f:
            return UserProfile.from_dict(json.load(f))

    def save(self, profile: UserProfile) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, indent=2)
