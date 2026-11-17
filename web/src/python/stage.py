"""Turn a parsed shared-format DataFrame into a staging file for DuckDB (src/sql/stage_*.sql).

Parquet (via pyarrow) is preferred: typed, compact, no quoting issues. CSV is the
fallback when pyarrow is not available. Pure Python + pandas (+ optional pyarrow).
"""

from __future__ import annotations

import io

import pandas as pd

from schema import COLUMNS, TS_UTC

STAGE_COLUMNS = ["seq", *COLUMNS]


def stage_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Add `seq` (row order in the file) and make ts_utc a naive UTC timestamp,
    matching the DuckDB TIMESTAMP column."""
    out = df[COLUMNS].copy()
    out.insert(0, "seq", range(len(out)))
    out[TS_UTC] = pd.to_datetime(out[TS_UTC], utc=True).dt.tz_localize(None)
    return out


def to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    stage_frame(df).to_parquet(buf, index=False)
    return buf.getvalue()


def to_csv_text(df: pd.DataFrame) -> str:
    return stage_frame(df).to_csv(index=False, date_format="%Y-%m-%d %H:%M:%S.%f")
