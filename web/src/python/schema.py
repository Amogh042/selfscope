"""Shared event format — Python mirror of docs/schema.md and src/lib/schema.ts.

One row = one event from any source. Parsers build a DataFrame with SOURCE, TS_UTC
(tz-aware UTC), EVENT_TYPE, ACTOR, TITLE, TEXT, VALUE, CATEGORY, META and call
finalize_events(), which derives the local (Asia/Kolkata) fields and fixes the
column order and dtypes.

Pure Python + pandas: runs the same in Pyodide and in normal CPython.
"""

from __future__ import annotations

from datetime import timedelta, timezone, tzinfo

import pandas as pd

LOCAL_TZ_NAME = "Asia/Kolkata"

# Column names
SOURCE = "source"
TS_UTC = "ts_utc"
LOCAL_DATE = "local_date"
LOCAL_HOUR = "local_hour"
WEEKDAY = "weekday"  # 0 = Monday ... 6 = Sunday
EVENT_TYPE = "event_type"
ACTOR = "actor"
TITLE = "title"
TEXT = "text"
VALUE = "value"
CATEGORY = "category"
META = "meta"

COLUMNS = [SOURCE, TS_UTC, LOCAL_DATE, LOCAL_HOUR, WEEKDAY, EVENT_TYPE,
           ACTOR, TITLE, TEXT, VALUE, CATEGORY, META]

# Allowed values
SOURCES = ("whatsapp", "spotify", "youtube", "bank")
EVENT_TYPES = ("message", "play", "watch", "transaction", "system")


def local_tz(name: str = LOCAL_TZ_NAME) -> tzinfo:
    """Return a tzinfo for `name`. Falls back to fixed IST (+05:30, no DST since 1945)
    if the runtime has no tz database."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:
        if name == LOCAL_TZ_NAME:
            return timezone(timedelta(hours=5, minutes=30), "IST")
        raise


LOCAL_TZ = local_tz()


def empty_events() -> pd.DataFrame:
    """An empty DataFrame with the shared columns and dtypes."""
    return finalize_events(pd.DataFrame({
        SOURCE: pd.Series(dtype="object"),
        TS_UTC: pd.Series(dtype="datetime64[ns, UTC]"),
        EVENT_TYPE: pd.Series(dtype="object"),
    }))


def finalize_events(df: pd.DataFrame, tz: tzinfo | None = None) -> pd.DataFrame:
    """Derive local_date / local_hour / weekday from ts_utc and return the frame
    with exactly COLUMNS, in order, sorted by time. Missing optional columns are null."""
    tz = tz or LOCAL_TZ
    out = df.copy()
    ts = pd.to_datetime(out[TS_UTC], utc=True)
    out[TS_UTC] = ts
    local = ts.dt.tz_convert(tz)
    out[LOCAL_DATE] = local.dt.strftime("%Y-%m-%d")
    out[LOCAL_HOUR] = local.dt.hour.astype("int64")
    out[WEEKDAY] = local.dt.dayofweek.astype("int64")
    for col in (ACTOR, TITLE, TEXT, CATEGORY):
        if col not in out:
            out[col] = None
    if VALUE not in out:
        out[VALUE] = float("nan")
    out[VALUE] = pd.to_numeric(out[VALUE], errors="coerce").astype("float64")
    if META not in out:
        out[META] = "{}"
    for col in (SOURCE, EVENT_TYPE, ACTOR, TITLE, TEXT, CATEGORY, META):
        out[col] = out[col].astype("object").where(out[col].notna(), None)
    out = out[COLUMNS].sort_values(TS_UTC, kind="stable").reset_index(drop=True)
    return out
