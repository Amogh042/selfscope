"""YouTube video topic: study / music / comedy / podcast / tech / finance / other.

1. Curated channel -> topic map (web/public/data/youtube_channels.json), case-insensitive.
2. YouTube Music artist channels ("<Artist> - Topic") -> music.
3. Keyword rules on the video title (first matching rule wins; order matters, e.g.
   "Stand-up Comedy | Episode 3" is comedy, not podcast).
4. Otherwise "other". Ads are "other" (source "ad").
"""

from __future__ import annotations

import re

TOPICS = ["study", "music", "comedy", "podcast", "tech", "finance", "other"]

TITLE_RULES: list[tuple[str, re.Pattern]] = [
    ("music", re.compile(r"video song|lyrical|full song|audio song|official (music )?video|lyric video|\(lyrics\)|"
                         r"\blyrics\b|jukebox|music video", re.I)),
    ("comedy", re.compile(r"\bvines?\b|stand-?up|comedy|funny|roast|sketch|prank|crowd work|memes?\b", re.I)),
    ("podcast", re.compile(r"podcast|\bep\.? ?\d|\bepisode\b|full interview|ft\.", re.I)),
    ("study", re.compile(r"tutorial|explained|one shot|lecture|course|for beginners|interview questions|"
                         r"\blearn\b|\bclass \d|chapter|syllabus|crash course|in one video|\bdsa\b|"
                         r"\bdbms\b|\bjee\b|\bneet\b|\bgate\b|\bupsc\b", re.I)),
    ("tech", re.compile(r"review|unboxing|\bvs\.?\b|best phones?|smartphone|laptop|camera test|specs|"
                        r"hands[- ]on|first look", re.I)),
    ("finance", re.compile(r"stock|mutual funds?|\bsip\b|invest|money|budget|\btax\b|finance|savings|"
                           r"credit card|salary|lakh|crore", re.I)),
]


def channel_index(channels: dict[str, str]) -> dict[str, str]:
    return {k.strip().lower(): v for k, v in channels.items()}


def classify(channel: str | None, title: str | None, index: dict[str, str], is_ad: bool = False) -> tuple[str, str]:
    """-> (topic, source) with source in channel | topic_channel | title | ad | none."""
    if is_ad:
        return "other", "ad"
    ch = (channel or "").strip()
    if ch.lower() in index:
        return index[ch.lower()], "channel"
    if ch.endswith(" - Topic"):
        return "music", "topic_channel"
    t = title or ""
    for topic, rx in TITLE_RULES:
        if rx.search(t):
            return topic, "title"
    return "other", "none"
