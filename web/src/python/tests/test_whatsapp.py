import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

import schema
from parsers.whatsapp import (chat_name_from_filename, get_participants, parse_whatsapp,
                              read_export, summarize_chat)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def meta(df, i):
    return json.loads(df.loc[i, schema.META])


def msgs(df):
    return df[df[schema.EVENT_TYPE] == "message"].reset_index(drop=True)


# ---------------------------------------------------------------- shared schema

def test_output_matches_shared_schema():
    df = parse_whatsapp(load("android_12h_dmy.txt"), chat_name="Priya")
    assert list(df.columns) == schema.COLUMNS
    assert str(df[schema.TS_UTC].dt.tz) == "UTC"
    assert set(df[schema.SOURCE]) == {"whatsapp"}
    assert set(df[schema.EVENT_TYPE]) <= set(schema.EVENT_TYPES)
    assert df[schema.TITLE].isna().all() and df[schema.VALUE].isna().all()
    assert df[schema.CATEGORY].isna().all()
    assert df[schema.LOCAL_HOUR].dtype == "int64" and df[schema.WEEKDAY].dtype == "int64"
    assert all(isinstance(json.loads(m), dict) for m in df[schema.META])


def test_empty_or_unrelated_text_gives_empty_schema_frame():
    for text in ["", "hello\nthis is not a chat export\n"]:
        df = parse_whatsapp(text)
        assert df.empty and list(df.columns) == schema.COLUMNS


# ---------------------------------------------------------------- Android

def test_android_12h_dmy():
    df = parse_whatsapp(load("android_12h_dmy.txt"), chat_name="Priya")
    assert df.attrs["platform"] == "android" and df.attrs["date_order"] == "DMY"
    assert (df[schema.EVENT_TYPE] == "system").sum() == 1
    assert df.loc[0, schema.ACTOR] is None and "end-to-end encrypted" in df.loc[0, schema.TEXT]
    m = msgs(df)
    assert len(m) == 9
    assert get_participants(df) == ["Priya", "Amogh"]

    # 9:41 pm IST (narrow no-break space) == 16:11 UTC; local fields in IST
    first = m.iloc[0]
    assert first[schema.TS_UTC] == pd.Timestamp("2025-11-17 16:11", tz="UTC")
    assert (first[schema.LOCAL_DATE], first[schema.LOCAL_HOUR], first[schema.WEEKDAY]) == ("2025-11-17", 21, 0)
    assert json.loads(first[schema.META]) == {"chat": "Priya", "platform": "android", "kind": "text"}


def test_android_multiline_media_deleted_edited():
    m = msgs(parse_whatsapp(load("android_12h_dmy.txt")))
    texts = m[schema.TEXT].tolist()
    assert texts[2] == "haan done\nthings to bring:\n1. snacks\n2. charger"
    assert texts[1] == "movie chalein? 🎬"
    # <Media omitted> after a regular no-break space
    assert texts[3] is None and json.loads(m.loc[3, schema.META])["kind"] == "media"
    # both deleted variants
    assert [json.loads(x)["kind"] for x in m.loc[4:5, schema.META]] == ["deleted", "deleted"]
    assert m.loc[4:5, schema.TEXT].isna().all()
    # edited marker stripped; colon inside the text is kept
    assert texts[6] == "see you at 10: don't be late"
    assert json.loads(m.loc[6, schema.META])["edited"] is True


def test_android_12am_and_12pm():
    m = msgs(parse_whatsapp(load("android_12h_dmy.txt")))
    gn, reached = m.iloc[7], m.iloc[8]
    assert (gn[schema.LOCAL_DATE], gn[schema.LOCAL_HOUR]) == ("2025-11-18", 0)
    assert gn[schema.TS_UTC] == pd.Timestamp("2025-11-17 18:35", tz="UTC")  # crosses UTC midnight
    assert reached[schema.LOCAL_HOUR] == 12


def test_android_24h_mdy_group_and_system_lines():
    df = parse_whatsapp(load("android_24h_mdy_group.txt"), chat_name="CSE Batch 27")
    assert df.attrs["date_order"] == "MDY"
    system = df[df[schema.EVENT_TYPE] == "system"][schema.TEXT].tolist()
    assert len(system) == 5
    assert 'Karthik changed the subject from "CSE Batch 27" to "CSE: Batch 27"' in system
    assert "Sneha left" in system and "Karthik added you" in system
    assert get_participants(df) == ["Amogh", "Karthik", "Sneha"]
    assert df[schema.LOCAL_HOUR].tolist()[-1] == 8
    s = summarize_chat(df)
    assert s["is_group"] and s["messages"] == 3 and s["system"] == 5


@pytest.mark.parametrize("line, hour", [
    ("17/11/25, 21:41 - A: x", 21),
    ("17.11.25, 21:41 - A: x", 21),
    ("17/11/2025, 9:41 PM - A: x", 21),
    ("17/11/25, 9:41 p.m. - A: x", 21),
    ("17/11/25, 9:41 am - A: x", 9),
])
def test_android_time_variants(line, hour):
    df = parse_whatsapp(line + "\n")
    assert len(df) == 1 and df.loc[0, schema.LOCAL_HOUR] == hour
    assert df.loc[0, schema.LOCAL_DATE] == "2025-11-17"


def test_ambiguous_dates_use_chronological_order():
    dmy = "01/02/26, 10:00 - A: one\n05/02/26, 10:00 - B: two\n02/03/26, 10:00 - A: three\n"
    mdy = "01/02/26, 10:00 - A: one\n01/05/26, 10:00 - B: two\n02/01/26, 10:00 - A: three\n"
    assert parse_whatsapp(dmy).attrs["date_order"] == "DMY"
    assert parse_whatsapp(mdy).attrs["date_order"] == "MDY"
    assert parse_whatsapp(mdy)[schema.LOCAL_DATE].tolist() == ["2026-01-02", "2026-01-05", "2026-02-01"]


# ---------------------------------------------------------------- iOS

def test_ios_format():
    df = parse_whatsapp(load("ios_chat.txt"), chat_name="Rohan")
    assert df.attrs["platform"] == "ios" and df.attrs["date_order"] == "DMY"
    assert (df[schema.EVENT_TYPE] == "system").sum() == 1  # encryption notice, despite "Rohan:" prefix
    m = msgs(df)
    assert len(m) == 9
    assert get_participants(df) == ["Amogh", "Rohan"]
    assert m.loc[0, schema.TS_UTC] == pd.Timestamp("2025-11-17 16:11:30", tz="UTC")  # seconds kept
    assert m.loc[1, schema.TEXT] == "haan 9 baje\naur record bhi submit karna hai"
    kinds = [json.loads(x) for x in m[schema.META]]
    assert [k.get("media_type") for k in kinds[3:5]] == ["image", "sticker"]
    assert kinds[5]["kind"] == "deleted"
    assert kinds[6] == {"chat": "Rohan", "platform": "ios", "kind": "media", "media_type": "image"}
    assert m.loc[7, schema.TEXT] == "sahi hai" and kinds[7]["edited"] is True
    assert (m.loc[8, schema.LOCAL_DATE], m.loc[8, schema.LOCAL_HOUR]) == ("2025-11-18", 0)


def test_ios_zip_export(tmp_path):
    zpath = tmp_path / "WhatsApp Chat - Rohan.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("_chat.txt", load("ios_chat.txt"))
        zf.writestr("00000012-PHOTO-2025-11-17-21-45-00.jpg", b"\xff\xd8fake")
    text = read_export(zpath.read_bytes(), zpath.name)
    assert chat_name_from_filename(zpath.name) == "Rohan"
    assert len(msgs(parse_whatsapp(text, chat_name="Rohan"))) == 9


def test_read_export_handles_bom_txt():
    raw = ("﻿" + load("android_12h_dmy.txt")).encode("utf-8")
    assert len(parse_whatsapp(read_export(raw, "chat.txt"))) == 10


# ---------------------------------------------------------------- helpers

@pytest.mark.parametrize("name, expected", [
    ("WhatsApp Chat with Priya.txt", "Priya"),
    ("WhatsApp Chat with CSE Batch 27.txt", "CSE Batch 27"),
    ("WhatsApp Chat - Rohan.zip", "Rohan"),
    ("some/folder/WhatsApp Chat with Ishita (2).txt", "Ishita"),
    ("notes.txt", None),
])
def test_chat_name_from_filename(name, expected):
    assert chat_name_from_filename(name) == expected


def test_summary():
    s = summarize_chat(parse_whatsapp(load("android_12h_dmy.txt"), chat_name="Priya"))
    assert s["messages"] == 9 and s["media"] == 1 and s["deleted"] == 2 and s["system"] == 1
    assert s["per_person"] == {"Priya": 5, "Amogh": 4}
    assert (s["first_date"], s["last_date"]) == ("2025-11-17", "2025-11-18")
    assert s["is_group"] is False
    json.dumps(s)  # must be JSON-serialisable for the UI
