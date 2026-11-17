# Demo data (synthetic)

Everything in this folder is **generated**, not real. It's here to demo SelfScope without exposing anyone's private data.

- `spotify/StreamingHistory_music_*.json`: about 11.8k plays over one year, in Spotify's real "Account data" format
- `google/Takeout/YouTube and YouTube Music/history/watch-history.json`: about 7.8k entries in Google Takeout's real JSON format (newest first, about 5% are ads)
- `whatsapp/`: 5 chats, about 20.8k messages, from the user **Amogh**'s point of view, in WhatsApp's real export formats:
  - `WhatsApp Chat with Priya.txt` (close friend, ~6.5k), `WhatsApp Chat with Ishita.txt` (sister, ~1.7k), `WhatsApp Chat with CSE Batch 27.txt` (college group of 7, ~6.9k), `WhatsApp Chat with Varun.txt` (classmate, ~0.9k): **Android** format (`17/11/25, 9:41 pm - Name: text`, narrow no-break space before am/pm)
  - `WhatsApp Chat - Rohan.zip` (close friend, ~4.7k): **iOS** format, a .zip containing `_chat.txt` (`[17/11/25, 9:41:23 PM] Name: text`, U+200E marks on media/system lines)
  - English + Hinglish; includes media-omitted lines, deleted and edited messages, multi-line messages, and group system lines (created, added, left, icon/description changes)
  - Every text message comes from a clearly positive, neutral or negative pool, so sentiment models have signal

Date range: 17 Nov 2025 to 16 Nov 2026 (IST). Song and channel names are real; every play, timestamp, video title and video ID is generated. All WhatsApp names and messages are made up.

## Music mix
Bollywood 80%, English 10%, Kannada 10%. Mostly romantic and sad/breakup songs, with a few upbeat ones.

## Planted patterns (what the analysis should find)
1. **Exam weeks** (8–20 Dec 2025, 11–25 May 2026, 2–14 Nov 2026): more study videos, more late-night YouTube, a higher share of sad songs
2. **Weekends:** more music and comedy, with a later start to the day
3. **Late night (11 pm to 2 am):** sad songs are much more likely
4. **Semester breaks** (21 Dec–4 Jan, Jun–Jul 2026): more entertainment and more listening
5. **Song of the month:** one track is replayed heavily each month

### WhatsApp (same calendar)
- **Exam weeks:** more messages, much more late-night chatting (about 32% of messages between 11 pm and 2 am, vs about 7% normally), and about 43% negative/stressed messages (vs about 12%). The classmate chat (Varun) triples; the family chat stays out of late night
- **Weekends:** the group chat more than doubles (about 31 vs 14 messages a day); chatting starts later in the day
- **Semester breaks:** more active (about 69 vs 51 messages a day overall) and more positive (about 55% positive); the classmate chat goes quiet
- **Group membership:** Nikhil is added on 12 Jan 2026; Rahul leaves on 19 Jul 2026

## Regenerate
```
python ml/scripts/generate_demo_data.py --out data/samples --seed 42
```

Real exports go in `data/private/` (git-ignored), never here.
