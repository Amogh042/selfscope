"""Catalogue of daily metrics (columns of the daily_features view): source, wording, unit,
plus helpers to format values in plain English."""

from __future__ import annotations

import math
from typing import NamedTuple


class Metric(NamedTuple):
    source: str
    short: str             # used in conditions / lists: "with 2.0h+ of YouTube", "₹500 food delivery spend"
    unit: str              # min | inr | share | score | count
    event: str | None      # "did it happen?" phrase for mostly-zero metrics: "order food delivery"
    subject: str           # sentence subject: "your food delivery spend is 30% higher"


METRICS: dict[str, Metric] = {
    "spotify_minutes": Metric("spotify", "Spotify listening", "min", None, "your Spotify listening time"),
    "spotify_plays": Metric("spotify", "songs played", "count", None, "the number of songs you play"),
    "skip_rate": Metric("spotify", "song skip rate", "share", None, "your song skip rate"),
    "spotify_late_night_share": Metric("spotify", "share of songs played late at night", "share", None,
                                       "the share of songs you play late at night"),
    "spotify_sad_share": Metric("spotify", "share of sad songs", "share", None, "the share of sad songs you play"),
    "spotify_romantic_share": Metric("spotify", "share of romantic songs", "share", None,
                                     "the share of romantic songs you play"),
    "youtube_est_minutes": Metric("youtube", "YouTube", "min", None, "your YouTube watch time"),
    "youtube_videos": Metric("youtube", "YouTube videos", "count", None, "the number of YouTube videos you watch"),
    "youtube_late_night_share": Metric("youtube", "share of YouTube watched late at night", "share", None,
                                       "the share of YouTube you watch late at night"),
    "youtube_study_min": Metric("youtube", "study videos", "min", "watch study videos", "your time on study videos"),
    "youtube_comedy_min": Metric("youtube", "comedy videos", "min", "watch comedy videos",
                                 "your time on comedy videos"),
    "youtube_music_min": Metric("youtube", "music videos", "min", "watch music videos", "your time on music videos"),
    "wa_sent": Metric("whatsapp", "messages sent", "count", None, "the number of messages you send"),
    "wa_received": Metric("whatsapp", "messages received", "count", None, "the number of messages you receive"),
    "wa_late_night_share": Metric("whatsapp", "share of messages late at night", "share", None,
                                  "the share of your chat messages that are late at night"),
    "wa_active_chats": Metric("whatsapp", "active chats", "count", None, "the number of chats you're active in"),
    "wa_sentiment_mean": Metric("whatsapp", "the mood of your messages", "score", None, "the mood of your messages"),
    "wa_negative_share": Metric("whatsapp", "share of your messages that are negative", "share", None,
                                "the share of your messages that are negative"),
    "wa_others_sentiment_mean": Metric("whatsapp", "the mood of messages you receive", "score", None,
                                       "the mood of messages you receive"),
    "spend_total": Metric("bank", "total spend", "inr", None, "your total spend"),
    "spend_txn_count": Metric("bank", "payments", "count", None, "the number of payments you make"),
    "received_total": Metric("bank", "money received", "inr", "receive money", "the money you receive"),
    "food_delivery_spend": Metric("bank", "food delivery spend", "inr", "order food delivery",
                                  "your food delivery spend"),
    "discretionary_spend": Metric("bank", "discretionary spend", "inr", None, "your discretionary spend"),
    "entertainment_shopping_spend": Metric("bank", "entertainment & shopping spend", "inr",
                                           "spend on entertainment or shopping",
                                           "your entertainment & shopping spend"),
}

SOURCES = ["spotify", "youtube", "whatsapp", "bank"]


def source_of(m: str) -> str:
    return METRICS[m].source


def label(m: str) -> str:
    return METRICS[m].short


def subject(m: str) -> str:
    return METRICS[m].subject


def unit(m: str) -> str:
    return METRICS[m].unit


def fmt(m: str, v: float | None) -> str:
    """Value in plain units: 2.1h / 45 min, ₹1,240, 38%, 12, +0.21."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    u = unit(m)
    if u == "min":
        return f"{v / 60:.1f}h" if v >= 90 else f"{v:.0f} min"
    if u == "inr":
        return f"₹{v:,.0f}"
    if u == "share":
        return f"{v * 100:.0f}%"
    if u == "score":
        return f"{v:+.2f}"
    return f"{v:.0f}" if abs(v) >= 10 else f"{v:.1f}"


def strength(rho: float) -> str:
    """Plain-language strength of a rank correlation / effect size."""
    a = abs(rho)
    return "strong" if a >= 0.5 else "moderate" if a >= 0.3 else "weak"
