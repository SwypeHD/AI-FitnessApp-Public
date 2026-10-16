"""Dev-mode interaction logger — writes every /messages request/response to JSONL.

Produces one file per day in ``<data_dir>/interactions/YYYY-MM-DD.jsonl``. Each line
is a JSON object with the user's input, the system's response, and a timestamp.
Useful for analyzing parsing errors and debugging extraction issues.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

_LOG_DIR: Path | None = None


def init_interaction_log(data_dir: str) -> None:
    global _LOG_DIR
    _LOG_DIR = Path(data_dir) / "interactions"
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_interaction(input_text: str, has_context: bool, response: dict) -> None:
    if _LOG_DIR is None:
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "input": input_text,
        "has_context": has_context,
        "status": response.get("status"),
        "message": response.get("message"),
        "meal_id": response.get("meal_id"),
        "notes": response.get("notes"),
    }
    log_file = _LOG_DIR / f"{date.today().isoformat()}.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
