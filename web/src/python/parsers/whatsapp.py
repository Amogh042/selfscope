"""WhatsApp chat export parser -> shared event format.

Pure Python + pandas (no browser code): the same module runs in Pyodide and CPython.

Handles
  Android  "17/11/25, 9:41 pm - Name: text"      (12h with a normal, no-break or narrow
                                                   no-break space before am/pm; 24h too)
  iOS      "[17/11/25, 9:41:23 PM] Name: text"  (lines may start with U+200E; the export
                                                   is a .zip containing _chat.txt)
  - day/month vs month/day order is detected from the data
  - multi-line messages, system notices, media placeholders, deleted and edited messages

Timestamps in exports are the phone's local time with no zone; they are assumed to be
Asia/Kolkata unless `tz` is given, and stored as UTC.

    df = parse_whatsapp(text, chat_name="Priya")
    get_participants(df)   # ["Priya", "Amogh"]
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, tzinfo

import pandas as pd

from schema import (ACTOR, EVENT_TYPE, LOCAL_DATE, META, SOURCE, TEXT, TS_UTC,
                    empty_events, finalize_events, local_tz)

SOURCE_NAME = "whatsapp"

# Bidi / zero-width marks WhatsApp sprinkles into exports (U+200E is the common one on iOS).
_INVISIBLE = "‎‏‪‫‬‭‮⁦⁧⁨⁩﻿"
_INVISIBLE_RE = re.compile(f"[{_INVISIBLE}]")
_SP = "[   ]"  # space, no-break space, narrow no-break space

_DATE = r"(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4})"
_TIME = (r"(?P<time>\d{1,2}[:.]\d{2}(?:[:.]\d{2})?)"
         rf"(?:{_SP}?(?P<ampm>[aApP]\.?{_SP}?[mM]\.?))?")
ANDROID_RE = re.compile(rf"^{_DATE},?{_SP}{_TIME}{_SP}[-–]{_SP}(?P<rest>.*)$")
IOS_RE = re.compile(rf"^\[{_DATE},?{_SP}{_TIME}\]{_SP}(?P<rest>.*)$")

_SENDER_RE = re.compile(rf"^(?P<sender>[^:\n]+?):{_SP}?(?P<text>.*)$", re.S)
_EDITED_RE = re.compile(rf"{_SP}*[{_INVISIBLE}]?<This message was edited>{_SP}*$")
_DELETED = {"this message was deleted", "you deleted this message"}

# Android system lines normally have no "Name: " part; these are the ones that can
# contain a colon (e.g. a group subject) and would otherwise look like a message.
_ANDROID_SYSTEM_WITH_COLON = re.compile(
    r"^[^:]+ (?:changed the subject|changed the group description|created group)")

_MEDIA_OMITTED = re.compile(
    r"^(?:<Media omitted>|(?P<kind>image|video|audio|sticker|GIF|document|Contact card|"
    r"location|video note)(?: omitted)?)$", re.I)
_ATTACHED = re.compile(r"^<attached: (?P<file>.+)>$|^(?P<file2>.+) \(file attached\)$")
_MEDIA_TYPE_HINTS = [("PHOTO", "image"), ("IMG", "image"), ("VIDEO", "video"), ("VID", "video"),
                     ("AUDIO", "audio"), ("PTT", "audio"), ("AUD", "audio"),
                     ("STICKER", "sticker"), ("STK", "sticker"), ("GIF", "gif")]


def _strip_invisible(s: str) -> str:
    return _INVISIBLE_RE.sub("", s)


def read_export(data: bytes, filename: str = "") -> str:
    """Return chat text from raw export bytes: a .txt file, or a .zip with _chat.txt
    (iOS) / a single .txt (Android "export with media")."""
    if filename.lower().endswith(".zip") or data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            if not names:
                raise ValueError("zip contains no chat .txt file")
            name = next((n for n in names if n.split("/")[-1] == "_chat.txt"), names[0])
            data = zf.read(name)
    return data.decode("utf-8-sig", errors="replace")


def chat_name_from_filename(filename: str) -> str | None:
    """'WhatsApp Chat with Priya.txt' / 'WhatsApp Chat - Rohan.zip' -> 'Priya' / 'Rohan'."""
    base = filename.replace("\\", "/").split("/")[-1]
    m = re.match(r"^WhatsApp Chat (?:with|-)\s*(.+?)(?:\s*\(\d+\))?\.(?:txt|zip)$", base, re.I)
    return m.group(1).strip() if m else None


def _detect_platform(lines: list[str]) -> str:
    sample = [l.lstrip(_INVISIBLE) for l in lines[:500]]
    ios = sum(bool(IOS_RE.match(l)) for l in sample)
    android = sum(bool(ANDROID_RE.match(l)) for l in sample)
    return "ios" if ios > android else "android"


def _split_date(d: str) -> tuple[int, int, int]:
    a, b, c = (int(x) for x in re.split(r"[./-]", d))
    return a, b, c


def _detect_date_order(dates: list[str], times: list[tuple[int, int, int]]) -> str:
    """Return 'DMY', 'MDY' or 'YMD'. Uses impossible values first, then which order
    keeps the chat in chronological order. Defaults to DMY (Indian locale)."""
    parts = [_split_date(d) for d in dates]
    if not parts:
        return "DMY"
    if any(a > 31 for a, _, _ in parts):
        return "YMD"
    first_gt12 = any(a > 12 for a, _, _ in parts)
    second_gt12 = any(b > 12 for _, b, _ in parts)
    if first_gt12 and not second_gt12:
        return "DMY"
    if second_gt12 and not first_gt12:
        return "MDY"

    def inversions(order: str) -> int:
        prev, bad = None, 0
        for (a, b, c), t in zip(parts, times):
            day, month = (a, b) if order == "DMY" else (b, a)
            try:
                cur = datetime(_year(c), month, day, *t)
            except ValueError:
                return len(parts) + 1
            if prev is not None and cur < prev:
                bad += 1
            prev = cur
        return bad

    return "MDY" if inversions("MDY") < inversions("DMY") else "DMY"


def _year(y: int) -> int:
    return 2000 + y if y < 100 else y


def _parse_time(t: str, ampm: str | None) -> tuple[int, int, int]:
    nums = [int(x) for x in re.split(r"[:.]", t)]
    h, m, s = nums[0], nums[1], nums[2] if len(nums) > 2 else 0
    if ampm:
        p = _strip_invisible(ampm).lower().replace(".", "").strip()[0]
        if p == "p" and h < 12:
            h += 12
        elif p == "a" and h == 12:
            h = 0
    return h, m, s


def _media_type(text: str) -> str | None:
    m = _MEDIA_OMITTED.match(text)
    if m:
        kind = (m.group("kind") or "media").lower()
        return {"contact card": "contact", "video note": "video"}.get(kind, kind)
    m = _ATTACHED.match(text)
    if m:
        fname = (m.group("file") or m.group("file2") or "").upper()
        for hint, kind in _MEDIA_TYPE_HINTS:
            if hint in fname:
                return kind
        return "document"
    return None


def _classify(rest: str, platform: str):
    """-> (event_type, actor, text, meta_extra)"""
    m = _SENDER_RE.match(rest)
    if not m or (platform == "android" and _ANDROID_SYSTEM_WITH_COLON.match(rest)):
        return "system", None, _strip_invisible(rest).strip(), {}

    sender = _strip_invisible(m.group("sender")).strip()
    raw = m.group("text")
    extra: dict = {}
    if _EDITED_RE.search(raw):
        raw = _EDITED_RE.sub("", raw)
        extra["edited"] = True
    starts_marked = raw[:1] in _INVISIBLE
    clean = _strip_invisible(raw).strip()

    if clean.rstrip(".").lower() in _DELETED:
        return "message", sender, None, {"kind": "deleted", **extra}
    media = _media_type(clean)
    if media:
        return "message", sender, None, {"kind": "media", "media_type": media, **extra}
    if starts_marked:
        # iOS prefixes system notices (and only those, besides media) with U+200E;
        # the "sender" is then the chat itself, not a participant.
        return "system", None, clean, {}
    return "message", sender, raw.rstrip(), {"kind": "text", **extra}


def parse_whatsapp(text: str, chat_name: str | None = None, tz: tzinfo | None = None) -> pd.DataFrame:
    """Parse a WhatsApp export (.txt content) into the shared event format.

    `chat_name` is stored in meta.chat. `tz` is the zone the phone was in
    (default Asia/Kolkata). The result's .attrs has platform / date_order / skipped_lines.
    """
    tz = tz or local_tz()
    lines = re.split(r"\r\n|\r|\n", text.lstrip("﻿"))
    platform = _detect_platform(lines)
    rx = IOS_RE if platform == "ios" else ANDROID_RE

    records: list[list[str | None]] = []  # [date, time, ampm, rest]
    skipped = 0
    for line in lines:
        m = rx.match(line.lstrip(_INVISIBLE)) if line else None
        if m:
            records.append([m.group("date"), m.group("time"), m.group("ampm"), m.group("rest")])
        elif records:
            records[-1][3] += "\n" + line  # continuation of a multi-line message
        elif line.strip():
            skipped += 1

    if not records:
        df = empty_events()
        df.attrs.update(platform=platform, date_order=None, skipped_lines=skipped)
        return df

    times = [_parse_time(r[1], r[2]) for r in records]
    order = _detect_date_order([r[0] for r in records], times)

    rows = []
    for (date_s, _, _, rest), t in zip(records, times):
        a, b, c = _split_date(date_s)
        y, mo, d = {"DMY": (c, b, a), "MDY": (c, a, b), "YMD": (a, b, c)}[order]
        try:
            local = datetime(_year(y), mo, d, *t)
        except ValueError:
            skipped += 1
            continue
        event_type, actor, body, extra = _classify(rest.rstrip("\n"), platform)
        meta = {"chat": chat_name, "platform": platform, **extra}
        rows.append({SOURCE: SOURCE_NAME, TS_UTC: local, EVENT_TYPE: event_type, ACTOR: actor,
                     TEXT: body, META: json.dumps(meta, ensure_ascii=False)})

    df = pd.DataFrame(rows)
    df[TS_UTC] = (pd.to_datetime(df[TS_UTC])
                  .dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward")
                  .dt.tz_convert("UTC"))
    df = finalize_events(df.dropna(subset=[TS_UTC]), tz)
    df.attrs.update(platform=platform, date_order=order, skipped_lines=skipped)
    return df


def get_participants(df: pd.DataFrame) -> list[str]:
    """Senders of real messages (not system notices), most active first."""
    msgs = df[df[EVENT_TYPE] == "message"]
    counts = msgs[ACTOR].value_counts()
    return sorted(counts.index.tolist(), key=lambda n: (-counts[n], n))


def summarize_chat(df: pd.DataFrame) -> dict:
    """Small JSON-friendly summary for the import screen."""
    msgs = df[df[EVENT_TYPE] == "message"]
    kinds = msgs[META].map(lambda m: json.loads(m).get("kind"))
    per_person = msgs[ACTOR].value_counts()
    system_text = df.loc[df[EVENT_TYPE] == "system", TEXT].fillna("")
    participants = get_participants(df)
    return {
        "platform": df.attrs.get("platform"),
        "date_order": df.attrs.get("date_order"),
        "participants": participants,
        "is_group": bool(len(participants) > 2 or system_text.str.contains("created group").any()),
        "events": int(len(df)),
        "messages": int(len(msgs)),
        "text_messages": int((kinds == "text").sum()),
        "media": int((kinds == "media").sum()),
        "deleted": int((kinds == "deleted").sum()),
        "system": int((df[EVENT_TYPE] == "system").sum()),
        "first_date": df[LOCAL_DATE].min() if len(df) else None,
        "last_date": df[LOCAL_DATE].max() if len(df) else None,
        "per_person": {k: int(per_person[k]) for k in participants},
        "skipped_lines": int(df.attrs.get("skipped_lines", 0)),
    }
