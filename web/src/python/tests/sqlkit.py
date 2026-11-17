"""Test helpers: run web/src/sql/*.sql with the duckdb Python package, mirroring
what web/src/lib/store.ts does in the browser."""

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path

import duckdb

from stage import to_csv_text, to_parquet_bytes

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
_TMP = Path(tempfile.mkdtemp(prefix="selfscope-sql-"))


def sql(name: str) -> str:
    return (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")


def named(name: str) -> dict[str, str]:
    """Split a file of '-- name: x' blocks into {x: sql}."""
    parts = re.split(r"^-- name: (\w+)\s*$", sql(name), flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def literal(v) -> str:
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def set_vars(con, **values) -> None:
    for k, v in values.items():
        con.execute(f"SET VARIABLE {k} = {literal(v)}")


def connect():
    con = duckdb.connect()
    con.execute(sql("schema"))
    con.execute(sql("views"))
    return con


def import_df(con, df, source: str, file_name: str, fmt: str = "parquet") -> dict:
    """Stage a parsed frame and merge it like the app does. Returns the imports row."""
    path = _TMP / f"{uuid.uuid4().hex}.{fmt}"
    if fmt == "parquet":
        path.write_bytes(to_parquet_bytes(df))
    else:
        path.write_text(to_csv_text(df), encoding="utf-8")
    import_id = uuid.uuid4().hex
    set_vars(con, stage_file=str(path), import_id=import_id, source=source, file_name=file_name,
             file_hash=None, imported_at="2026-11-17 12:00:00")
    con.execute(sql(f"stage_{fmt}"))
    con.execute(sql("import"))
    row = con.execute("SELECT * FROM imports WHERE import_id = ?", [import_id]).fetchone()
    cols = [d[0] for d in con.description]
    return dict(zip(cols, row))


def scalar(con, q: str, *params):
    return con.execute(q, list(params)).fetchone()[0]
