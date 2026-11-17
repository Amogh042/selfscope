# Demo data (synthetic)

Everything in this folder is **generated**, not real. It's here to demo SelfScope without exposing anyone's private data.

- `spotify/StreamingHistory_music_*.json`: about 11.8k plays over one year, in Spotify's real "Account data" format
- `google/Takeout/YouTube and YouTube Music/history/watch-history.json`: about 7.8k entries in Google Takeout's real JSON format (newest first, about 5% are ads)

Date range: 17 Nov 2025 to 16 Nov 2026 (IST). Song and channel names are real; every play, timestamp, video title and video ID is generated.

## Music mix
Bollywood 80%, English 10%, Kannada 10%. Mostly romantic and sad/breakup songs, with a few upbeat ones.

## Planted patterns (what the analysis should find)
1. **Exam weeks** (8–20 Dec 2025, 11–25 May 2026, 2–14 Nov 2026): more study videos, more late-night YouTube, a higher share of sad songs
2. **Weekends:** more music and comedy, with a later start to the day
3. **Late night (11 pm to 2 am):** sad songs are much more likely
4. **Semester breaks** (21 Dec–4 Jan, Jun–Jul 2026): more entertainment and more listening
5. **Song of the month:** one track is replayed heavily each month

## Regenerate
```
python ml/scripts/generate_demo_data.py --out data/samples --seed 42
```

Real exports go in `data/private/` (git-ignored), never here.
