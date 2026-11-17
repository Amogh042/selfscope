"""
SelfScope demo data generator.

Creates ONE YEAR of synthetic Spotify + YouTube history in the exact file formats
the real exports use, so the same parsers work on demo data and real data.

  Spotify  -> data/samples/spotify/StreamingHistory_music_N.json   (Account data format)
  YouTube  -> data/samples/google/Takeout/YouTube and YouTube Music/history/watch-history.json

All data is SYNTHETIC. Song and channel names are real so the demo looks natural,
but every play, timestamp, video title and video ID is generated.

Planted patterns (so the analysis has something real to find):
  1. Exam weeks      -> more study videos, more late-night YouTube, sadder music
  2. Weekends        -> more music + entertainment, later start to the day
  3. Late night      -> sad songs much more likely after 11 pm
  4. Semester break  -> more entertainment, more music overall
  5. "Song of the month" -> one track gets replayed heavily each month

Usage:  python ml/scripts/generate_demo_data.py [--out data/samples] [--seed 42]
"""

import argparse
import hashlib
import json
import os
import random
import string
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
START = date(2025, 11, 17)
END = date(2026, 11, 16)

EXAM_WEEKS = [(date(2025, 12, 8), date(2025, 12, 20)),
              (date(2026, 5, 11), date(2026, 5, 25)),
              (date(2026, 11, 2), date(2026, 11, 14))]
BREAKS = [(date(2025, 12, 21), date(2026, 1, 4)),
          (date(2026, 6, 1), date(2026, 7, 31))]

# ---------------------------------------------------------------- songs
# (track, primary artist, mood)  mood: R = romantic, S = sad/breakup, U = upbeat
BOLLYWOOD = [
    ("Tum Hi Ho", "Arijit Singh", "R"), ("Raabta", "Arijit Singh", "R"),
    ("Kesariya", "Arijit Singh", "R"), ("Tera Ban Jaunga", "Akhil Sachdeva", "R"),
    ("Pehla Nasha", "Udit Narayan", "R"), ("Tum Se Hi", "Mohit Chauhan", "R"),
    ("Raataan Lambiyan", "Jubin Nautiyal", "R"), ("Shayad", "Arijit Singh", "R"),
    ("Pee Loon", "Mohit Chauhan", "R"), ("Gerua", "Arijit Singh", "R"),
    ("Hawayein", "Arijit Singh", "R"), ("Apna Bana Le", "Arijit Singh", "R"),
    ("Tere Vaaste", "Varun Jain", "R"), ("Ve Kamleya", "Arijit Singh", "R"),
    ("Satranga", "Arijit Singh", "R"), ("Jeene Laga Hoon", "Atif Aslam", "R"),
    ("Tera Hone Laga Hoon", "Atif Aslam", "R"), ("Kabira", "Tochi Raina", "R"),
    ("Ilahi", "Arijit Singh", "R"), ("Sanam Re", "Arijit Singh", "R"),
    ("Zaalima", "Arijit Singh", "R"), ("Tujh Mein Rab Dikhta Hai", "Roop Kumar Rathod", "R"),
    ("O Maahi", "Arijit Singh", "R"), ("Heeriye", "Jasleen Royal", "R"),
    ("Chaleya", "Arijit Singh", "R"), ("Tum Kya Mile", "Arijit Singh", "R"),
    ("Tum Jo Aaye", "Rahat Fateh Ali Khan", "R"), ("O Saathi", "Atif Aslam", "R"),
    ("Main Rang Sharbaton Ka", "Atif Aslam", "R"), ("Tujhe Kitna Chahne Lage", "Arijit Singh", "R"),
    ("Channa Mereya", "Arijit Singh", "S"), ("Agar Tum Saath Ho", "Alka Yagnik", "S"),
    ("Phir Bhi Tumko Chaahunga", "Arijit Singh", "S"), ("Kalank", "Arijit Singh", "S"),
    ("Hamari Adhuri Kahani", "Arijit Singh", "S"), ("Tadap Tadap", "KK", "S"),
    ("Tujhe Bhula Diya", "Mohit Chauhan", "S"), ("Bhula Dena", "Mustafa Zahid", "S"),
    ("Lambiyaan Si Judaiyaan", "Arijit Singh", "S"), ("Main Dhoondne Ko Zamaane Mein", "Arijit Singh", "S"),
    ("Khairiyat", "Arijit Singh", "S"), ("Humnava Mere", "Jubin Nautiyal", "S"),
    ("Ae Dil Hai Mushkil", "Arijit Singh", "S"), ("Achha Chalta Hoon", "Arijit Singh", "S"),
    ("Bekhayali", "Sachet Tandon", "S"), ("Mere Bina", "Nikhil D'Souza", "S"),
    ("Tujhe Bhoolna Toh Chaaha", "Jubin Nautiyal", "S"), ("Dil Ibaadat", "KK", "S"),
    ("Badtameez Dil", "Benny Dayal", "U"), ("Kala Chashma", "Amar Arshi", "U"),
    ("The Breakup Song", "Arijit Singh", "U"), ("Kar Gayi Chull", "Badshah", "U"),
]
ENGLISH = [
    ("Perfect", "Ed Sheeran", "R"), ("All of Me", "John Legend", "R"),
    ("Photograph", "Ed Sheeran", "R"), ("Love Story", "Taylor Swift", "R"),
    ("Until I Found You", "Stephen Sanchez", "R"), ("Night Changes", "One Direction", "R"),
    ("Say You Won't Let Go", "James Arthur", "R"),
    ("Someone Like You", "Adele", "S"), ("Let Her Go", "Passenger", "S"),
    ("Happier", "Ed Sheeran", "S"), ("drivers license", "Olivia Rodrigo", "S"),
    ("When I Was Your Man", "Bruno Mars", "S"), ("lovely", "Billie Eilish", "S"),
    ("Too Good At Goodbyes", "Sam Smith", "S"),
]
KANNADA = [
    ("Belageddu", "Vijay Prakash", "R"), ("Bombe Helutaite", "Vijay Prakash", "R"),
    ("Anisuthide", "Sonu Nigam", "R"), ("Mungaru Maleye", "Sonu Nigam", "R"),
    ("Minchagi Neenu Baralu", "Sonu Nigam", "R"), ("Jagave Neenu Gelathiye", "Sid Sriram", "R"),
    ("Onde Samane", "Sonu Nigam", "R"), ("Mugulu Nage", "Sonu Nigam", "S"),
    ("Nenapina Hudugiye", "Vijay Prakash", "R"), ("Shrungarada Honge Mara", "Vijay Prakash", "R"),
    ("Saaluthillave", "Shreya Ghoshal", "R"), ("Sariyaagi", "Armaan Malik", "R"),
    ("Arere Avala Naguva", "Vasuki Vaibhav", "R"),
]
LANG_WEIGHTS = [("hi", BOLLYWOOD, 0.80), ("en", ENGLISH, 0.10), ("kn", KANNADA, 0.10)]
PICK_WEIGHTS = [0.78, 0.11, 0.11]  # slightly under 80% because "song of the month" is always Bollywood

# ---------------------------------------------------------------- youtube
CHANNELS = {
    "study": ["CodeWithHarry", "Apna College", "freeCodeCamp.org", "StatQuest with Josh Starmer",
              "Krish Naik", "3Blue1Brown", "Fireship", "Gate Smashers", "Neso Academy", "Telusko"],
    "comedy": ["BB Ki Vines", "Zakir Khan", "Samay Raina", "Tanmay Bhat", "Ashish Chanchlani Vines",
               "Danish Sait", "MostlySane"],
    "tech": ["Technical Guruji", "Marques Brownlee", "Trakin Tech", "Mrwhosetheboss"],
    "podcast": ["BeerBiceps", "Raj Shamani", "Nikhil Kamath"],
    "finance": ["Ankur Warikoo", "CA Rachana Phadke Ranade"],
    "music": ["T-Series", "Sony Music India", "Saregama Music", "Anand Audio"],
}
STUDY_TOPICS = ["Python", "DBMS", "Operating Systems", "pandas", "Machine Learning", "Linear Regression",
                "React", "SQL Joins", "Computer Networks", "Data Structures", "Probability",
                "Statistics for Data Science", "Power BI", "Tableau", "Git", "Docker", "NumPy",
                "Logistic Regression", "Random Forest", "Normalization in DBMS", "Deadlocks"]
STUDY_TPL = ["{t} in One Shot", "{t} Explained Simply", "{t} Tutorial for Beginners",
             "{t} | Complete Course", "{t} Interview Questions", "Learn {t} in 1 Hour"]
COMEDY_TPL = ["Stand-up Comedy | Episode {n}", "When Your Friend {x}", "Crowd Work Special #{n}",
              "Funny Moments Compilation {n}", "Reacting to {x}"]
COMEDY_X = ["Borrows Money", "Gets Placed", "Has Exams Tomorrow", "Joins the Gym", "Starts Trading",
            "Old Bollywood Songs", "Engineering Life", "Hostel Food"]
TECH_TPL = ["{p} Review: Worth It?", "{p} Unboxing", "Best Phones Under {n}k", "{p} vs {q}"]
PHONES = ["iPhone 17", "Pixel 10", "Galaxy S26", "OnePlus 14", "Nothing Phone 3", "MacBook Air M4"]
PODCAST_TPL = ["Ep. {n}: {x}", "{x} | Full Podcast", "{x} ft. Guest"]
PODCAST_X = ["Startups in India", "Money Habits in Your 20s", "AI and Jobs", "Discipline & Focus",
             "Building a Career", "Fitness Basics"]
FIN_TPL = ["How to Save Your First 1 Lakh", "Mutual Funds for Beginners", "Budgeting as a Student",
           "SIP Explained", "Credit Cards: Good or Bad?"]
ADS = ["New Phone Launch Offer", "Online Course Sale", "Food Delivery Deal", "Shoe Sale Ad"]


def in_ranges(d, ranges):
    return any(a <= d <= b for a, b in ranges)


def song_duration_ms(track):
    h = int(hashlib.md5(track.encode()).hexdigest(), 16)
    return (180 + h % 150) * 1000


def vid_id(rng):
    return "".join(rng.choice(string.ascii_letters + string.digits + "-_") for _ in range(11))


def chan_id(name):
    return "UC" + hashlib.sha1(name.encode()).hexdigest()[:22]


def pick_hour(rng, weekend, exam):
    # IST hour weights: morning commute, evening peak, some late night
    w = {h: 0.3 for h in range(24)}
    for h in (8, 9): w[h] = 2.0
    for h in range(18, 23): w[h] = 3.0
    w[23] = 2.5; w[0] = 1.8; w[1] = 1.0; w[2] = 0.4
    for h in (3, 4, 5, 6): w[h] = 0.05
    if weekend:
        for h in (8, 9): w[h] = 0.6
        for h in range(11, 17): w[h] = 1.8
    if exam:
        w[0] = 3.0; w[1] = 2.2; w[2] = 1.2
    hours, weights = zip(*w.items())
    return rng.choices(hours, weights)[0]


def gen_spotify(rng):
    plays = []
    monthly_fav = {}
    d = START
    while d <= END:
        weekend = d.weekday() >= 5
        exam, brk = in_ranges(d, EXAM_WEEKS), in_ranges(d, BREAKS)
        n = rng.randint(18, 38) + (10 if weekend else 0) + (8 if brk else 0)
        key = (d.year, d.month)
        if key not in monthly_fav:
            monthly_fav[key] = rng.choice(BOLLYWOOD[:30])
        for _ in range(n):
            hour = pick_hour(rng, weekend, exam)
            late = hour >= 23 or hour <= 2
            p_sad = 0.22 + (0.30 if exam else 0) + (0.25 if late else 0)
            if rng.random() < 0.10:
                track = monthly_fav[key]
            else:
                lang_pool = rng.choices([p for _, p, _ in LANG_WEIGHTS], PICK_WEIGHTS)[0]
                r = rng.random()
                mood = "S" if r < p_sad else ("U" if r > 0.93 else "R")
                pool = [s for s in lang_pool if s[2] == mood] or lang_pool
                track = rng.choice(pool)
            dur = song_duration_ms(track[0])
            r = rng.random()
            ms = rng.randint(1500, 29000) if r < 0.12 else (int(dur * rng.uniform(0.3, 0.9)) if r < 0.25 else dur - rng.randint(0, 3000))
            t = datetime(d.year, d.month, d.day, hour, rng.randint(0, 59), rng.randint(0, 59), tzinfo=IST)
            plays.append((t, track, ms))
        d += timedelta(days=1)
    plays.sort(key=lambda p: p[0])
    return [{"endTime": t.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M"),
             "artistName": tr[1], "trackName": tr[0], "msPlayed": ms} for t, tr, ms in plays]


def yt_title(rng, cat):
    if cat == "study":
        return rng.choice(STUDY_TPL).format(t=rng.choice(STUDY_TOPICS))
    if cat == "comedy":
        return rng.choice(COMEDY_TPL).format(n=rng.randint(1, 60), x=rng.choice(COMEDY_X))
    if cat == "tech":
        a, b = rng.sample(PHONES, 2)
        return rng.choice(TECH_TPL).format(p=a, q=b, n=rng.choice([15, 20, 30, 50]))
    if cat == "podcast":
        return rng.choice(PODCAST_TPL).format(n=rng.randint(100, 450), x=rng.choice(PODCAST_X))
    if cat == "finance":
        return rng.choice(FIN_TPL)
    raise ValueError("music handled in gen_youtube")


def gen_youtube(rng):
    entries = []
    d = START
    while d <= END:
        weekend = d.weekday() >= 5
        exam, brk = in_ranges(d, EXAM_WEEKS), in_ranges(d, BREAKS)
        sessions = rng.randint(2, 4) + (1 if weekend or brk else 0) + (1 if exam else 0)
        for _ in range(sessions):
            hour = pick_hour(rng, weekend, exam)
            t = datetime(d.year, d.month, d.day, hour, rng.randint(0, 59), rng.randint(0, 59), tzinfo=IST)
            weights = {"study": 0.25, "comedy": 0.22, "tech": 0.10, "podcast": 0.12, "finance": 0.06, "music": 0.25}
            if exam: weights.update(study=0.60, comedy=0.15)
            if brk or weekend: weights.update(comedy=0.35, study=0.10)
            for _ in range(rng.randint(3, 9)):
                if rng.random() < 0.05:
                    entries.append({"header": "YouTube", "title": "Watched " + rng.choice(ADS),
                                    "titleUrl": f"https://www.youtube.com/watch?v={vid_id(rng)}",
                                    "time": t.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                                    "products": ["YouTube"], "details": [{"name": "From Google Ads"}],
                                    "activityControls": ["Web & App Activity", "YouTube watch history"]})
                else:
                    cat = rng.choices(list(weights), list(weights.values()))[0]
                    if cat == "music":  # music videos match the Spotify taste; Kannada songs on a Kannada label
                        kn = rng.random() < 0.15
                        song = rng.choice(KANNADA if kn else BOLLYWOOD)
                        ch = "Anand Audio" if kn else rng.choice(["T-Series", "Sony Music India", "Saregama Music"])
                        title = f"{song[0]} | {song[1]} | Full Video Song"
                    else:
                        ch = rng.choice(CHANNELS[cat])
                        title = yt_title(rng, cat)
                    entries.append({"header": "YouTube", "title": "Watched " + title,
                                    "titleUrl": f"https://www.youtube.com/watch?v={vid_id(rng)}",
                                    "subtitles": [{"name": ch, "url": f"https://www.youtube.com/channel/{chan_id(ch)}"}],
                                    "time": t.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                                    "products": ["YouTube"], "activityControls": ["YouTube watch history"]})
                t += timedelta(minutes=rng.choice([1, 2, 4, 6, 9, 12, 15, 22]), seconds=rng.randint(0, 59), milliseconds=rng.randint(0, 999))
        d += timedelta(days=1)
    entries.sort(key=lambda e: e["time"], reverse=True)  # Takeout lists newest first
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/samples")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rng = random.Random(a.seed)

    sp = gen_spotify(rng)
    sp_dir = os.path.join(a.out, "spotify")
    os.makedirs(sp_dir, exist_ok=True)
    for i in range(0, len(sp), 10000):  # Spotify splits files every 10k rows
        with open(os.path.join(sp_dir, f"StreamingHistory_music_{i // 10000}.json"), "w", encoding="utf-8") as f:
            json.dump(sp[i:i + 10000], f, ensure_ascii=False, indent=2)

    yt = gen_youtube(rng)
    yt_dir = os.path.join(a.out, "google", "Takeout", "YouTube and YouTube Music", "history")
    os.makedirs(yt_dir, exist_ok=True)
    with open(os.path.join(yt_dir, "watch-history.json"), "w", encoding="utf-8") as f:
        json.dump(yt, f, ensure_ascii=False, indent=2)

    print(f"Spotify plays: {len(sp):,}  |  YouTube entries: {len(yt):,}  |  {START} to {END}")


if __name__ == "__main__":
    main()
