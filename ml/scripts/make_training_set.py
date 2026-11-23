"""Build the TRAINING set for the spend categoriser.

Turns the hand-written merchant list (ml/data/merchant_labels.csv) plus synthetic small
vendors, auto drivers and friends into realistic SBI statement rows, for several
synthetic users over a year.

Independence from the demo statement (which is the final TEST set):
  - its own random stream ("train:<seed>") and a different year (2024),
  - its own name lists: no demo vendor, auto driver, friend or parent name is used
    (checked by web/src/python/tests and ml/tests),
  - user habits are randomised per synthetic user, so the model has to learn general
    behaviour ("small fixed amount, several times a day"), not one person's routine.
Real brands (Swiggy, Zomato, …) appear in both, as they would in real life.

Output: ml/data/training_set.csv with one row per DEBIT:
  statement_id, txn_date, description, ref, debit, category, payee_group
payee_group identifies the real payee (brand, or one statement's vendor/person) and is
used for GroupKFold, so a payee never appears in both a training and a validation fold.

Usage:  python ml/scripts/make_training_set.py [--seed 2027] [--users 12]
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import string
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
START, END = date(2024, 1, 1), date(2024, 12, 31)

# ---- training-only name lists (must never contain demo names; see tests)
FIRST = ["AARAV", "VIVAAN", "ADITYA", "ARJUN", "REYANSH", "ISHAAN", "SHAURYA", "ATHARV", "AYAAN", "KABIR",
         "DHRUV", "ANANYA", "DIYA", "AADHYA", "SAANVI", "ANIKA", "KAVYA", "MYRA", "PARI", "MEERA",
         "NISHA", "POOJA", "DEEPAK", "MANOJ", "RAVI", "SANJAY", "VIKRAM", "HARISH", "LOKESH", "NAVEEN",
         "PRAKASH", "GIRISH", "MAHESH", "GANESH", "ARUN", "TEJAS", "YASH", "NEHA", "SWATHI", "SHRUTI",
         "BHAVYA", "KEERTHI", "LAVANYA", "HARINI", "ABHISHEK", "AKSHAY", "CHETAN", "GAURAV", "HEMANT",
         "JAYANT", "KIRAN", "MOHIT", "PAVAN", "RAJAT", "SACHIN", "TARUN", "UDAY", "VINAY",
         "ZOYA", "FATIMA", "AYESHA", "SAMEER", "IMRAN", "JOSEPH", "MARIA", "TANVI", "RITU",
         "SHREYA", "ANJALI", "BHARATH", "DEVIKA", "ESHA", "GAYATHRI", "HRITHIK", "JANVI", "KUSHAL"]
LAST = ["NAIR", "IYER", "REDDY", "PATIL", "DESAI", "MENON", "GOWDA", "HEGDE", "KULKARNI", "JOSHI",
        "GUPTA", "SINGH", "VERMA", "MISHRA", "PANDEY", "BHAT", "SHETTY", "PILLAI", "DAS", "BOSE",
        "CHOPRA", "KAPOOR", "MALHOTRA", "AGARWAL", "JAIN", "KHAN", "SHAIKH", "FERNANDES", "DSOUZA", "THOMAS",
        "CHAUDHARY", "YADAV", "TIWARI", "SAXENA", "RAO", "MURTHY", "PRASAD", "NAIDU", "SHARMA", "KAMATH"]
DRIVERS = ["BASAVARAJ", "NAGARAJ", "MAHADEVA", "CHANDRU", "THIMMAPPA", "KRISHNAPPA", "RANGASWAMY",
           "PUTTASWAMY", "LINGAPPA", "HANUMANTHA", "SIDDAPPA", "GOVINDA", "MALLESH", "RAMAPPA", "NINGAPPA",
           "PRABHU", "SELVAM", "MURUGESAN", "ANWAR", "SALIM", "RAFIQ", "JOHN", "DEVARAJ", "SHANKAR",
           "BHEEMA", "KEMPANNA", "CHIKKANNA", "DODDAIAH", "HONNAPPA", "YELLAPPA"]
VENDOR_PREFIX = ["GANESH", "BALAJI", "VINAYAKA", "MURUGAN", "AMMA", "NEW", "OM", "JAI", "SHREE", "KRISHNA",
                 "RAGHAVENDRA", "BHAGYA", "DURGA", "ANJANEYA", "CHAMUNDI", "KAVERI", "TIRUPATI", "VASAVI",
                 "ROYAL", "FRIENDS", "STAR", "CITY", "GREEN", "GOLDEN", "SAGAR", "PANCHAMI", "MAYURI",
                 "SANGAM", "SWAGATH", "ARYA", "BHARATH", "NETHRA", "AKSHAYA", "VAIBHAV", "PRIME", "UNIVERSITY"]
TEA_SUFFIX = ["TEA STALL", "TEA CORNER", "TEA SHOP", "BAKERY", "BAKERS", "JUICE CENTRE", "COOL BAR",
              "CONDIMENTS", "SNACKS", "TEA HOUSE", "CHATS", "BAKE HOUSE", "TEA POINT", "COFFEE CORNER"]
MEAL_SUFFIX = ["MESS", "CANTEEN", "HOTEL", "DARSHINI", "BHAVAN", "RESTAURANT", "TIFFINS", "FAST FOOD",
               "FOOD COURT", "MEALS", "KITCHEN", "DHABA", "UPAHARA", "FAMILY RESTAURANT"]
GROCERY_SUFFIX = ["PROVISION STORE", "SUPERMARKET", "GENERAL STORES", "FRESH MART", "FRUITS", "MILK BOOTH",
                  "KIRANA", "VEGETABLES", "DAILY NEEDS"]
ATM_AREAS = ["KORAMANGALA", "INDIRANAGAR", "HSR LAYOUT", "MALLESWARAM", "BTM LAYOUT", "WHITEFIELD", "HEBBAL",
             "RAJAJINAGAR", "VIJAYANAGAR", "BANASHANKARI", "ELECTRONIC CITY", "MARATHAHALLI", "YELAHANKA"]
BANKS = ["YESB", "UTIB", "ICIC", "HDFC", "SBIN", "PYTM", "KKBK", "IDFB", "INDB", "BARB"]
MERCHANT_NOTES = ["UPI", "UPI", "UPI", "Payment", "Pay", "Paid", "Order", "Txn", "purchase", "bill", ""]
P2P_NOTES = ["UPI", "UPI", "split", "dinner", "rent", "bday", "movie", "trip", "lunch", "thanks", "share",
             "tea", "fees", "cab", "return", "gift", "party", "food", ""]
SUB_NOTES = ["AutoPay", "Mandate", "Subscription", "UPI", "Monthly"]


def load_merchants():
    with open(os.path.join(DATA, "merchant_labels.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    merchants = [r for r in rows if r["kind"] == "merchant"]
    handles = [r for r in rows if r["kind"] == "handle"]
    for r in merchants + handles:
        r["min"], r["max"], r["weight"] = float(r["min"]), float(r["max"]), float(r["weight"])
    return merchants, handles


class Gen:
    def __init__(self, seed):
        self.rng = random.Random(f"train:{seed}")

    def digits(self, n):
        return "".join(self.rng.choice(string.digits) for _ in range(n))

    def cut(self, s, base):
        # SBI cuts names (~8 chars) and UPI IDs (~10 chars); allow small variation
        n = base if self.rng.random() < 0.8 else base + self.rng.choice([-1, 1, 2])
        return s[:n]

    def person_vpa(self, first, last, handles):
        h = self.rng.choices(handles, [x["weight"] for x in handles])[0]
        suffix = h["vpa"]
        if suffix.startswith("PHONE"):
            return self.rng.choice("6789") + self.digits(9) + suffix[5:], h["bank"]
        style = self.rng.random()
        local = (first.lower() + last.lower()[:self.rng.randint(1, 4)] if style < 0.4 else
                 first.lower() + self.digits(self.rng.randint(2, 4)) if style < 0.7 else
                 first.lower() + "." + last.lower() if style < 0.85 else
                 self.rng.choice("6789") + self.digits(9))
        return local + suffix, h["bank"]

    def qr_vpa(self, handles):
        h = self.rng.choices([x for x in handles if x["category"] == "merchant_qr"],
                             [x["weight"] for x in handles if x["category"] == "merchant_qr"])[0]
        v = h["vpa"]
        if v.startswith("paytmqr"):
            return "paytmqr" + "".join(self.rng.choice(string.ascii_lowercase + string.digits)
                                       for _ in range(self.rng.randint(10, 20))) + "@paytm", "PYTM"
        if v.startswith("Q@"):
            return "q" + self.digits(9) + "@ybl", "YESB"
        if v.startswith("bharatpe"):
            return "bharatpe." + self.digits(10) + "@yesbankltd", "YESB"
        return "gpay-" + self.digits(11) + "@okbizaxis", "UTIB"

    def vendor_name(self, suffixes):
        return f"{self.rng.choice(VENDOR_PREFIX)} {self.rng.choice(suffixes)}"

    def upi(self, direction, name, vpa, bank, note):
        ref = self.rng.choice("3456789") + self.digits(11)
        return (f"{'TO' if direction == 'DR' else 'BY'} TRANSFER-UPI/{direction}/{ref}/{self.cut(name, 8)}/{bank}/"
                f"{self.cut(vpa, 10)}/{note}-")


def money(rng, lo, hi, step=None):
    step = step or rng.choice([1, 1, 5, 10])
    v = rng.uniform(lo, hi)
    return max(round(v / step) * step, 1)


def make_user(g: Gen, uid, merchants, handles):
    """One synthetic student/young professional with randomised habits."""
    rng = g.rng
    by_cat = {}
    for m in merchants:
        by_cat.setdefault(m["category"], []).append(m)

    def pick_brands(cat, k):
        pool = by_cat[cat]
        chosen = set()
        while len(chosen) < min(k, len(pool)):
            chosen.add(rng.choices(range(len(pool)), [m["weight"] for m in pool])[0])
        return [pool[i] for i in chosen]

    payees = []  # (payee dict, daily_or_monthly rate spec)

    def local_payee(name, cat, price, vpa_kind, kind):
        if vpa_kind == "qr":
            vpa, bank = g.qr_vpa(handles)
        elif vpa_kind == "biz":
            vpa, bank = name.lower().replace(" ", "")[:14] + rng.choice(["@ybl", "@okaxis", "@paytm", "@ibl"]), \
                rng.choice(BANKS)
        else:
            vpa, bank = g.person_vpa(name.split()[0], name.split()[-1], [h for h in handles if h["category"] == "p2p_transfer"])
        return {"name": name, "vpa": vpa, "bank": bank, "category": cat, "price": price, "kind": kind,
                "group": f"u{uid}:{cat}:{name}"}

    # tea / snacks: 0-7 regular vendors, small fixed prices, several times a day
    tea = [local_payee(g.vendor_name(TEA_SUFFIX), "tea_snacks", rng.choice([10, 12, 15, 20, 25, 30]),
                       rng.choices(["qr", "biz", "person"], [0.7, 0.2, 0.1])[0], "tea")
           for _ in range(rng.choice([0, 2, 3, 4, 5, 6, 7]))]
    tea_per_day = rng.choice([0.5, 1.5, 2.5, 3.5, 4.5]) if tea else 0
    # meals: regular canteens / messes / hotels
    meals = [local_payee(g.vendor_name(MEAL_SUFFIX), "meals", rng.randrange(50, 220, 10),
                         rng.choices(["qr", "biz", "person"], [0.55, 0.35, 0.1])[0], "meal")
             for _ in range(rng.randint(2, 6))]
    meals_per_day = rng.choice([0.6, 1.0, 1.4, 1.8])
    # local transport: autos paid to drivers' phone / name VPAs, fixed-ish fares
    drivers = []
    for _ in range(rng.choice([0, 3, 6, 9, 12])):
        n = rng.choice(DRIVERS)
        p = local_payee(f"{n} {rng.choice(['K', 'M', 'R', 'S', 'B', 'N'])}", "transport",
                        rng.choice([20, 25, 30, 40, 50, 60, 80, 100]), "person", "auto")
        drivers.append(p)
    auto_prob = rng.choice([0.2, 0.4, 0.6, 0.8]) if drivers else 0
    # small local shops of other kinds (unknown names, QR codes)
    grocers = [local_payee(g.vendor_name(GROCERY_SUFFIX), "groceries_qcommerce", 0,
                           rng.choices(["qr", "biz"], [0.6, 0.4])[0], "grocer") for _ in range(rng.randint(0, 4))]
    # friends and family
    friends = []
    for _ in range(rng.randint(4, 18)):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        p = local_payee(f"{first} {last}", "p2p_transfer", 0, "person", "friend")
        friends.append(p)
    p2p_per_month = rng.choice([3, 6, 10, 15, 25])
    # brands: per category monthly rate and a personal set of brands
    rates = {"food_delivery": rng.choice([0, 1, 3, 5, 8, 12]), "groceries_qcommerce": rng.choice([0, 1, 2, 4, 7]),
             "transport": rng.choice([0, 2, 4, 8, 14]), "shopping": rng.choice([0.5, 1, 2, 3]),
             "entertainment": rng.choice([0.5, 1, 2, 4, 6]), "other": rng.choice([0.5, 1, 2, 3]),
             "meals": rng.choice([0, 1, 2, 4]), "tea_snacks": rng.choice([0, 1, 2, 4])}
    brands = {c: pick_brands(c, rng.randint(2, 7)) for c in rates}
    subs = pick_brands("subscriptions", rng.randint(0, 4))
    bills = pick_brands("bills_recharge", rng.randint(1, 3))
    atm_per_month = rng.choice([0, 0.5, 1, 2, 3])
    return locals()


def simulate(g: Gen, uid, u):
    rng = g.rng
    rows = []  # (date, minute, description, ref, amount, category, group)

    def add(d, minute, desc, amount, cat, group, ref=None):
        ref = ref if ref is not None else f"TRANSFER TO {rng.choice(['4897', '3199'])}{g.digits(9)}"
        rows.append((d, minute, desc, ref, round(amount, 2), cat, group))

    def pay_local(d, p, amount, note_pool):
        add(d, rng.randint(420, 1380), g.upi("DR", p["name"], p["vpa"], p["bank"], rng.choice(note_pool)),
            amount, p["category"], p["group"])

    def pay_brand(d, m, note_pool=MERCHANT_NOTES):
        amt = money(rng, m["min"], m["max"])
        add(d, rng.randint(420, 1400), g.upi("DR", m["name"], m["vpa"], m["bank"], rng.choice(note_pool)),
            amt, m["category"], f"m:{m['name']}")

    sub_days = {id(s): rng.randint(1, 28) for s in u["subs"]}
    sub_amt = {id(s): money(rng, s["min"], s["max"], 1) for s in u["subs"]}
    sub_mandate = {id(s): rng.random() < 0.6 for s in u["subs"]}
    bill_days = {id(b): rng.randint(1, 28) for b in u["bills"]}
    d = START
    while d <= END:
        weekend = d.weekday() >= 5
        # tea / snacks
        if u["tea"]:
            n = max(0, round(rng.gauss(u["tea_per_day"] * (0.75 if d.weekday() == 6 else 1), 1.0)))
            for _ in range(n):
                p = rng.choice(u["tea"][:max(1, len(u["tea"]))])
                price = p["price"] if rng.random() < 0.8 else p["price"] + rng.choice([-5, 5, 10, 15])
                pay_local(d, p, max(price, 5), MERCHANT_NOTES)
        # meals
        n = sum(rng.random() < u["meals_per_day"] / 2 for _ in range(2))
        for _ in range(n):
            p = rng.choice(u["meals"])
            pay_local(d, p, max(p["price"] + rng.randrange(-20, 25, 5), 20), MERCHANT_NOTES)
        # autos
        if u["drivers"] and rng.random() < u["auto_prob"]:
            p = rng.choice(u["drivers"])
            pay_local(d, p, p["price"] if rng.random() < 0.85 else p["price"] + rng.choice([10, 20]), ["UPI", "auto", ""])
        # small grocers
        for p in u["grocers"]:
            if rng.random() < 0.06:
                pay_local(d, p, money(rng, 30, 700, 5), MERCHANT_NOTES)
        # brands (monthly rates -> daily probability; entertainment / shopping lean to weekends)
        for cat, per_month in u["rates"].items():
            lean = 1.8 if weekend and cat in ("entertainment", "shopping") else 1.0
            if u["brands"][cat] and rng.random() < per_month / 30 * lean:
                pay_brand(d, rng.choice(u["brands"][cat]))
        # friends
        if u["friends"] and rng.random() < u["p2p_per_month"] / 30:
            p = rng.choice(u["friends"])
            amt = rng.choice([money(rng, 20, 300, 10), money(rng, 50, 800, 50), money(rng, 200, 3000, 100)])
            pay_local(d, p, amt, P2P_NOTES)
        # subscriptions (mandate debit or UPI autopay) and bills on fixed days
        for s in u["subs"]:
            if d.day == sub_days[id(s)]:
                if sub_mandate[id(s)]:
                    add(d, 300, f"DEBIT-CMP MANDATE DEBIT {s['name'][:20]}-", sub_amt[id(s)], "subscriptions",
                        f"m:{s['name']}", ref=" ")
                else:
                    add(d, 300, g.upi("DR", s["name"], s["vpa"], s["bank"], rng.choice(SUB_NOTES)), sub_amt[id(s)],
                        "subscriptions", f"m:{s['name']}")
        for b in u["bills"]:
            if d.day == bill_days[id(b)]:
                pay_brand(d, b, ["UPI", "Recharge", "bill", "Payment", "BBPS"])
        # ATM cash
        if rng.random() < u["atm_per_month"] / 30:
            add(d, rng.randint(540, 1200), f"ATM WDL-ATM CASH {g.digits(4)} {rng.choice(['SBI', 'SBI', 'HDFC', 'AXIS'])} "
                f"{rng.choice(ATM_AREAS)} BANGALORE-", rng.choice([200, 500, 500, 1000, 2000, 3000]), "cash_atm",
                f"u{uid}:atm", ref=" ")
        d += timedelta(days=1)
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2027)
    ap.add_argument("--users", type=int, default=12)
    ap.add_argument("--out", default=os.path.join(DATA, "training_set.csv"))
    a = ap.parse_args()
    merchants, handles = load_merchants()
    g = Gen(a.seed)
    total = 0
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["statement_id", "txn_date", "description", "ref", "debit", "category", "payee_group"])
        for uid in range(a.users):
            rows = simulate(g, uid, make_user(g, uid, merchants, handles))
            for d, _, desc, ref, amt, cat, group in rows:
                w.writerow([f"S{uid:02d}", d.isoformat(), desc, ref, f"{amt:.2f}", cat, group])
            total += len(rows)
    print(f"training rows: {total:,} from {a.users} synthetic users -> {os.path.relpath(a.out)}")


if __name__ == "__main__":
    main()
