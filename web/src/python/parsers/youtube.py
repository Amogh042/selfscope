"""YouTube watch history (Google Takeout watch-history.json) -> shared event format.

Pure Python + pandas (no browser code): the same module runs in Pyodide and CPython.

Takeout entries look like
  {"header": "YouTube", "title": "Watched <video title>", "titleUrl": "https://www.youtube.com/watch?v=…",
   "subtitles": [{"name": "<channel>", "url": "…/channel/…"}], "time": "2026-11-16T17:26:07.900Z",
   "details": [{"name": "From Google Ads"}]}      # details only on ads

Takeout records no watch duration, so meta.est_watch_min is estimated from the gap to
the next watch in the same session (method in docs/schema.md, "YouTube watch time").

    df = parse_youtube(text)        # or {label: text} for several files
    summarize_youtube(df)
"""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from schema import (ACTOR, EVENT_TYPE, LOCAL_DATE, META, SOURCE, TEXT, TITLE, TS_UTC,
                    empty_events, finalize_events)

SOURCE_NAME = "youtube"

# Watch-time estimate (documented in docs/schema.md — keep in sync)
SESSION_GAP_MIN = 30.0   # a gap of 30+ minutes starts a new session
MAX_WATCH_MIN = 20.0     # cap on any single estimate
LAST_IN_SESSION_MIN = 5.0  # default for the last video of a session

WATCHED = "Watched "
VIEWED = "Viewed "
REMOVED_TITLES = {"Watched a video that has been removed", "Watched a post that is no longer available"}
AD_MARKER = "From Google Ads"
_VIDEO_ID = re.compile(r"(?:[?&]v=|/shorts/|youtu\.be/|/live/)([A-Za-z0-9_-]{6,})")
_VIDEO_URL = re.compile(r"youtube\.com/(?:watch|shorts/|live/)|youtu\.be/")


def _load(files) -> list[tuple[str, list]]:
    """Accept {label: json text | bytes | list}, a single JSON text, or a list of entries."""
    if isinstance(files, (str, bytes, list)):
        files = {"watch-history.json": files}
    out = []
    for label, content in files.items():
        data = json.loads(content) if isinstance(content, (str, bytes)) else content
        if not isinstance(data, list):
            raise ValueError(f"{label}: expected a JSON array (Takeout watch-history.json)")
        out.append((label, data))
    return out


def video_id(url: str | None) -> str | None:
    if not url:
        return None
    m = _VIDEO_ID.search(url)
    return m.group(1) if m else None


def _entry(e, log: dict):
    """-> (time, event_type, actor, title, text, meta) or None if not an entry."""
    if not isinstance(e, dict) or "time" not in e:
        return None
    raw_title = e.get("title") or ""
    url = e.get("titleUrl") or None
    subs = e.get("subtitles") or []
    channel = subs[0] if subs and isinstance(subs[0], dict) else {}
    details = e.get("details") or []
    is_ad = any(isinstance(d, dict) and d.get("name") == AD_MARKER for d in details)
    meta = {"header": e.get("header"), "video_id": video_id(url), "channel_url": channel.get("url"),
            "is_ad": is_ad, "is_short": bool(url and "/shorts/" in url)}

    if raw_title.startswith(VIEWED):
        # Community posts / stories etc. — not a video watch
        return e["time"], "system", None, None, raw_title, {**meta, "kind": "viewed", "url": url}
    if raw_title in REMOVED_TITLES:
        return e["time"], "watch", None, None, None, {**meta, "removed": True}
    if raw_title.startswith(WATCHED):
        title = raw_title[len(WATCHED):]
    else:
        # Non-English Takeout ("Visto …", "… देखा गया"): keep the title as-is and log it.
        if not (url and _VIDEO_URL.search(url)):
            return e["time"], "system", None, None, raw_title, {**meta, "kind": "other", "url": url}
        title = raw_title
        log["unrecognised_prefix"] += 1
        if len(log["examples"]) < 5:
            log["examples"].append(raw_title[:80])
    if title.startswith(("http://", "https://")):  # private/unavailable video: title is the URL
        meta["title_unavailable"] = True
        meta["video_id"] = meta["video_id"] or video_id(title)
        title = None
    return e["time"], "watch", channel.get("name") or None, title or None, None, meta


def estimate_watch_minutes(ts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """For time-sorted watch timestamps -> (est minutes, session number).

    est = gap to the next watch, capped at MAX_WATCH_MIN, unless that gap is
    SESSION_GAP_MIN or more (or there is no next watch): then it is the last video of
    its session and gets LAST_IN_SESSION_MIN.
    """
    gap = (ts.shift(-1) - ts).dt.total_seconds().to_numpy() / 60.0
    last = np.isnan(gap) | (gap >= SESSION_GAP_MIN)
    est = np.where(last, LAST_IN_SESSION_MIN, np.minimum(np.nan_to_num(gap), MAX_WATCH_MIN))
    session = np.concatenate([[0], np.cumsum(last[:-1])]) if len(ts) else np.array([], dtype=int)
    return np.round(est, 2), session.astype(int)


def parse_youtube(files) -> pd.DataFrame:
    """Parse Takeout watch history into the shared event format.

    The result's .attrs has per_file / unrecognised_prefix / prefix_examples /
    skipped_records / duplicates_dropped / sessions.
    """
    log = {"unrecognised_prefix": 0, "examples": []}
    rows, per_file, bad = [], {}, 0
    for label, entries in _load(files):
        n = 0
        for e in entries:
            r = _entry(e, log)
            if r is None:
                bad += 1
                continue
            rows.append((label, *r))
            n += 1
        per_file[label] = n

    attrs = dict(per_file=per_file, unrecognised_prefix=log["unrecognised_prefix"],
                 prefix_examples=log["examples"], skipped_records=bad, duplicates_dropped=0, sessions=0)
    if not rows:
        df = empty_events()
        df.attrs.update(attrs)
        return df

    raw = pd.DataFrame(rows, columns=["label", "time", EVENT_TYPE, ACTOR, TITLE, TEXT, "meta_d"])
    raw[TS_UTC] = pd.to_datetime(raw["time"], utc=True, format="ISO8601", errors="coerce")
    attrs["skipped_records"] += int(raw[TS_UTC].isna().sum())
    raw = raw[raw[TS_UTC].notna()].sort_values(TS_UTC, kind="stable").reset_index(drop=True)
    kept = raw["label"].value_counts()
    attrs["per_file"] = {label: int(kept.get(label, 0)) for label in per_file}  # rows with a valid time

    # The same entry in two files (e.g. two Takeouts) should count once.
    # (Built in plain Python: pandas 3's astype(str) keeps None as NaN, and NaN keys would
    # all collide.)
    key = pd.Series([f"{t}|{m.get('video_id')}|{ti}|{tx}" for t, m, ti, tx
                     in zip(raw["time"], raw["meta_d"], raw[TITLE], raw[TEXT])])
    dup = key.duplicated()
    attrs["duplicates_dropped"] = int(dup.sum())
    raw = raw[~dup].reset_index(drop=True)

    watch = raw[EVENT_TYPE] == "watch"
    est, session = estimate_watch_minutes(raw.loc[watch, TS_UTC])
    raw["est"], raw["session"] = np.nan, -1
    raw.loc[watch, "est"], raw.loc[watch, "session"] = est, session
    attrs["sessions"] = int(session.max() + 1) if len(session) else 0

    def meta_json(m, est_min, sess):
        if est_min == est_min:  # watch rows only
            m = {**m, "est_watch_min": float(est_min), "session": int(sess)}
        return json.dumps(m, ensure_ascii=False)

    raw[META] = [meta_json(m, e_, s) for m, e_, s in zip(raw["meta_d"], raw["est"], raw["session"])]
    raw[SOURCE] = SOURCE_NAME
    df = finalize_events(raw)
    df.attrs.update(attrs)
    return df


def summarize_youtube(df: pd.DataFrame, top: int = 5) -> dict:
    """Small JSON-friendly summary for the import screen."""
    meta = df[META].map(json.loads)
    watch = df[EVENT_TYPE] == "watch"
    is_ad = meta.map(lambda m: bool(m.get("is_ad")))
    videos = df[watch & ~is_ad]
    vmeta = meta[watch & ~is_ad]
    est_min = vmeta.map(lambda m: m.get("est_watch_min", 0.0)).sum()
    channels = videos[videos[ACTOR].notna()].groupby(ACTOR).size().sort_values(ascending=False).head(top)
    return {
        "entries": int(len(df)),
        "videos": int(len(videos)),
        "ads": int((watch & is_ad).sum()),
        "est_hours": round(float(est_min) / 60.0, 1),
        "top_channels": [{"name": c, "videos": int(n)} for c, n in channels.items()],
        "channels": int(videos[ACTOR].nunique()),
        "shorts": int(vmeta.map(lambda m: m.get("is_short", False)).sum()),
        "music": int(vmeta.map(lambda m: m.get("header") == "YouTube Music").sum()),
        "removed": int(vmeta.map(lambda m: bool(m.get("removed") or m.get("title_unavailable"))).sum()),
        "system": int((df[EVENT_TYPE] == "system").sum()),
        "sessions": int(df.attrs.get("sessions", 0)),
        "first_date": df[LOCAL_DATE].min() if len(df) else None,
        "last_date": df[LOCAL_DATE].max() if len(df) else None,
        "per_file": df.attrs.get("per_file", {}),
        "unrecognised_prefix": int(df.attrs.get("unrecognised_prefix", 0)),
        "prefix_examples": df.attrs.get("prefix_examples", []),
        "duplicates_dropped": int(df.attrs.get("duplicates_dropped", 0)),
        "skipped_records": int(df.attrs.get("skipped_records", 0)),
    }
