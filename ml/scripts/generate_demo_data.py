"""
SelfScope demo data generator.

Creates ONE YEAR of synthetic Spotify + YouTube history in the exact file formats
the real exports use, so the same parsers work on demo data and real data.

  Spotify  -> data/samples/spotify/StreamingHistory_music_N.json   (Account data format)
  YouTube  -> data/samples/google/Takeout/YouTube and YouTube Music/history/watch-history.json
  WhatsApp -> data/samples/whatsapp/WhatsApp Chat with <Name>.txt  (Android, 4 chats)
              data/samples/whatsapp/WhatsApp Chat - Rohan.zip      (iOS, _chat.txt inside)
  Bank     -> data/samples/bank/SBI_statement_demo.xlsx         (SBI Excel statement)
              ml/data/demo_bank_truth.csv  (true category per row; answer key, not used by the app)
  Periods  -> data/samples/periods.json (exam weeks, pre-tagged in the DEMO database)
  Answer key for sentiment: ml/data/demo_whatsapp_truth.csv (true pos/neu/neg per text message)

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
import io
import json
import os
import random
import string
import zipfile
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


# ---------------------------------------------------------------- whatsapp
# Five synthetic chats from the user's ("Amogh") point of view. Uses its own RNG stream
# (seeded from --seed) so adding WhatsApp did not change the Spotify / YouTube output.
# Sentiment is kept clear-cut (positive / neutral / negative pools) so it is learnable.
WA_ME = "Amogh"
WA_LRM = "‎"
WA_GROUP = "CSE Batch 27"
WA_CHATS = [
    # name, kind, other members, platform, base msgs/day,
    # multipliers on volume for (weekend, exam, break)
    dict(name="Priya", kind="friend", members=["Priya"], platform="android", per_day=15,
         mult=(1.3, 1.15, 1.5)),
    dict(name="Rohan", kind="friend", members=["Rohan"], platform="ios", per_day=11,
         mult=(1.3, 1.15, 1.5)),
    dict(name="Ishita", kind="family", members=["Ishita"], platform="android", per_day=4.5,
         mult=(1.2, 1.3, 1.3)),
    dict(name=WA_GROUP, kind="group",
         members=["Karthik", "Sneha", "Aditi", "Rahul", "Divya", "Nikhil"], platform="android",
         per_day=13, mult=(2.2, 1.5, 1.4)),
    dict(name="Varun", kind="classmate", members=["Varun"], platform="android", per_day=3,
         mult=(0.6, 3.0, 0.5)),
]
# Group membership changes (made visible as system lines)
WA_JOINS = {"Nikhil": date(2026, 1, 12)}
WA_LEAVES = {"Rahul": date(2026, 7, 20)}

WA_POS = ["hahaha 😂", "lmaooo", "sahi hai bhai 🔥", "best day ever yaar", "omg yesss", "love this 😍",
          "mast tha yaar", "thank youuu ❤️", "you're the best", "chal party karte hai 🎉",
          "bhai kya scene tha kal 😂😂", "finally weekend!!", "so happy rn", "that movie was sooo good",
          "hahaha dead 💀", "proud of you yaar", "let's gooo", "kal ka plan fix 🙌", "best biryani ever",
          "yay!!", "ekdum mast", "bahut maza aaya", "can't stop laughing 😂", "good vibes only ✨",
          "missed you yaar ❤️", "wohooo", "this is amazing", "aaj ka din accha tha", "masti time 😎",
          "cutest thing ever 🥹", "result accha aaya!! 🥳", "you made my day"]
WA_NEU = ["ok", "okk", "haan", "hmm", "kab aa raha?", "where are you", "on my way", "kal baat karte",
          "kya scene hai", "done", "acha", "theek hai", "what time?", "6 baje?", "call kar", "free ho?",
          "ya", "k", "bhej de", "dekhta hu", "will check", "brb", "kahan hai", "reached",
          "abhi nahi, baad me", "lunch kiya?", "kya kar raha", "nothing much", "same",
          "tell me when you're free", "link bhej", "class hai kal?", "chal theek", "1 min", "haan bol"]
WA_NEG = ["ugh", "worst day", "I'm so tired", "kuch acha nahi lag raha", "feeling low yaar",
          "bohot bura hua", "not in the mood", "can't sleep", "sab kharab ho gaya", "I hate this",
          "bas yaar, thak gaya", "mood off hai", "so annoyed rn", "kitna boring hai sab",
          "headache ho raha hai", "kuch nahi ho raha mujhse", "this sucks", "sad hu thoda",
          "please don't ask 😞", "really upset today"]
WA_EXAM_NEG = ["bohot stress ho raha hai", "kuch padha nahi abhi tak 😭", "kal ka paper gaya",
               "mujhse nahi hoga ye", "bhai fail ho jaunga", "syllabus khatam hi nahi ho raha",
               "3 baj gaye aur abhi 2 units baaki", "I'm so stressed", "panicking rn",
               "can't focus at all", "DBMS samajh nahi aa raha 😩", "neend aa rahi hai but padhna hai",
               "worst paper ever", "I'm going to fail OS", "zero motivation", "anxiety ho rahi hai",
               "itna syllabus kaise hoga", "brain dead 💀", "paper bahut tough tha",
               "regretting not studying earlier"]
WA_STUDY_NEU = ["notes bhej de", "kal kaunsa paper hai?", "syllabus me unit 4 hai?", "important questions?",
                "PYQ ka link?", "kitne baje reporting?", "hall ticket print kiya?", "calculator allowed hai?",
                "which room?", "unit 3 kar raha hu", "revision kar le", "formula sheet bhej",
                "kal library chal", "pdf bhej diya", "chapter 5 ka summary?", "assignment submit kiya?",
                "lab record complete?", "viva me kya pucha?"]
WA_BREAK_POS = ["goa trip confirmed!! 🏖️", "ghar aake mast lag raha", "sleeping till 11 every day 😌",
                "bhai trip pe chalein?", "netflix marathon tonight 🍿", "holidays best hai",
                "no assignments, pure bliss", "beach pe hai abhi 🌊", "mummy ke haath ka khana ❤️",
                "road trip plan karte", "finally free!!", "chill mode on 😎"]
WA_FAMILY = {
    "pos": ["love you ❤️", "miss you!", "proud of you 🥹", "all the best for exam! 👍", "great news!!",
            "so happy for you", "mummy says hi 😊", "Diwali pe aa raha na? 🪔", "come home soon ❤️",
            "you did great"],
    "neu": ["khana khaya?", "kab aa raha ghar?", "call karna free hoke", "ok", "haan", "paise bhej diye",
            "ticket book kar di", "mummy ka call utha", "kal baat karte", "reached hostel?", "theek hai",
            "kya kar raha", "photos bhej", "papa ko bata diya"],
    "neg": ["call kyu nahi utha raha?", "itna late kyu jag raha hai?", "mummy worried hai",
            "tabiyat theek nahi hai", "too much stress, take care 😟", "why are you so upset?",
            "sad news, nani ki tabiyat kharab hai"],
}
WA_GROUP_EXTRA = {
    "pos": ["party at Karthik's 🎉", "bunk maarte hai aaj 😂", "who's coming for movie?",
            "happy birthday!! 🎂🎉", "hahaha this meme 💀", "squad goals", "trip photos!!!",
            "aaj ka fest was lit 🔥"],
    "neu": ["anyone has notes?", "class cancelled?", "attendance laga do", "assignment deadline kab hai?",
            "kal lab hai?", "kaun aa raha canteen?", "poll: friday movie?", "sir ne kya bola?",
            "timetable bhejo", "kitne baje?"],
    "neg": ["attendance shortage aa gaya 😭", "worst lecture ever", "internals me kam marks aaye",
            "who else is dying rn", "assignment kal hai and I haven't started",
            "bhai ye semester kharab hai"],
}
WA_MULTILINE = ["things to bring:\n1. charger\n2. notes\n3. ID card",
                "kal ka plan:\n10 baje library\n1 baje lunch\n4 baje movie",
                "unit 3 important:\n- deadlocks\n- paging\n- scheduling",
                "happy birthday!! 🎂\nhave the best year\nparty kab hai? 😂",
                "bro listen\nI'm not coming today\nwill explain later",
                "assignment questions:\nQ1 normalization\nQ2 ER diagram\nQ3 SQL joins",
                "ok so\nsorry for yesterday\nwas really stressed 😞"]
WA_IOS_MEDIA = ["image omitted", "image omitted", "sticker omitted", "video omitted", "audio omitted",
                "GIF omitted", "document omitted"]


def wa_hour(rng, kind, weekend, exam):
    """IST hour weights for chatting. Exams push activity into 11 pm - 2 am."""
    w = {h: 0.02 for h in range(24)}
    for h in (7, 8, 9): w[h] = 1.0
    for h in range(10, 18): w[h] = 1.2
    for h in range(18, 23): w[h] = 3.0
    w[23], w[0], w[1], w[2] = 1.4, 0.6, 0.2, 0.05
    if weekend:
        for h in (7, 8, 9): w[h] = 0.3
        for h in range(11, 18): w[h] = 2.0
    if exam and kind != "family":
        w[23], w[0], w[1], w[2] = 4.5, 4.0, 3.0, 1.5
    if kind == "family":
        w[23], w[0], w[1], w[2] = 0.3, 0.05, 0.02, 0.02
    hours, weights = zip(*w.items())
    return rng.choices(hours, weights)[0]


def wa_sentiment(rng, exam, brk, weekend, late):
    if exam:
        p = (0.10, 0.38, 0.52) if late else (0.12, 0.45, 0.43)
    elif brk:
        p = (0.58, 0.36, 0.06)
    elif weekend:
        p = (0.42, 0.48, 0.10)
    else:
        p = (0.30, 0.55, 0.15)
    return rng.choices(["pos", "neu", "neg"], p)[0]


# True sentiment of each multi-line template (single-line texts take the label of their pool).
WA_MULTILINE_LABELS = ["neu", "neu", "neu", "pos", "neu", "neu", "neg"]


def wa_text(rng, kind, sentiment, exam, brk):
    """-> (text, true sentiment label). The label is bookkeeping only: it uses no randomness,
    so recording it does not change any generated file."""
    if rng.random() < 0.015:
        text = rng.choice(WA_MULTILINE)
        return text, WA_MULTILINE_LABELS[WA_MULTILINE.index(text)]
    if kind == "family":
        return rng.choice(WA_FAMILY[sentiment]), sentiment
    pools = {"pos": WA_POS + (WA_BREAK_POS * 2 if brk else []),
             "neu": WA_NEU + (WA_STUDY_NEU * (3 if exam else 1) if kind in ("classmate", "group") or exam else []),
             "neg": WA_NEG + (WA_EXAM_NEG * 3 if exam else [])}
    if kind == "group" and rng.random() < 0.35:
        return rng.choice(WA_GROUP_EXTRA[sentiment]), sentiment
    if kind == "classmate" and sentiment == "neu":
        return rng.choice(WA_STUDY_NEU), "neu"
    return rng.choice(pools[sentiment]), sentiment


def wa_line(platform, t, sender, body, marked=False):
    h12 = t.hour % 12 or 12
    if platform == "ios":
        stamp = f"[{t:%d/%m/%y}, {h12}:{t:%M:%S} {'AM' if t.hour < 12 else 'PM'}]"
        prefix = WA_LRM if marked else ""
        return f"{prefix}{stamp} {sender}: {WA_LRM if marked else ''}{body}"
    stamp = f"{t:%d/%m/%y}, {h12}:{t:%M} {'am' if t.hour < 12 else 'pm'}"
    return f"{stamp} - {sender}: {body}" if sender else f"{stamp} - {body}"


def wa_members_on(chat, d):
    return [m for m in chat["members"]
            if WA_JOINS.get(m, START) <= d and d < WA_LEAVES.get(m, END + timedelta(days=1))]


def gen_whatsapp_chat(rng, chat):
    kind, platform = chat["kind"], chat["platform"]
    end_ts = datetime(END.year, END.month, END.day, 23, 59, 59)
    msgs = []  # (naive IST datetime, sender, body, marked)
    d = START
    while d <= END:
        weekend = d.weekday() >= 5
        exam, brk = in_ranges(d, EXAM_WEEKS), in_ranges(d, BREAKS)
        mw, me, mb = chat["mult"]
        expected = chat["per_day"] * (mw if weekend else 1) * (me if exam else 1) * (mb if brk else 1)
        target = max(0, int(rng.gauss(expected, expected * 0.35)))
        members = wa_members_on(chat, d)
        weights = [1.0 + i * 0.4 for i in range(len(members))][::-1]
        made = 0
        while made < target:
            hour = wa_hour(rng, kind, weekend, exam)
            t = datetime(d.year, d.month, d.day, hour, rng.randint(0, 59), rng.randint(0, 59))
            sender = WA_ME if rng.random() < 0.5 else rng.choices(members, weights)[0]
            for _ in range(min(rng.randint(3, 12), target - made)):
                late = t.hour >= 23 or t.hour <= 2
                r = rng.random()
                media_p = {"friend": 0.05, "group": 0.07, "family": 0.06, "classmate": 0.03}[kind]
                mine = sender == WA_ME
                if r < 0.004:
                    body = (("You deleted this message" if mine else "This message was deleted")
                            + ("." if platform == "ios" else ""))
                    msgs.append((t, sender, body, platform == "ios", None))
                elif r < 0.004 + media_p:
                    if platform == "ios":
                        msgs.append((t, sender, rng.choice(WA_IOS_MEDIA), True, None))
                    else:
                        msgs.append((t, sender, "<Media omitted>", False, None))
                else:
                    body, label = wa_text(rng, kind, wa_sentiment(rng, exam, brk, weekend, late), exam, brk)
                    truth = (label, body)
                    if rng.random() < 0.005:
                        body += (f" {WA_LRM}<This message was edited>" if platform == "ios"
                                 else " <This message was edited>")
                    msgs.append((t, sender, body, False, truth))
                made += 1
                t += timedelta(seconds=rng.choice([4, 9, 15, 25, 40, 60, 90, 150, 300]) + rng.randint(0, 20))
                if rng.random() < (0.4 if kind != "group" else 0.25):
                    pass  # double-text: same sender again
                elif kind == "group":
                    sender = rng.choice([WA_ME] + members)
                else:
                    sender = members[0] if sender == WA_ME else WA_ME
        d += timedelta(days=1)

    msgs = sorted((m for m in msgs if m[0] <= end_ts), key=lambda m: m[0])
    first = msgs[0][0]
    lines = []
    if platform == "ios":
        lines.append(wa_line("ios", first, chat["members"][0],
                             "Messages and calls are end-to-end encrypted. No one outside of this chat, "
                             "not even WhatsApp, can read or listen to them.", marked=True))
    else:
        lines.append(wa_line("android", first, None,
                             "Messages and calls are end-to-end encrypted. Only people in this chat can "
                             "read, listen to, or share them. Learn more."))
    system = []
    if kind == "group":
        created = datetime(START.year, START.month, START.day, 0, 0, 0)
        system += [(created, f'Karthik created group "{chat["name"]}"'), (created, "Karthik added you")]
        system += [(datetime(j.year, j.month, j.day, 10, 2), f"Karthik added {m}") for m, j in WA_JOINS.items()]
        system += [(datetime(l.year, l.month, l.day, 0, 0) - timedelta(minutes=13), f"{m} left")
                   for m, l in WA_LEAVES.items()]
        system += [(datetime(2026, 1, 3, 18, 30), "Aditi changed this group's icon"),
                   (datetime(2026, 8, 3, 9, 15), "Sneha changed the group description")]
        lines[0] = wa_line("android", created, None, lines[0].split(" - ", 1)[1])
    events = [(t, None, s, False, None) for t, s in system] + msgs
    events.sort(key=lambda e: e[0])
    for t, sender, body, marked, _ in events:
        lines.append(wa_line(platform, t, sender, body, marked))
    truth = [(t, sender, tr[0], tr[1]) for t, sender, _, _, tr in msgs if tr]
    return lines, len(msgs), truth


def gen_whatsapp(seed):
    """-> {filename: bytes}, {chat name: message count}"""
    rng = random.Random(f"{seed}:whatsapp")
    files, counts, truth = {}, {}, []
    for chat in WA_CHATS:
        lines, n, chat_truth = gen_whatsapp_chat(rng, chat)
        truth += [(chat["name"], *x) for x in chat_truth]
        text = ("\n".join(lines) + "\n").encode("utf-8")
        counts[chat["name"]] = n
        if chat["platform"] == "ios":  # iOS exports: a .zip containing _chat.txt
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(zipfile.ZipInfo("_chat.txt", date_time=(2026, 11, 16, 23, 59, 0)), text,
                            compress_type=zipfile.ZIP_DEFLATED)
            files[f"WhatsApp Chat - {chat['name']}.zip"] = buf.getvalue()
        else:
            files[f"WhatsApp Chat with {chat['name']}.txt"] = text
    return files, counts, truth


# ---------------------------------------------------------------- bank (SBI Excel statement)
# One year of a student's SBI savings account, written like an OnlineSBI Excel download.
# Own RNG stream ("<seed>:bank") so the other demo files stay byte-identical.
# Every merchant/person name, UPI ID, phone number and reference number is made up.
BK_OPENING = 12000.00
BK_LOW = 3500.00  # below this, extras are skipped (about 9 days of routine)
BK_PARENT = ("SURESH KUMAR", "sureshkumar1968@sbi", "SBIN")
BK_SNACKS = [  # (name, vpa, bank code, weight) — repeat tea/snack vendors (paytmqr-style)
    ("SRI LAKSHMI TEA STALL", "paytmqr281005050101lak9@paytm", "PYTM", 5),
    ("RAJU TEA POINT", "paytmqr1y7xk0qz9a@paytm", "PYTM", 4),
    ("CAMPUS BAKERY", "paytmqr281005050101cmpb@paytm", "PYTM", 3),
    ("NANDINI MILK PARLOUR", "paytmqr6h2k9d1mz@paytm", "PYTM", 2),
    ("MANJU CONDIMENTS", "paytmqr5p8c3x0nb@paytm", "PYTM", 2),
    ("IYENGAR BAKERY", "q839201745@ybl", "YESB", 2),
]
BK_LUNCH = [("MAIN CANTEEN", "paytmqr28100505mcan@paytm", "PYTM", 5),
            ("ANNAPOORNA MESS", "annapoornamess@okaxis", "UTIB", 3),
            ("HOTEL NALAPAKA", "nalapakahotel@icici", "ICIC", 1)]
BK_DINNER = [("SRI SAI DARSHINI", "q492018377@ybl", "YESB", 4),
             ("DAKSHIN MESS", "dakshinmess@oksbi", "SBIN", 3),
             ("HOTEL NALAPAKA", "nalapakahotel@icici", "ICIC", 2),
             ("UDUPI GRAND", "udupigrand@hdfcbank", "HDFC", 1)]
BK_AUTO = [("RAPIDO", "rapido.upi@axisbank", "UTIB", 4),
           ("MUNIRAJU", "9845012736@ybl", "YESB", 3),     # local autos pay to phone-number VPAs
           ("VENKATESH K", "9880645213@paytm", "PYTM", 2),
           ("SHIVANNA", "7259031846@ybl", "YESB", 1)]
BK_DELIVERY = [("SWIGGY", "swiggy.stores@axb", "UTIB", 1), ("ZOMATO", "zomato.order@hdfcbank", "HDFC", 1)]
BK_QCOMM = [("ZEPTO MARKETPLACE", "zeptomarketplace@ybl", "YESB", 1), ("BLINKIT", "blinkit.payu@hdfcbank", "HDFC", 1)]
BK_METRO = ("BMRCL", "bmrcl.qr@icici", "ICIC")
BK_SHOPPING = [("AMAZON PAY", "amazonupi@apl", "UTIB", 3), ("FLIPKART", "flipkart.payu@axisbank", "UTIB", 2),
               ("MYNTRA DESIGNS", "myntra.payu@hdfcbank", "HDFC", 1)]
BK_FUN = [("BOOKMYSHOW", "bookmyshow@icici", "ICIC", 2, (180, 450)),        # movies
          ("THIRD WAVE COFFEE", "thirdwave.cafe@ybl", "YESB", 2, (180, 380)),  # cafe outings
          ("CHAI POINT", "chaipoint@icici", "ICIC", 1, (90, 220)),
          ("CAFE COFFEE DAY", "ccd.upi@axisbank", "UTIB", 1, (150, 320))]
BK_RECHARGE = ("RELIANCE JIO", "jiorecharge@icici", "ICIC")
BK_MANDATES = [("SPOTIFY", 119, 5), ("NETFLIX", 199, 12)]  # name, amount, day of month
# Friends = the same people as the demo WhatsApp chats (Varun is the classmate).
BK_FRIENDS = [("PRIYA SHARMA", "priyasharma@okhdfcbank", "HDFC", 4), ("ROHAN KUMAR", "rohank98@okicici", "ICIC", 4),
              ("VARUN RAO", "varunrao@oksbi", "SBIN", 2), ("KARTHIK S", "karthik.s@ybl", "YESB", 2),
              ("SNEHA M", "sneham@okaxis", "UTIB", 1), ("ISHITA R", "ishita.r@okhdfcbank", "HDFC", 1)]
BK_FREELANCE = ("PIXELCRAFT STUDIO", "HDFC0004321")
BK_ATM = ["ATM CASH 4521 SBI JAYANAGAR 4TH BLOCK BANGALORE", "ATM CASH 1187 SBI BASAVANAGUDI BANGALORE"]
BK_POOL = {"PYTM": "4897691162091", "YESB": "4897736162093", "UTIB": "3199412044306",
           "ICIC": "4897702162088", "HDFC": "4897718162097", "SBIN": "3199400051121"}


def inr(x):
    """1234567.5 -> '12,34,567.50' (Indian digit grouping)."""
    whole, frac = f"{x:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(([head] if head else []) + groups + [tail])
    return f"{whole}.{frac}"


def yt_daily_minutes(yt):
    """Estimated YouTube minutes per IST date, same method as parsers/youtube.py (ads excluded)."""
    rows = sorted((datetime.fromisoformat(e["time"].replace("Z", "+00:00")),
                   any(d.get("name") == "From Google Ads" for d in e.get("details", []))) for e in yt)
    out = {}
    for i, (t, ad) in enumerate(rows):
        gap = (rows[i + 1][0] - t).total_seconds() / 60 if i + 1 < len(rows) else None
        est = 5.0 if gap is None or gap >= 30 else min(gap, 20.0)
        if not ad:
            d = t.astimezone(IST).date()
            out[d] = out.get(d, 0.0) + est
    return out


def gen_bank(seed, yt):
    """-> (statement rows [(date, desc, ref, debit, credit, balance)], truth categories, stats)"""
    rng = random.Random(f"{seed}:bank")
    pick = lambda opts: rng.choices(opts, [o[3] for o in opts])[0]  # noqa: E731
    ytm = yt_daily_minutes(yt)
    yt_mean = sum(ytm.values()) / max(len(ytm), 1)
    txns = []  # (date, minute-of-day, kind, payload, amount (+credit / -debit), category)

    def upi(d, minute, payee, amount, category, note="UPI", credit=False):
        txns.append((d, minute, "upi_cr" if credit else "upi_dr", (payee, note), amount if credit else -amount, category))

    d, credit_day = START, None
    while d <= END:
        weekend, sunday = d.weekday() >= 5, d.weekday() == 6
        exam = in_ranges(d, EXAM_WEEKS)
        dom = d.day
        # monthly parent credit around the 1st
        if dom == 1:
            credit_day = d + timedelta(days=rng.choice([0, 0, 1, 2]))
        if credit_day == d:
            upi(d, rng.randint(540, 720), BK_PARENT, 15000, "income", note="Monthly", credit=True)
        post_credit = credit_day is not None and 0 <= (d - credit_day).days < 7
        boost = 1.5 if post_credit else 1.0

        # --- base routine
        n_snacks = rng.choices([2, 3, 4, 5], [0.1, 0.25, 0.4, 0.25])[0] - (1 if sunday else 0)
        for _ in range(n_snacks):
            amt = 25 if rng.random() < 0.85 else rng.choice([20, 30, 40])
            upi(d, rng.randint(480, 1170), pick(BK_SNACKS), amt, "tea_snacks")
        upi(d, rng.randint(735, 840), pick(BK_LUNCH), rng.randrange(100, 145, 5), "meals")
        if rng.random() < 20 / 30:
            upi(d, rng.randint(450, 1260), pick(BK_AUTO), 20, "transport")

        # --- extras
        f_yt = min(max(0.35 + 0.65 * ytm.get(d, 0.0) / yt_mean, 0.3), 2.5)
        delivery = rng.random() < 0.13 * f_yt * (1.7 if exam else 1.0) * boost
        if delivery:
            upi(d, rng.randint(1170, 1350), pick(BK_DELIVERY), rng.randrange(180, 455, 5), "food_delivery", note="Order")
        if not delivery or rng.random() < 0.15:  # delivery usually replaces the canteen dinner
            upi(d, rng.randint(1140, 1260), pick(BK_DINNER), rng.randrange(100, 145, 5), "meals")
        if rng.random() < 0.06 * (1.3 if weekend else 1.0) * boost:
            upi(d, rng.randint(600, 1320), pick(BK_QCOMM), rng.randrange(120, 520, 10), "groceries_qcommerce")
        if rng.random() < 0.11:
            upi(d, rng.randint(540, 1200), BK_METRO, rng.choice([30, 40, 50, 60]), "transport")
        if rng.random() < 0.03 * (2.2 if weekend else 1.0) * boost:
            upi(d, rng.randint(600, 1380), pick(BK_SHOPPING), rng.randrange(249, 1500, 50), "shopping", note="Order")
        if rng.random() < (0.28 if weekend else 0.03) * boost:
            fun = rng.choices(BK_FUN, [f[3] for f in BK_FUN])[0]
            upi(d, rng.randint(900, 1320), fun[:4], rng.randrange(fun[4][0], fun[4][1], 10), "entertainment")
        if dom == 20:
            upi(d, rng.randint(600, 1200), BK_RECHARGE, 299, "bills_recharge", note="Recharge")
        for name, amount, day in BK_MANDATES:
            if dom == day:
                txns.append((d, 300, "mandate", name, -amount, "subscriptions"))
        # friends: splitting bills; exam weeks -> more transfers to the classmate (Varun)
        if rng.random() < 0.14:
            upi(d, rng.randint(720, 1380), pick(BK_FRIENDS), rng.randrange(50, 505, 10), "p2p_transfer",
                note=rng.choice(["split", "UPI", "dinner", "movie", "UPI"]))
        if exam and rng.random() < 0.35:
            upi(d, rng.randint(1200, 1410), BK_FRIENDS[2], rng.randrange(60, 260, 10), "p2p_transfer", note="food split")
        if rng.random() < 0.11:
            upi(d, rng.randint(600, 1380), pick(BK_FRIENDS), rng.randrange(50, 405, 10), "income", note="returned",
                credit=True)
        if rng.random() < 1 / 40:
            txns.append((d, rng.randint(600, 1200), "atm", rng.choice(BK_ATM), -rng.choice([500, 500, 500, 1000]),
                         "cash_atm"))
        d += timedelta(days=1)

    for fd in (date(2026, 1, 23), date(2026, 5, 4), date(2026, 8, 18), date(2026, 10, 9)):  # freelance NEFT
        txns.append((fd, 660, "neft", BK_FREELANCE, rng.randrange(3000, 8001, 250), "income"))
    interest_days = (date(2026, 2, 10), date(2026, 5, 10), date(2026, 8, 10), date(2026, 11, 10))

    # --- running balance, in time order; never negative. Like a real student near month-end,
    # extras (delivery, shopping, outings, transfers, ATM) are skipped when the balance would
    # drop below BK_LOW; the daily routine only stops if it would overdraw.
    txns.sort(key=lambda t: (t[0], t[1]))
    routine = {"tea_snacks", "meals", "transport", "subscriptions", "bills_recharge"}
    rows, truth, bal, dropped, quarter_sum, quarter_days = [], [], BK_OPENING, 0, 0.0, 0
    skipped_extras = 0
    last_day = None
    pending_interest = list(interest_days)
    for dd, minute, kind, payload, amount, category in txns:
        if last_day != dd:
            if pending_interest and dd >= pending_interest[0]:
                interest = round(quarter_sum / max(quarter_days, 1) * 0.027 / 4)
                bal = round(bal + interest, 2)
                rows.append((pending_interest[0], "CREDIT INTEREST--", "", None, interest, bal))
                truth.append("income")
                pending_interest.pop(0)
                quarter_sum, quarter_days = 0.0, 0
            quarter_sum, quarter_days, last_day = quarter_sum + bal, quarter_days + 1, dd
        if amount < 0 and category not in routine and bal + amount < BK_LOW:
            skipped_extras += 1
            continue
        if amount < 0 and bal + amount < 0:
            dropped += 1
            continue
        ref12 = str(rng.choice("456789")) + "".join(rng.choice(string.digits) for _ in range(11))
        if kind in ("upi_dr", "upi_cr"):
            (name, vpa, code, *_), note = payload
            direction = "DR" if kind == "upi_dr" else "CR"
            desc = (f"{'TO' if direction == 'DR' else 'BY'} TRANSFER-UPI/{direction}/{ref12}/{name[:8]}/{code}/"
                    f"{vpa[:10]}/{note}-")
            ref = f"TRANSFER {'TO' if direction == 'DR' else 'FROM'} {BK_POOL[code]}"
        elif kind == "mandate":
            desc, ref = f"DEBIT-CMP MANDATE DEBIT {payload}-", ""
        elif kind == "atm":
            desc, ref = f"ATM WDL-{payload}-", ""
        else:  # neft
            utr = "N" + "".join(rng.choice(string.digits) for _ in range(12))
            desc = f"BY TRANSFER-NEFT*{payload[1]}*{utr}*{payload[0]}*-"
            ref = f"TRANSFER FROM {BK_POOL['HDFC']}"
        bal = round(bal + amount, 2)
        rows.append((dd, desc, ref, -amount if amount < 0 else None, amount if amount > 0 else None, bal))
        truth.append(category)
    return rows, truth, {"dropped_overdraw": dropped, "skipped_low_balance": skipped_extras, "closing": bal}


def xlsx_bytes(cells):
    """Minimal one-sheet .xlsx (inline strings only) built with the stdlib."""
    from xml.sax.saxutils import escape

    def col(i):
        return "ABCDEFGHIJ"[i]
    sheet_rows = []
    for r, row in enumerate(cells, start=1):
        cs = "".join(f'<c r="{col(c)}{r}" t="inlineStr"><is><t xml:space="preserve">{escape(str(v))}</t></is></c>'
                     for c, v in enumerate(row) if v not in (None, ""))
        sheet_rows.append(f'<row r="{r}">{cs}</row>')
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Statement" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="1"><xf/></cellXfs></styleSheet>',
        "xl/worksheets/sheet1.xml": ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                                     + "".join(sheet_rows) + "</sheetData></worksheet>"),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(zipfile.ZipInfo(name, date_time=(2026, 11, 17, 9, 0, 0)), text.encode("utf-8"),
                        compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def bank_statement_cells(rows):
    fmt_d = lambda x: f"{x.day} {x:%b %Y}"  # noqa: E731  "13 Aug 2026"
    head = [
        ["Account Name", ":", "DEMO USER"],
        ["Address", ":", "DEMO ADDRESS, BENGALURU 560000"],
        ["Date", ":", fmt_d(END + timedelta(days=1))],
        ["Account Number", ":", "XXXXXXX1234"],
        ["Account Description", ":", "REGULAR SB CHQ-INDIVIDUALS"],
        ["Branch", ":", "DEMO BRANCH"],
        ["Drawing Power", ":", "0.00"],
        ["Interest Rate(% p.a.)", ":", "2.7"],
        ["MOD Balance", ":", "0.00"],
        ["CIF No.", ":", "XXXXXXX5678"],
        ["IFS Code", ":", "SBIN0000000"],
        ["MICR Code", ":", "560000000"],
        ["Nomination Registered", ":", "No"],
        [f"Balance as on {fmt_d(START)}", ":", inr(BK_OPENING)],
        [],
        [f"Account Statement from {fmt_d(START)} to {fmt_d(END)}"],
        [],
        ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Debit", "Credit", "Balance"],
    ]
    body = [[fmt_d(d), fmt_d(d), desc, ref or " ", inr(dr) if dr else " ", inr(cr) if cr else " ", inr(bal)]
            for d, desc, ref, dr, cr, bal in rows]
    return head + body + [[], ["**This is a computer generated statement and does not require a signature."]]


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

    wa_files, wa_counts, wa_truth = gen_whatsapp(a.seed)
    wa_dir = os.path.join(a.out, "whatsapp")
    os.makedirs(wa_dir, exist_ok=True)
    for name, data in wa_files.items():
        with open(os.path.join(wa_dir, name), "wb") as f:
            f.write(data)

    # Answer key for the sentiment scorer: true pos/neu/neg of every demo text message (NOT used by the app)
    import csv as _csv
    truth_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(truth_dir, exist_ok=True)
    with open(os.path.join(truth_dir, "demo_whatsapp_truth.csv"), "w", encoding="utf-8", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["chat", "local_time", "sender", "label", "text"])
        for chat, t, sender, label, text in wa_truth:
            w.writerow([chat, t.isoformat(sep=" "), sender, label, text])
    # Exam periods, pre-tagged in the app's DEMO database, and the demo user's chat name ("me")
    with open(os.path.join(a.out, "periods.json"), "w", encoding="utf-8") as f:
        json.dump({"periods": [{"label": "Exams", "start": s.isoformat(), "end": e.isoformat()}
                               for s, e in EXAM_WEEKS], "me": WA_ME}, f, indent=2)

    bank_rows, bank_truth, bank_stats = gen_bank(a.seed, yt)
    bank_dir = os.path.join(a.out, "bank")
    os.makedirs(bank_dir, exist_ok=True)
    with open(os.path.join(bank_dir, "SBI_statement_demo.xlsx"), "wb") as f:
        f.write(xlsx_bytes(bank_statement_cells(bank_rows)))
    # Hidden answer key for evaluating the spend categoriser (NOT used by the app)
    truth_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(truth_dir, exist_ok=True)
    with open(os.path.join(truth_dir, "demo_bank_truth.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("row,txn_date,description,debit,credit,category\n")
        for i, ((dd, desc, _, dr, cr, _), cat) in enumerate(zip(bank_rows, bank_truth), start=1):
            f.write(f'{i},{dd},"{desc}",{dr or ""},{cr or ""},{cat}\n')

    print(f"Spotify plays: {len(sp):,}  |  YouTube entries: {len(yt):,}  |  {START} to {END}")
    print(f"Bank transactions: {len(bank_rows):,}  |  closing balance {inr(bank_stats['closing'])}"
          f"  |  extras skipped at low balance: {bank_stats['skipped_low_balance']}"
          f"  |  overdraw-dropped debits: {bank_stats['dropped_overdraw']}")
    print(f"WhatsApp messages: {sum(wa_counts.values()):,}  |  "
          + ", ".join(f"{k}: {v:,}" for k, v in wa_counts.items()))


if __name__ == "__main__":
    main()
