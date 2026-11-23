"""Hand-written keyword dictionary + channel rules for bank debits.

Used two ways:
  1. the RULES-ONLY BASELINE (`rule_category`) the ML models are compared against, and
  2. as "rule flags" inside the full model (`keyword_category` -> one-hot features).

The dictionary is written by hand from general knowledge (well-known Indian brands and
generic shop words). It is deliberately NOT generated from ml/data/merchant_labels.csv,
so cross-validation on the training set does not get the answers for free.

Pure Python: shared verbatim with the browser (see ml/selfscope_ml/README.md).
"""

from __future__ import annotations

import re

# keyword -> category. Matched as a substring of the lower-cased payee name and UPI ID
# (spaces removed). The longest matching keyword wins; on a tie, one found in the payee
# name beats one found only in the UPI ID.
KEYWORDS: dict[str, str] = {
    # food delivery
    "swiggy": "food_delivery", "zomato": "food_delivery", "dominos": "food_delivery", "pizzahut": "food_delivery",
    "eatsure": "food_delivery", "faasos": "food_delivery", "behrouz": "food_delivery", "box8": "food_delivery",
    # groceries / quick commerce
    "zepto": "groceries_qcommerce", "blinkit": "groceries_qcommerce", "instamart": "groceries_qcommerce",
    "bigbasket": "groceries_qcommerce", "jiomart": "groceries_qcommerce", "dmart": "groceries_qcommerce",
    "supermarket": "groceries_qcommerce", "provision": "groceries_qcommerce", "kirana": "groceries_qcommerce",
    "grocery": "groceries_qcommerce", "fresh": "groceries_qcommerce", "mart": "groceries_qcommerce",
    "vegetable": "groceries_qcommerce", "fruits": "groceries_qcommerce", "milkbooth": "groceries_qcommerce",
    # transport
    "uber": "transport", "olacabs": "transport", "rapido": "transport", "nammayatri": "transport",
    "metro": "transport", "bmrcl": "transport", "irctc": "transport", "redbus": "transport", "ksrtc": "transport",
    "bmtc": "transport", "petrol": "transport", "fuel": "transport", "fastag": "transport", "yulu": "transport",
    "auto": "transport", "cab": "transport", "travels": "transport", "smartcard": "transport", "dmrc": "transport",
    # shopping
    "amazon": "shopping", "flipkart": "shopping", "myntra": "shopping", "ajio": "shopping", "nykaa": "shopping",
    "meesho": "shopping", "decathlon": "shopping", "croma": "shopping", "zudio": "shopping", "lenskart": "shopping",
    "fashion": "shopping", "garments": "shopping", "footwear": "shopping", "electronics": "shopping",
    # entertainment (movies, events, games, sit-down cafe chains, pubs)
    "bookmyshow": "entertainment", "pvr": "entertainment", "inox": "entertainment", "cinepolis": "entertainment",
    "starbucks": "entertainment", "thirdwave": "entertainment", "bluetokai": "entertainment",
    "chaipoint": "entertainment", "chaayos": "entertainment", "coffeeday": "entertainment", "ccd": "entertainment",
    "cafe": "entertainment", "cinema": "entertainment", "theatre": "entertainment", "gaming": "entertainment",
    "brew": "entertainment", "pub": "entertainment", "steam": "entertainment",
    # meals (eating out: restaurants, canteens, messes, darshinis)
    "mcdonald": "meals", "kfc": "meals", "burgerking": "meals", "subway": "meals", "restaurant": "meals",
    "canteen": "meals", "mess": "meals", "hotel": "meals", "darshini": "meals", "bhavan": "meals",
    "tiffin": "meals", "dhaba": "meals", "biryani": "meals", "meals": "meals", "kitchen": "meals",
    "foodcourt": "meals",
    # tea / snacks
    "tea": "tea_snacks", "chai": "tea_snacks", "bakery": "tea_snacks", "bakers": "tea_snacks",
    "juice": "tea_snacks", "condiment": "tea_snacks", "snack": "tea_snacks", "icecream": "tea_snacks",
    "chats": "tea_snacks", "coolbar": "tea_snacks", "sweets": "tea_snacks", "milkshake": "tea_snacks",
    # bills / recharge
    "airtel": "bills_recharge", "jio": "bills_recharge", "vodafone": "bills_recharge", "bsnl": "bills_recharge",
    "recharge": "bills_recharge", "bescom": "bills_recharge", "electricity": "bills_recharge",
    "broadband": "bills_recharge", "fibernet": "bills_recharge", "billdesk": "bills_recharge", "bbps": "bills_recharge",
    "indane": "bills_recharge", "hpgas": "bills_recharge", "bharatgas": "bills_recharge",
    # subscriptions
    "netflix": "subscriptions", "spotify": "subscriptions", "hotstar": "subscriptions", "amazonprime": "subscriptions",
    "youtube": "subscriptions", "googleplay": "subscriptions", "sonyliv": "subscriptions", "zee5": "subscriptions",
    "jiocinema": "subscriptions", "jiosaavn": "subscriptions", "subscription": "subscriptions",
    # other (health, education, services, finance)
    "pharma": "other", "medical": "other", "medplus": "other", "hospital": "other", "clinic": "other",
    "apollo": "other", "insurance": "other", "college": "other", "university": "other", "fees": "other",
    "xerox": "other", "salon": "other", "courier": "other",
}

PERSONAL_HANDLES = ("@ok", "@ybl", "@ibl", "@axl", "@paytm", "@upi", "@sbi", "@apl", "@kotak", "@fam", "@pt")
BUSINESS_WORDS = ("tea", "chai", "bakery", "hotel", "mess", "canteen", "store", "mart", "shop", "cafe", "foods",
                  "restaurant", "darshini", "bhavan", "juice", "stall", "corner", "centre", "center", "traders",
                  "enterprises", "agencies", "pvt", "ltd", "limited", "services", "retail", "kitchen", "snacks")


def _squash(s: str | None) -> str:
    return re.sub(r"[^a-z0-9@.]", "", (s or "").lower())


def keyword_category(counterparty: str | None, vpa: str | None) -> str | None:
    """Category of the longest dictionary keyword found in the payee name or UPI ID
    (ties: the payee name wins)."""
    name, v = _squash(counterparty), _squash(vpa)
    best = max(((len(kw), kw in name, kw) for kw in KEYWORDS if kw in name or kw in v), default=None)
    return KEYWORDS[best[2]] if best else None


def is_phone_vpa(vpa: str | None) -> bool:
    """A UPI ID that is a (masked) 10-digit phone number, e.g. 'XXXXXX2736' or '9845012736@ybl'."""
    v = (vpa or "").lower()
    return bool(re.match(r"^[x\d]{8,}(@|$)", v)) and sum(c.isdigit() for c in v[:10]) >= 4


def is_merchant_qr(vpa: str | None) -> bool:
    """Shop QR-code handles: paytmqr…, PhonePe 'q<digits>', BharatPe, GPay business."""
    v = (vpa or "").lower()
    return bool(re.match(r"^(paytmqr|bharatpe|gpay-)", v) or re.match(r"^q[x\d]{6,}", v))


def looks_like_person(counterparty: str | None, vpa: str | None) -> bool:
    """Person-to-person: phone-number handle, or a personal handle / name-like UPI ID,
    with no merchant keyword or business word."""
    if is_merchant_qr(vpa):
        return False
    if keyword_category(counterparty, vpa) is not None:
        return False
    name, v = (counterparty or "").lower(), (vpa or "").lower()
    if any(w in name.replace(" ", "") or w in v for w in BUSINESS_WORDS):
        return False
    if is_phone_vpa(v):
        return True
    first = name.split()[0] if name.split() else ""
    return (len(first) >= 3 and v.startswith(first[:4])) or any(h in v for h in PERSONAL_HANDLES)


def rule_category(row: dict) -> str:
    """RULES-ONLY BASELINE for one parsed debit row (see features.row_from_event)."""
    ch = row.get("channel")
    if ch == "ATM":
        return "cash_atm"
    if ch == "MANDATE":
        return keyword_category(row.get("counterparty"), None) or "subscriptions"
    kw = keyword_category(row.get("counterparty"), row.get("vpa_fragment"))
    if kw:
        return kw
    if looks_like_person(row.get("counterparty"), row.get("vpa_fragment")):
        return "p2p_transfer"
    if is_merchant_qr(row.get("vpa_fragment")) and row.get("amount", 0) <= 40:
        return "tea_snacks"
    return "other"
