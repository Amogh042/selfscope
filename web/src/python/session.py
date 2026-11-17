"""In-memory store for parsed events inside the Python worker, plus JSON helpers
for the import screen. Nothing is persisted or sent anywhere (DuckDB storage comes later).
"""

from __future__ import annotations

import json

import pandas as pd

from parsers.whatsapp import parse_whatsapp, summarize_chat

# file id -> DataFrame in the shared event format
EVENTS: dict[str, pd.DataFrame] = {}


def _preview(df: pd.DataFrame, n: int = 20) -> list[dict]:
    return json.loads(df.head(n).to_json(orient="records", date_format="iso"))


def import_whatsapp(file_id: str, text: str, chat_name: str | None) -> str:
    """Parse one chat, keep it in memory, return a JSON summary + 20-row preview."""
    df = parse_whatsapp(text, chat_name=chat_name)
    EVENTS[file_id] = df
    summary = summarize_chat(df)
    summary["chat"] = chat_name
    summary["preview"] = _preview(df)
    return json.dumps(summary, ensure_ascii=False)


def forget(file_id: str) -> None:
    EVENTS.pop(file_id, None)
