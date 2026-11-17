import json
import re
from pathlib import Path

import pandas as pd
import pytest

import schema
from parsers.sbi import (PDF_MESSAGE, StatementError, balance_breaks, find_header, mask_digits,
                         parse_amount, parse_date, parse_narration, parse_sbi, read_rows, sniff)

FIX = Path(__file__).parent / "fixtures" / "sbi"
DEMO = Path(__file__).resolve().parents[4] / "data" / "samples" / "bank" / "SBI_statement_demo.xlsx"
FORMATS = ["statement.xlsx", "statement_tab.xls", "statement_html.xls", "statement.csv"]


def load(name):
    return parse_sbi((FIX / name).read_bytes(), name)


def metas(df):
    return [json.loads(m) for m in df[schema.META]]


# ---------------------------------------------------------------- narration parsing

@pytest.mark.parametrize("desc, expected", [
    ("TO TRANSFER-UPI/DR/512345678902/RAJU TEA/PYTM/paytmqr1y7/UPI-",
     dict(channel="UPI", direction="DR", upi_ref="512345678902", counterparty="RAJU TEA", bank_code="PYTM",
          vpa_fragment="paytmqr1y7", note="UPI")),
    ("BY TRANSFER-UPI/CR/512345678901/SURESH K/SBIN/sureshkuma/Monthly-",
     dict(channel="UPI", direction="CR", counterparty="SURESH K", bank_code="SBIN", note="Monthly")),
    # truncated by the bank mid-field
    ("TO TRANSFER-UPI/DR/512345678905/MAIN CAN/PY",
     dict(channel="UPI", counterparty="MAIN CAN", bank_code="PY", vpa_fragment=None, note=None)),
    # cut right after the reference
    ("TO TRANSFER-UPI/DR/5123456789",
     dict(channel="UPI", upi_ref="5123456789", counterparty=None)),
    ("TO TRANSFER-UPI/DR/", dict(channel="UPI", upi_ref=None, counterparty=None)),
    # empty note, double dash, note containing a slash
    ("TO TRANSFER-UPI/DR/512345678908/ZOMATO/HDFC/zomato.ord/", dict(counterparty="ZOMATO", note=None)),
    ("BY TRANSFER-UPI/CR/512345678909/ROHAN KU/ICIC/rohank98@o/UPI--", dict(direction="CR", note="UPI")),
    ("TO TRANSFER-UPI/DR/512345678910/PRIYA SH/HDFC/priyasharm/dinner/movie-", dict(note="dinner/movie")),
    ("BY TRANSFER-NEFT*HDFC0004321*N312345678901*PIXELCRAFT STUDIO*-",
     dict(channel="NEFT", direction="CR", counterparty="PIXELCRAFT STUDIO", bank_code="HDFC", ref="N312345678901")),
    ("TO TRANSFER-IMPS/P2A/612345678906/ROHAN KUMAR/ICIC/rohank98@o-",
     dict(channel="IMPS", direction="DR", ref="612345678906", counterparty="ROHAN KUMAR", bank_code="ICIC")),
    ("ATM WDL-ATM CASH 4521 SBI JAYANAGAR 4TH BLOCK BANGALORE-",
     dict(channel="ATM", direction="DR", note="ATM CASH 4521 SBI JAYANAGAR 4TH BLOCK BANGALORE")),
    ("DEBIT-CMP MANDATE DEBIT SPOTIFY-", dict(channel="MANDATE", direction="DR", counterparty="SPOTIFY")),
    ("CREDIT INTEREST--", dict(channel="INTEREST", direction="CR")),
    ("TO TRANSFER-INB 00000012345678901 SBI General Insurance-", dict(channel="OTHER", direction="DR")),
    ("DEBIT CARD ANNUAL FEE AND GST-", dict(channel="OTHER", direction="DR")),
    ("", dict(channel="OTHER", direction=None)),
    ("???///***", dict(channel="OTHER")),
])
def test_parse_narration(desc, expected):
    got = parse_narration(desc)
    for k, v in expected.items():
        assert got[k] == v, (k, got)


# ---------------------------------------------------------------- reading files

@pytest.mark.parametrize("name, kind", [("statement.xlsx", "xlsx"), ("statement_tab.xls", "text"),
                                        ("statement_html.xls", "html"), ("statement.csv", "text"),
                                        ("statement.pdf", "pdf")])
def test_sniff_uses_content_not_extension(name, kind):
    assert sniff((FIX / name).read_bytes()) == kind


def test_binary_xls_magic_is_recognised():
    assert sniff(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100) == "xls"


@pytest.mark.parametrize("name", FORMATS)
def test_header_row_found_after_header_block(name):
    _, rows = read_rows((FIX / name).read_bytes())
    assert find_header(rows) == 9


@pytest.mark.parametrize("name", FORMATS)
def test_every_format_gives_the_same_events(name):
    df = load(name)
    ref = load("statement.xlsx")
    assert list(df.columns) == schema.COLUMNS
    assert len(df) == 14 and df.attrs["skipped_rows"] == 1  # the footer line
    pd.testing.assert_frame_equal(df.reset_index(drop=True), ref.reset_index(drop=True))


def test_mapping_signed_amounts_and_dates():
    df = load("statement.xlsx")
    assert set(df[schema.SOURCE]) == {"bank"} and set(df[schema.EVENT_TYPE]) == {"transaction"}
    assert df[schema.VALUE].tolist()[:4] == [15000.0, -25.0, -20.0, -349.0]
    assert df[schema.VALUE].sum() == pytest.approx(21409.0 - 5000.0)
    first = df.iloc[0]
    # date-only: ts_utc = local midnight (1 Mar 00:00 IST = 28 Feb 18:30 UTC); hour unknown
    assert first[schema.TS_UTC] == pd.Timestamp("2026-02-28 18:30", tz="UTC")
    assert first[schema.LOCAL_DATE] == "2026-03-01" and first[schema.WEEKDAY] == 6
    assert df[schema.LOCAL_HOUR].isna().all()
    actors = df[schema.ACTOR].tolist()
    assert actors[0] == "SURESH K" and "ATM" in actors and "SBI Interest" in actors and "SPOTIFY" in actors
    m = metas(df)
    assert m[0]["direction"] == "CR" and m[1]["direction"] == "DR" and m[1]["balance"] == 19975.0
    assert df[schema.TITLE].tolist()[1] == "paytmqr1y7"
    assert df[df[schema.ACTOR] == "SPOTIFY"][schema.TITLE].iloc[0] == "SPOTIFY"  # mandate name


def test_balance_is_continuous():
    assert balance_breaks(load("statement.xlsx")) == 0


# ---------------------------------------------------------------- privacy

def _all_strings(df):
    for col in (schema.ACTOR, schema.TITLE, schema.TEXT, schema.CATEGORY):
        yield from (v for v in df[col] if isinstance(v, str))
    for m in df[schema.META]:
        yield m


@pytest.mark.parametrize("name", FORMATS)
def test_no_long_digit_runs_survive_except_upi_refs(name):
    df = load(name)
    upi_refs = {x.get("upi_ref") for x in metas(df)} - {None}
    assert upi_refs and all(len(r) == 12 for r in upi_refs)
    for s in _all_strings(df):
        for run in re.findall(r"\d{9,}", s):
            assert run in upi_refs, (run, s)


def test_header_block_is_never_stored():
    blob = " ".join(_all_strings(load("statement.xlsx")))
    for secret in ("TEST PERSON", "TEST ROAD", "31234567890", "85012345678", "SBIN0001234"):
        assert secret not in blob


def test_masking_details():
    assert mask_digits("TRANSFER TO 4897691162091") == "TRANSFER TO XXXXXXXXX2091"
    assert mask_digits("9845012736@ybl") == "XXXXXX2736@ybl"
    assert mask_digits("UPI/DR/512345678901/X", keep="512345678901") == "UPI/DR/512345678901/X"
    assert mask_digits("ref 12345678") == "ref 12345678"  # 8 digits: not account-like
    m = metas(load("statement.xlsx"))
    assert m[2]["vpa_fragment"] == "XXXXXX2736"           # phone-number VPA
    assert m[0]["ref_no"] == "TRANSFER FROM XXXXXXXXX1121"
    assert "XXXXXXXXXXXXX8901" in m[9]["raw_description"]  # 17-digit number in an INB narration


# ---------------------------------------------------------------- helpers + errors

@pytest.mark.parametrize("s, d", [("13 Aug 2026", "2026-08-13"), ("13-Aug-2026", "2026-08-13"),
                                  ("13/08/2026", "2026-08-13"), ("13-08-26", "2026-08-13"),
                                  ("46247", "2026-08-13"), ("13 Aug 2026 10:15", "2026-08-13"),
                                  ("", None), ("Txn Date", None)])
def test_parse_date(s, d):
    got = parse_date(s)
    assert (got.isoformat() if got else None) == d


@pytest.mark.parametrize("s, v", [("1,23,456.78", 123456.78), ("25.00", 25.0), (" ", None), ("-", None),
                                  ("500.00 Cr", 500.0), ("500.00 Dr", -500.0), ("₹ 1,200", 1200.0), (None, None)])
def test_parse_amount(s, v):
    assert parse_amount(s) == v


def test_pdf_is_rejected_with_a_clear_message():
    with pytest.raises(StatementError, match="download the statement as Excel"):
        load("statement.pdf")
    assert "PDF not supported yet" in PDF_MESSAGE


def test_not_a_statement():
    with pytest.raises(StatementError, match="Txn Date"):
        parse_sbi(b"name,amount\nx,1\n", "other.csv")


# ---------------------------------------------------------------- demo statement

@pytest.fixture(scope="module")
def demo():
    return parse_sbi(DEMO.read_bytes(), DEMO.name)


def test_demo_statement(demo):
    assert demo.attrs["file_kind"] == "xlsx" and demo.attrs["header_row"] == 17
    assert len(demo) == 2629 and demo.attrs["skipped_rows"] == 1
    assert (demo["local_date"].min(), demo["local_date"].max()) == ("2025-11-17", "2026-11-16")
    assert balance_breaks(demo) == 0
    balances = [json.loads(m)["balance"] for m in demo[schema.META]]
    assert min(balances) >= 0
    channels = {json.loads(m)["channel"] for m in demo[schema.META]}
    assert channels == {"UPI", "NEFT", "ATM", "MANDATE", "INTEREST"}
    assert "DEMO USER" not in " ".join(_all_strings(demo))
