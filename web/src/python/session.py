"""Worker-side entry point for the import screen: parse ONE file and return it as a
staging file (Parquet, or CSV fallback) for DuckDB. Nothing is kept in worker memory;
storage and de-duplication live in DuckDB (src/sql/import.sql).
"""

from __future__ import annotations

import json

import pandas as pd

from parsers.sbi import parse_sbi
from parsers.spotify import parse_spotify
from parsers.whatsapp import parse_whatsapp
from parsers.youtube import parse_youtube
from stage import to_csv_text, to_parquet_bytes


def _as_bytes(data) -> bytes:
    """Bank files arrive as bytes (a JS Uint8Array proxy in Pyodide)."""
    if hasattr(data, "to_bytes"):  # pyodide JsProxy of a typed array
        return data.to_bytes()
    if isinstance(data, str):
        return data.encode("utf-8")
    return bytes(data)


def parse(source: str, text, chat_name: str | None = None, label: str = "file") -> pd.DataFrame:
    if source == "bank":
        return parse_sbi(_as_bytes(text), filename=label)
    if source == "whatsapp":
        return parse_whatsapp(text, chat_name=chat_name)
    if source == "spotify":
        return parse_spotify({label: text})
    if source == "youtube":
        return parse_youtube({label: text})
    raise ValueError(f"no parser for source {source!r}")


def stage(source: str, text: str, chat_name: str | None = None, label: str = "file",
          fmt: str = "parquet") -> dict:
    """-> {"format", "data" (bytes for parquet / str for csv), "rows", "info" (JSON of parser attrs)}"""
    df = parse(source, text, chat_name, label)
    data = to_parquet_bytes(df) if fmt == "parquet" else to_csv_text(df)
    info = {k: v for k, v in df.attrs.items() if k != "per_file"}
    return {"format": fmt, "data": data, "rows": int(len(df)), "info": json.dumps(info, default=str)}
