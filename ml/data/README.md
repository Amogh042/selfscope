# ml/data — categoriser data

| File | What | Used for |
|---|---|---|
| `merchant_labels.csv` | **Hand-written** list of 434 real Indian merchants/brands + 20 UPI handle patterns, with a category, a typical UPI ID, bank code, amount range and how common it is | building the training set |
| `training_set.csv` | ~24k synthetic SBI debits (12 synthetic users, year 2024), made by `ml/scripts/make_training_set.py` | training + cross-validation |
| `demo_bank_truth.csv` | true category of every row of the demo statement (`data/samples/bank/SBI_statement_demo.xlsx`), made by `ml/scripts/generate_demo_data.py` | **final test only** — never for training or tuning; the app never reads it |

## merchant_labels.csv

Columns: `kind` (`merchant` or `handle`), `name` (as it would appear as the payee; often the legal entity, e.g. *BUNDL TECHNOLOGIES* = Swiggy, *KIRANAKART TECHNOLOGIES* = Zepto, *BIGTREE ENTERTAINMENT* = BookMyShow), `keyword`, `vpa` (typical UPI ID), `bank` (PSP bank code), `category`, `min`/`max` (typical amount in ₹), `weight` (how common).

`handle` rows are UPI handle patterns: personal handles (`@okaxis`, `@ybl`, `@paytm`, phone numbers, …) → `p2p_transfer`, and shop QR handles (`paytmqr…`, `q<digits>@ybl`, BharatPe, GPay business) used for small vendors.

### Labelling conventions (same as the demo answer key)

- **tea_snacks** — tea/coffee stalls, bakeries, juice, ice cream, condiments/petty shops, chaat.
- **meals** — eating out: restaurants, canteens, messes, darshinis, QSR dine-in (McDonald's, KFC, Burger King, Subway).
- **food_delivery** — Swiggy, Zomato and delivery-first brands (Domino's, EatSure/Rebel Foods, Box8, …).
- **entertainment** — movies, events, games, pubs **and sit-down cafe chains** (Starbucks, Third Wave, Blue Tokai, Chai Point, CCD, …): a cafe visit is a social outing, not a meal.
- **groceries_qcommerce** — Zepto, Blinkit, Instamart, BigBasket, DMart, kirana/provision stores, fruit, milk booths.
- **transport** — cabs, autos, metro, bus, trains, flights booked for travel, fuel, FASTag.
- **bills_recharge** — mobile/DTH/broadband recharges, electricity, water, cooking gas, BBPS.
- **subscriptions** — streaming, music, cloud storage, software, gym memberships (often mandate debits).
- **other** — pharmacies, hospitals, labs, insurance, education/fees, government, courier, salon, rent, investments.
- **p2p_transfer** — money sent to a person. **cash_atm** — ATM withdrawals. **income** — every credit (rule).

## Independence from the test set

`make_training_set.py` uses its own random stream (`train:<seed>`), a different year (2024) and its own
name lists for tea stalls, canteens, auto drivers and friends. `ml/tests/test_training_data.py` fails if
any made-up demo name (vendors, drivers, friends, parent, WhatsApp members) or demo UPI ID appears in the
training data or the merchant list. Real brands (Swiggy, Zomato, Rapido, …) appear in both, as they would
for any real categoriser.

Regenerate: `python ml/scripts/make_training_set.py [--seed 2027] [--users 12]`
