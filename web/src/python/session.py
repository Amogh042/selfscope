"""In-memory store for parsed events inside the Python worker, plus JSON helpers
for the import screen. Nothing is persisted or sent anywhere (DuckDB storage comes later).
"""

from __future__ import annotations

import json

import pandas as pd

from parsers.spotify import parse_spotify, summarize_spotify
from parsers.whatsapp import parse_whatsapp, summarize_chat
from parsers.youtube import parse_youtube, summarize_youtube

# WhatsApp: file id -> DataFrame (one per chat).
# Spotify / YouTube: "spotify" / "youtube" -> one merged DataFrame for all files of that source.
EVENTS: dict[str, pd.DataFrame] = {}

# Raw file text per source, so adding more files later re-merges (and de-duplicates) everything.
RAW: dict[str, dict[str, str]] = {"spotify": {}, "youtube": {}}

_PARSERS = {"spotify": (parse_spotify, summarize_spotify), "youtube": (parse_youtube, summarize_youtube)}


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


def import_files(source: str, files: dict[str, str]) -> str:
    """Add Spotify / YouTube files ({file id: JSON text}), re-parse all files of that
    source into one merged frame, return a JSON summary + 20-row preview.
    summary["per_file"] is keyed by file id."""
    parse, summarize = _PARSERS[source]
    RAW[source].update(files)
    df = parse(RAW[source])
    EVENTS[source] = df
    summary = summarize(df)
    summary["preview"] = _preview(df)
    return json.dumps(summary, ensure_ascii=False)


def forget(file_id: str) -> None:
    EVENTS.pop(file_id, None)
