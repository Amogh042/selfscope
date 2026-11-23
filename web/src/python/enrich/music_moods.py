"""Spotify mood (romantic / sad / upbeat / unknown) and language (hi / en / kn / other / unknown).

Spotify no longer gives new apps audio features (valence, energy, …), so moods come from
a curated list (web/public/data/song_moods.json). A song that is not on the list stays
"unknown" and is excluded from mood statistics — it is never guessed. Language comes
from the song list, else from a curated artist -> language map, else "unknown".
"""

from __future__ import annotations

import re
import unicodedata


def _key(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


class MoodIndex:
    def __init__(self, data: dict):
        self.by_pair: dict[tuple[str, str], dict] = {}
        titles: dict[str, list[dict]] = {}
        for s in data["songs"]:
            self.by_pair[(_key(s["title"]), _key(s["artist"]))] = s
            titles.setdefault(_key(s["title"]), []).append(s)
        # a title alone is enough only when it is unambiguous (one song, one mood)
        self.by_title = {t: v[0] for t, v in titles.items() if len({x["mood"] for x in v}) == 1 and len(v) == 1}
        self.artists = {_key(a): lang for a, lang in data["artists"].items()}

    def lookup(self, title: str | None, artist: str | None) -> tuple[str, str, str]:
        """-> (mood, language, source) with source in song | title | artist | none."""
        t, a = _key(title), _key(artist)
        song = self.by_pair.get((t, a))
        if song:
            return song["mood"], song["lang"], "song"
        song = self.by_title.get(t)
        if song:
            return song["mood"], song["lang"], "title"
        lang = self.artists.get(a)
        if lang:
            return "unknown", lang, "artist"
        return "unknown", "unknown", "none"
