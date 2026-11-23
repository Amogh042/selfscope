"""Worker entry point: enrich stored events (YouTube topic, Spotify mood/language,
WhatsApp sentiment) and return what to write back into DuckDB (src/sql/enrich.sql).

Output per event: category (topic / mood / pos-neu-neg, or null) + a meta patch.
Every event processed also gets meta.enrich_version so it is not processed again.
"""

from __future__ import annotations

import json

from . import ENRICH_VERSION
from .music_moods import MoodIndex
from .sentiment import Scorer
from .youtube_topics import channel_index, classify

_RES: dict = {}


def load_resources(channels: dict | str, songs: dict | str, lexicon: dict | str) -> None:
    def j(x):
        return json.loads(x) if isinstance(x, (str, bytes)) else x
    _RES["channels"] = channel_index(j(channels)["channels"])
    _RES["moods"] = MoodIndex(j(songs))
    _RES["sentiment"] = Scorer(j(lexicon))


def loaded() -> bool:
    return bool(_RES)


def enrich_event(e: dict) -> dict:
    """e: {event_key, source, event_type, actor, title, text, meta (dict)} -> {event_key, category, patch}."""
    meta = e["meta"]
    patch: dict = {"enrich_version": ENRICH_VERSION}
    category = None
    if e["source"] == "youtube" and e["event_type"] == "watch":
        topic, src = classify(e.get("actor"), e.get("title"), _RES["channels"], bool(meta.get("is_ad")))
        category, patch["topic_source"] = topic, src
    elif e["source"] == "spotify":
        if meta.get("kind", "music") == "music":
            mood, lang, src = _RES["moods"].lookup(e.get("title"), e.get("actor"))
        else:
            mood, lang, src = "unknown", "unknown", "not_music"
        category = mood
        patch.update(language=lang, mood_source=src)
    elif e["source"] == "whatsapp" and e["event_type"] == "message" and meta.get("kind") == "text" and e.get("text"):
        score, label = _RES["sentiment"].score(e["text"])
        category = label
        patch["sentiment"] = score
    return {"event_key": e["event_key"], "category": category, "patch": json.dumps(patch, ensure_ascii=False)}


def enrich_events_json(events_json: str) -> str:
    events = json.loads(events_json)
    out = []
    for e in events:
        e["meta"] = json.loads(e["meta"]) if isinstance(e["meta"], str) else e["meta"]
        out.append(enrich_event(e))
    return json.dumps({"version": ENRICH_VERSION, "predictions": out}, ensure_ascii=False)
