# Demo data (synthetic)

Everything in this folder is **generated**, not real. It's here to demo SelfScope without exposing anyone's private data.

- `spotify/StreamingHistory_music_*.json`: about 11.8k plays over one year, in Spotify's real "Account data" format
- `google/Takeout/YouTube and YouTube Music/history/watch-history.json`: about 7.8k entries in Google Takeout's real JSON format (newest first, about 5% are ads)
- `whatsapp/`: 5 chats, about 20.8k messages, from the user **Amogh**'s point of view, in WhatsApp's real export formats:
  - `WhatsApp Chat with Priya.txt` (close friend, ~6.5k), `WhatsApp Chat with Ishita.txt` (sister, ~1.7k), `WhatsApp Chat with CSE Batch 27.txt` (college group of 7, ~6.9k), `WhatsApp Chat with Varun.txt` (classmate, ~0.9k): **Android** format (`17/11/25, 9:41 pm - Name: text`, narrow no-break space before am/pm)
  - `WhatsApp Chat - Rohan.zip` (close friend, ~4.7k): **iOS** format, a .zip containing `_chat.txt` (`[17/11/25, 9:41:23 PM] Name: text`, U+200E marks on media/system lines)
  - English + Hinglish; includes media-omitted lines, deleted and edited messages, multi-line messages, and group system lines (created, added, left, icon/description changes)
  - Every text message comes from a clearly positive, neutral or negative pool, so sentiment models have signal
- `bank/SBI_statement_demo.xlsx`: one year of a student's SBI savings account, **2,629 transactions**, laid out like an OnlineSBI Excel download: a header block (Account Name: DEMO USER, Account Number: XXXXXXX1234, statement period, …), then `Txn Date | Value Date | Description | Ref No./Cheque No. | Debit | Credit | Balance`, dates like "13 Aug 2026", amounts as Indian-formatted text ("1,23,456.78"), and a running balance that never goes negative (opening ₹12,000). Real SBI narration formats: `TO TRANSFER-UPI/DR/<12-digit ref>/<payee cut to 8>/<bank code>/<UPI ID cut>/<note>-`, `BY TRANSFER-UPI/CR/…`, Ref No. `TRANSFER TO <13 digits>`, `ATM WDL-ATM CASH …-`, `DEBIT-CMP MANDATE DEBIT <name>-`, `CREDIT INTEREST--`, `BY TRANSFER-NEFT*<IFSC>*<UTR>*<name>*-`. Every name, UPI ID, phone number and reference number is made up. The true category of every row is in `ml/data/demo_bank_truth.csv` (answer key for the categoriser; the app never reads it)

- `periods.json`: the 3 exam periods and the 2 semester breaks ("Breaks"), pre-tagged in the DEMO database when demo data is loaded (the dashboard compares them with other days), and the demo user's chat name (`"me": "Amogh"`), picked automatically

The true sentiment label of every demo WhatsApp text message is in `ml/data/demo_whatsapp_truth.csv` (answer key for the sentiment scorer, made by the generator with its own random stream so the demo files did not change; the app never reads it).

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

### Bank (same calendar)

**Daily routine** (the base of the statement, close to a real student budget):
- **Tea / snacks:** ₹25 (sometimes ₹20–40), 2–5 times a day (about 3.7/day; one fewer on Sundays), at 6 regular paytmqr-style vendors (Sri Lakshmi Tea Stall, Raju Tea Point, Campus Bakery, …)
- **Lunch:** ₹100–140 every day at 2–3 regular canteens; **dinner:** ₹100–140 at a few regular places (about ₹222/day on meals overall)
- **Auto:** ₹20 on about 2 of 3 days (Rapido or local autos paid to phone-number UPI IDs)
- The routine continues through exams. Near month-end, when the balance drops below ₹3,500, *extras* are skipped (21 times in the year); the routine never is.

**Extras:** Swiggy/Zomato about 4 a month (₹180–450; on a delivery day the canteen dinner is usually skipped), Zepto/Blinkit 2–3 a month, Namma Metro (BMRCL) now and then, Amazon/Flipkart/Myntra 1–2 a month, BookMyShow and cafes mostly on weekends, Jio recharge ₹299 on the 20th, Spotify (₹119) and Netflix (₹199) as mandate debits, ATM cash about once a month, and transfers to the same friends as the WhatsApp chats (Priya, Rohan, Varun, Karthik, Sneha, Ishita; ₹50–500).

**Credits:** ₹15,000 from a parent (SURESH K) around the 1st of every month, friends paying back ₹50–400, 4 NEFT freelance payments (₹3,000–8,000), quarterly SBI interest. Spend is about ₹17k/month against about ₹17.4k/month received.

**Planted patterns** (measured on the generated file):
1. **Food delivery tracks YouTube and exams:** delivery happens on 19% of high-YouTube days vs 8% of low ones (daily YouTube minutes estimated from the demo watch history the same way the app does), and on 24% of exam-week days vs 12% otherwise
2. **Weekends:** entertainment + shopping ₹120/day vs ₹59/day on weekdays (cafe outings count as entertainment in the answer key)
3. **First week after the parent credit:** extras ₹222/day vs ₹116/day
4. **Exam weeks:** transfers to the classmate (Varun, splitting food) 0.46/day vs 0.04/day

## Regenerate
```
python ml/scripts/generate_demo_data.py --out data/samples --seed 42
```

Real exports go in `data/private/` (git-ignored), never here.
