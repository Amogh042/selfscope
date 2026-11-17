"""Spotify streaming history -> shared event format.

Pure Python + pandas (no browser code): the same module runs in Pyodide and CPython.

Supports both export types (and merges any number of files from one export):
  Account data        StreamingHistory_music_N.json    endTime "YYYY-MM-DD HH:MM" (UTC),
                      StreamingHistory_podcast_N.json  artistName/trackName or
                                                       podcastName/episodeName, msPlayed
  Extended history    Streaming_History_Audio_*.json   ts (ISO UTC), ms_played,
                      (older: endsong_N.json)          master_metadata_*, spotify_track_uri,
                                                       reason_start/end, shuffle, skipped,
                                                       platform, episode_name/_show_name, ...

Spotify timestamps mark when playback ENDED: that is what ts_utc holds, and
meta.start_estimate = end - ms played. Missing/unknown fields never raise.

    df = parse_spotify({"StreamingHistory_music_0.json": text, ...})
    summarize_spotify(df)
"""

from __future__ import annotations

import json

import pandas as pd

from schema import (ACTOR, EVENT_TYPE, LOCAL_DATE, META, SOURCE, TITLE, TS_UTC, VALUE,
                    empty_events, finalize_events)

SOURCE_NAME = "spotify"
SKIP_THRESHOLD_MS = 30_000  # plays shorter than this count as skipped when Spotify doesn't say

# Extended-history fields copied into meta when present (meta key <- export field)
_EXTENDED_META = [("album", "master_metadata_album_album_name"), ("platform", "platform"),
                  ("shuffle", "shuffle"), ("reason_start", "reason_start"),
                  ("reason_end", "reason_end")]


def _clean(v):
    """Strip strings; empty strings and NaN become None."""
    if isinstance(v, str):
        v = v.strip()
        return v or None
    if isinstance(v, float) and v != v:
        return None
    return v


def _load(files) -> list[tuple[str, list]]:
    """Accept {label: json text | bytes | list}, a single JSON text, or a list of records."""
    if isinstance(files, (str, bytes, list)):
        files = {"spotify.json": files}
    out = []
    for label, content in files.items():
        data = json.loads(content) if isinstance(content, (str, bytes)) else content
        if isinstance(data, dict):  # tolerate a single object
            data = [data]
        if not isinstance(data, list):
            raise ValueError(f"{label}: expected a JSON array of plays")
        out.append((label, data))
    return out


def _record(rec) -> tuple[str, str | None, str | None, float | None, dict] | None:
    """-> (raw timestamp, actor, title, ms played, meta) or None if not a Spotify play."""
    if not isinstance(rec, dict):
        return None
    if "ts" in rec:  # extended streaming history
        ts, ms = rec.get("ts"), rec.get("ms_played")
        track = _clean(rec.get("master_metadata_track_name"))
        artist = _clean(rec.get("master_metadata_album_artist_name"))
        episode, show = _clean(rec.get("episode_name")), _clean(rec.get("episode_show_name"))
        book = _clean(rec.get("audiobook_title"))
        if track or artist:
            kind, actor, title = "music", artist, track
            uri = _clean(rec.get("spotify_track_uri"))
        elif episode or show:
            kind, actor, title = "podcast", show, episode
            uri = _clean(rec.get("spotify_episode_uri"))
        elif book:
            kind, actor, title = "audiobook", book, _clean(rec.get("audiobook_chapter_title"))
            uri = _clean(rec.get("audiobook_uri"))
        else:  # e.g. local files or plays Spotify could not resolve
            kind, actor, title, uri = "unknown", None, None, None
        meta = {"kind": kind, "format": "extended"}
        if uri:
            meta["uri"] = uri
        for key, field in _EXTENDED_META:
            v = _clean(rec.get(field))
            if v is not None:
                meta[key] = v
        skipped = rec.get("skipped")
    elif "endTime" in rec:  # account data
        ts, ms = rec.get("endTime"), rec.get("msPlayed")
        if "podcastName" in rec or "episodeName" in rec:
            kind, actor, title = "podcast", _clean(rec.get("podcastName")), _clean(rec.get("episodeName"))
        else:
            kind, actor, title = "music", _clean(rec.get("artistName")), _clean(rec.get("trackName"))
        meta = {"kind": kind, "format": "account"}
        skipped = None
    else:
        return None

    try:
        ms = float(ms) if ms is not None else None
    except (TypeError, ValueError):
        ms = None
    if isinstance(skipped, bool):
        meta["skipped"] = skipped
    elif ms is not None:
        meta["skipped"] = ms < SKIP_THRESHOLD_MS
    return ts, actor, title, ms, meta


def parse_spotify(files) -> pd.DataFrame:
    """Parse one or more Spotify history files into the shared event format.

    `files` is {label: JSON text} (labels are usually file names). Exact duplicate
    plays across files are dropped. The result's .attrs has formats / per_file /
    duplicates_dropped / skipped_records.
    """
    rows, per_file, bad = [], {}, 0
    formats: set[str] = set()
    for label, records in _load(files):
        n = 0
        for rec in records:
            r = _record(rec)
            if r is None:
                bad += 1
                continue
            ts, actor, title, ms, meta = r
            rows.append((label, ts, actor, title, ms, meta))
            formats.add(meta["format"])
            n += 1
        per_file[label] = n

    if not rows:
        df = empty_events()
        df.attrs.update(formats=[], per_file=per_file, duplicates_dropped=0, skipped_records=bad)
        return df

    raw = pd.DataFrame(rows, columns=["label", "ts", ACTOR, TITLE, VALUE, "meta_d"])
    ts = pd.to_datetime(raw["ts"], utc=True, format="ISO8601", errors="coerce")
    bad += int(ts.isna().sum())
    raw[TS_UTC] = ts
    raw = raw[ts.notna()].reset_index(drop=True)
    kept = raw["label"].value_counts()
    per_file = {label: int(kept.get(label, 0)) for label in per_file}  # rows with a valid time

    start = raw[TS_UTC] - pd.to_timedelta(raw[VALUE].fillna(0), unit="ms")
    metas = []
    for meta, s, ms in zip(raw["meta_d"], start, raw[VALUE]):
        if ms == ms:  # not NaN
            meta = {**meta, "start_estimate": s.strftime("%Y-%m-%dT%H:%M:%S.") + f"{s.microsecond // 1000:03d}Z"}
        metas.append(json.dumps(meta, ensure_ascii=False))
    raw[META] = metas
    raw[SOURCE] = SOURCE_NAME
    raw[EVENT_TYPE] = "play"

    df = finalize_events(raw)
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    df.attrs.update(formats=sorted(formats), per_file=per_file,
                    duplicates_dropped=before - len(df), skipped_records=bad)
    return df


def summarize_spotify(df: pd.DataFrame, top: int = 5) -> dict:
    """Small JSON-friendly summary for the import screen."""
    meta = df[META].map(json.loads)
    kind = meta.map(lambda m: m.get("kind"))
    skipped = meta.map(lambda m: m.get("skipped"))
    music = df[kind == "music"]

    artists = (music.groupby(ACTOR)[VALUE].agg(["size", "sum"])
               .sort_values(["size", "sum"], ascending=False).head(top))
    tracks = (music.groupby([TITLE, ACTOR]).size().sort_values(ascending=False).head(top))
    known_skips = skipped.dropna()
    return {
        "plays": int(len(df)),
        "music_plays": int(len(music)),
        "podcast_plays": int((kind == "podcast").sum()),
        "hours": round(float(df[VALUE].sum()) / 3.6e6, 1),
        "skip_rate": round(float(known_skips.astype(bool).mean()), 4) if len(known_skips) else None,
        "first_date": df[LOCAL_DATE].min() if len(df) else None,
        "last_date": df[LOCAL_DATE].max() if len(df) else None,
        "top_artists": [{"name": a, "plays": int(r["size"]), "hours": round(float(r["sum"]) / 3.6e6, 1)}
                        for a, r in artists.iterrows()],
        "top_tracks": [{"title": t, "artist": a, "plays": int(n)} for (t, a), n in tracks.items()],
        "artists": int(music[ACTOR].nunique()),
        "formats": df.attrs.get("formats", []),
        "per_file": df.attrs.get("per_file", {}),
        "duplicates_dropped": int(df.attrs.get("duplicates_dropped", 0)),
        "skipped_records": int(df.attrs.get("skipped_records", 0)),
    }
