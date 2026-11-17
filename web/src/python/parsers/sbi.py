"""SBI account statement -> shared event format.

Pure Python + pandas (stdlib readers; xlrd only for genuine binary .xls), so it runs in
Pyodide and CPython alike.

Input: what OnlineSBI calls an "Excel" statement. The file type is sniffed from the bytes,
because a bank ".xls" can really be binary XLS, XLSX, an HTML table or tab-separated text.
CSV is accepted too. PDF is recognised and rejected with a clear message.

The header block (name, address, CIF, account number, …) is never read into the output:
parsing starts at the row containing "Txn Date". Every run of 9+ digits in stored text is
masked to its last 4 digits, except the 12-digit UPI reference.

    df = parse_sbi(file_bytes, filename="statement.xlsx")
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

import pandas as pd

from schema import (ACTOR, EVENT_TYPE, LOCAL_HOUR, META, SOURCE, TEXT, TITLE, TS_UTC, VALUE,
                    empty_events, finalize_events, local_tz)

SOURCE_NAME = "bank"
PDF_MESSAGE = "Please download the statement as Excel from OnlineSBI (PDF not supported yet)"
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class StatementError(ValueError):
    """A file we recognise but cannot read as an SBI statement (message is user-facing)."""


# ---------------------------------------------------------------- reading the file

def sniff(data: bytes) -> str:
    """-> 'xlsx' | 'xls' | 'pdf' | 'html' | 'text' (by content, not by file extension)."""
    if data[:4] == b"PK\x03\x04":
        return "xlsx"
    if data[:8] == OLE2_MAGIC:
        return "xls"
    if data[:5] == b"%PDF-":
        return "pdf"
    head = data[:4096].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith(b"<") or b"<table" in head or b"<html" in head:
        return "html"
    return "text"


_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _xlsx_rows(data: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).iter(f"{_M}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{_M}t")))
        sheet = None
        try:  # first sheet listed in the workbook
            first = ET.fromstring(zf.read("xl/workbook.xml")).find(f"{_M}sheets/{_M}sheet")
            rid = first.get(f"{_R}id")
            for rel in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels")):
                if rel.get("Id") == rid:
                    target = rel.get("Target").lstrip("/")
                    sheet = target if target.startswith("xl/") else f"xl/{target}"
        except (KeyError, AttributeError, ET.ParseError):
            pass
        if sheet not in names:
            sheet = sorted(n for n in names if n.startswith("xl/worksheets/sheet"))[0]
        rows = []
        for row in ET.fromstring(zf.read(sheet)).iter(f"{_M}row"):
            cells: dict[int, str] = {}
            for i, c in enumerate(row.findall(f"{_M}c")):
                col = _col_index(c.get("r")) if c.get("r") else i
                t, v = c.get("t"), c.find(f"{_M}v")
                if t == "s":
                    val = shared[int(v.text)] if v is not None else ""
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{_M}t"))
                else:
                    val = v.text if v is not None and v.text is not None else ""
                cells[col] = val
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
        return rows


def _xls_rows(data: bytes) -> list[list[str]]:
    try:
        import xlrd  # Pyodide ships it; only needed for genuine binary .xls
    except ImportError as e:  # pragma: no cover - depends on environment
        raise StatementError("This is a binary .xls file and the xlrd package is not available. "
                             "Open it in Excel and save as .xlsx, then import again.") from e
    book = xlrd.open_workbook(file_contents=data)
    sh = book.sheet_by_index(0)
    rows = []
    for r in range(sh.nrows):
        out = []
        for c in range(sh.ncols):
            cell = sh.cell(r, c)
            if cell.ctype == xlrd.XL_CELL_DATE:
                out.append(xlrd.xldate_as_datetime(cell.value, book.datemode).strftime("%d %b %Y"))
            elif cell.ctype == xlrd.XL_CELL_NUMBER:
                out.append(repr(cell.value))
            else:
                out.append(str(cell.value))
        rows.append(out)
    return rows


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _text_rows(text: str) -> list[list[str]]:
    lines = text.splitlines()
    header = next((l for l in lines if "txn date" in l.lower()), lines[0] if lines else "")
    delim = "\t" if "\t" in header else (";" if header.count(";") > header.count(",") else ",")
    return [row for row in csv.reader(io.StringIO(text), delimiter=delim)]


def read_rows(data: bytes) -> tuple[str, list[list[str]]]:
    """-> (sniffed kind, rows of cell strings)."""
    kind = sniff(data)
    if kind == "pdf":
        raise StatementError(PDF_MESSAGE)
    if kind == "xlsx":
        return kind, _xlsx_rows(data)
    if kind == "xls":
        return kind, _xls_rows(data)
    if kind == "html":
        p = _TableParser()
        p.feed(_decode(data))
        return kind, p.rows
    return kind, _text_rows(_decode(data))


# ---------------------------------------------------------------- the statement table

_COLUMNS = {  # our name -> header keywords (first match wins, checked in this order)
    "txn_date": ("txn date", "transaction date", "tran date"),
    "value_date": ("value date",),
    "description": ("description", "narration", "particulars", "remarks"),
    "ref": ("ref no", "cheque", "chq", "reference"),
    "debit": ("debit", "withdrawal"),
    "credit": ("credit", "deposit"),
    "balance": ("balance",),
}


def _norm(s) -> str:
    return " ".join(str(s or "").replace("\xa0", " ").split()).lower().rstrip(":").strip()


def find_header(rows: list[list[str]]) -> int:
    """Index of the row that contains 'Txn Date' (the header block above it varies)."""
    for i, row in enumerate(rows):
        if any(_norm(c) in _COLUMNS["txn_date"] for c in row):
            return i
    raise StatementError("Could not find the 'Txn Date' header row. Is this an SBI account statement?")


def map_columns(header: list[str]) -> dict[str, int]:
    cols: dict[str, int] = {}
    normed = [_norm(c) for c in header]
    for key, words in _COLUMNS.items():
        for i, h in enumerate(normed):
            if i in cols.values() or not h:
                continue
            if (key == "txn_date" and h in words) or (key != "txn_date" and any(w in h for w in words)):
                if key == "credit" and "debit" in h:  # e.g. "Debit/Credit" combined columns
                    continue
                cols[key] = i
                break
    missing = {"txn_date", "description", "balance"} - cols.keys()
    if missing or not ({"debit", "credit"} <= cols.keys()):
        raise StatementError(f"Statement table is missing columns: {sorted(missing | ({'debit', 'credit'} - cols.keys()))}")
    return cols


_DATE_FORMATS = ("%d %b %Y", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d %b %y", "%d-%b-%y", "%d/%m/%y",
                 "%d-%m-%y", "%Y-%m-%d", "%d.%m.%Y", "%d %B %Y")


def parse_date(s) -> date | None:
    s = " ".join(str(s or "").split())
    if not s:
        return None
    if re.fullmatch(r"\d{5}(\.0+)?", s):  # Excel serial day number
        n = int(float(s))
        if 20000 < n < 80000:
            return date(1899, 12, 30) + timedelta(days=n)
    s = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?(\s*[AP]M)?$", "", s, flags=re.I)  # drop a time part
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(s) -> float | None:
    s = str(s or "").replace("\xa0", " ").strip()
    neg = s.startswith("-") or s.upper().endswith("DR")
    s = re.sub(r"(?i)\s*(cr|dr)\.?$", "", s)
    s = re.sub(r"[^\d.]", "", s)
    if not s or s == ".":
        return None
    v = float(s)
    return -v if neg else v


# ---------------------------------------------------------------- narration

def mask_digits(s: str | None, keep: str | None = None) -> str | None:
    """Mask every run of 9+ digits to its last 4 (XXXXXXXXX1234), except `keep`."""
    if s is None:
        return None
    return re.sub(r"\d{9,}", lambda m: m.group(0) if m.group(0) == keep
                  else "X" * (len(m.group(0)) - 4) + m.group(0)[-4:], s)


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = " ".join(s.split()).strip(" -")
    return s or None


_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def parse_narration(desc: str) -> dict:
    """Split an SBI Description into channel / direction / counterparty / … (never raises).

    UPI:      TO TRANSFER-UPI/DR/<12-digit ref>/<payee, cut>/<bank code>/<VPA, cut>/<note>-
              BY TRANSFER-UPI/CR/...
    NEFT:     BY TRANSFER-NEFT*<IFSC>*<UTR>*<NAME>*-
    IMPS:     TO TRANSFER-IMPS/P2A/<ref>/<NAME>/...
    ATM:      ATM WDL-ATM CASH <id> <location>-
    MANDATE:  DEBIT-CMP MANDATE DEBIT <NAME>-
    INTEREST: CREDIT INTEREST--
    """
    d = " ".join(str(desc or "").split())
    up = d.upper()
    out: dict = {"channel": "OTHER", "direction": None, "upi_ref": None, "counterparty": None,
                 "bank_code": None, "vpa_fragment": None, "note": None, "ref": None}
    if up.startswith(("TO TRANSFER", "DEBIT", "ATM WDL", "WDL", "TO CLG", "TO ")):
        out["direction"] = "DR"
    elif up.startswith(("BY TRANSFER", "CREDIT", "BY CLG", "DEP", "BY ")):
        out["direction"] = "CR"

    m = re.search(r"UPI/(DR|CR)/(\d*)/?(.*)$", d, re.I)
    if m:
        out.update(channel="UPI", direction=m.group(1).upper(), upi_ref=m.group(2) or None)
        parts = m.group(3).rstrip("-").split("/") if m.group(3) else []
        parts += [None] * (4 - len(parts))
        out["counterparty"], out["bank_code"], out["vpa_fragment"] = (_clean(p) for p in parts[:3])
        out["note"] = _clean("/".join(p for p in parts[3:] if p)) if len(parts) > 3 else None
        return out

    m = re.search(r"NEFT[*/:\- ]+(.*)$", d, re.I)
    if m:
        out["channel"] = "NEFT"
        tokens = [_clean(t) for t in re.split(r"[*/]", m.group(1).rstrip("-"))]
        tokens = [t for t in tokens if t]
        for t in tokens:
            if _IFSC.match(t):
                out["bank_code"] = t[:4]
            elif out["ref"] is None and re.fullmatch(r"[A-Z0-9]{10,}", t) and re.search(r"\d", t):
                out["ref"] = t
            elif out["counterparty"] is None and re.search(r"[A-Za-z]{2}", t):
                out["counterparty"] = t
        return out

    m = re.search(r"IMPS[*/:\- ]+(.*)$", d, re.I)
    if m:
        out["channel"] = "IMPS"
        tokens = [t for t in (_clean(x) for x in m.group(1).rstrip("-").split("/")) if t]
        for t in tokens:
            if t.upper() in ("P2A", "P2P", "P2M"):
                continue
            if out["ref"] is None and re.fullmatch(r"\d{6,}", t):
                out["ref"] = t
            elif out["counterparty"] is None and re.search(r"[A-Za-z]{2}", t):
                out["counterparty"] = t
            elif out["counterparty"] and out["bank_code"] is None and re.fullmatch(r"[A-Z]{4}", t):
                out["bank_code"] = t
        return out

    if "MANDATE" in up:
        out["channel"] = "MANDATE"
        name = re.split(r"MANDATE(?:\s+DEBIT)?", d, maxsplit=1, flags=re.I)[-1]
        out["counterparty"] = _clean(name)
        out["direction"] = out["direction"] or "DR"
        return out
    if "ATM" in up and ("WDL" in up or "CASH" in up):
        out["channel"] = "ATM"
        out["note"] = _clean(re.sub(r"(?i)^ATM WDL-?", "", d))
        out["direction"] = "DR"
        return out
    if "INTEREST" in up:
        out["channel"] = "INTEREST"
        return out
    return out


# ---------------------------------------------------------------- main entry point

def _actor(n: dict, desc: str) -> str | None:
    if n["channel"] == "ATM":
        return "ATM"
    if n["channel"] == "INTEREST":
        return "SBI Interest"
    if n["counterparty"]:
        return n["counterparty"]
    if n["channel"] == "OTHER":
        label = re.sub(r"(?i)^(TO|BY) TRANSFER-", "", desc).strip(" -")
        return _clean(label[:40])
    return n["channel"]


def parse_sbi(data: bytes | str, filename: str = "") -> pd.DataFrame:
    """Parse an SBI statement into the shared event format (one row per transaction).

    value = signed INR (debit < 0, credit > 0); actor = counterparty / "ATM" / "SBI Interest";
    title = VPA fragment or mandate name; local_hour = NULL (statements have dates only;
    ts_utc = local midnight). The result's .attrs has file_kind / header_row / rows / skipped_rows.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    kind, rows = read_rows(data)
    h = find_header(rows)
    cols = map_columns(rows[h])
    tz = local_tz()

    def cell(row, key):
        i = cols.get(key)
        return row[i] if i is not None and i < len(row) else ""

    out, skipped = [], 0
    for row in rows[h + 1:]:
        d = parse_date(cell(row, "txn_date"))
        if d is None:
            if any(str(c).strip() for c in row):
                skipped += 1  # footer lines, blank-looking rows, repeated headers
            continue
        debit, credit = parse_amount(cell(row, "debit")), parse_amount(cell(row, "credit"))
        balance = parse_amount(cell(row, "balance"))
        if debit is None and credit is None:
            skipped += 1
            continue
        amount = (credit or 0.0) - abs(debit or 0.0)
        raw = " ".join(str(cell(row, "description")).split())
        n = parse_narration(raw)
        keep = n["upi_ref"] if n["upi_ref"] and len(n["upi_ref"]) == 12 else None
        direction = "DR" if amount < 0 else "CR"
        value_date = parse_date(cell(row, "value_date"))
        meta = {
            "channel": n["channel"],
            "direction": direction,
            "upi_ref": keep,
            "counterparty": mask_digits(n["counterparty"]),
            "bank_code": n["bank_code"],
            "vpa_fragment": mask_digits(n["vpa_fragment"]),
            "note": mask_digits(n["note"]),
            "ref_no": mask_digits(_clean(str(cell(row, "ref"))) or (mask_digits(n["ref"]) if n["ref"] else None)),
            "balance": balance,
            "value_date": value_date.isoformat() if value_date else None,
            "raw_description": mask_digits(raw, keep=keep),
        }
        meta = {k: v for k, v in meta.items() if v is not None}
        title = n["vpa_fragment"] if n["channel"] != "MANDATE" else n["counterparty"]
        out.append({
            SOURCE: SOURCE_NAME,
            TS_UTC: datetime(d.year, d.month, d.day),
            EVENT_TYPE: "transaction",
            ACTOR: mask_digits(_actor(n, raw)),
            TITLE: mask_digits(title),
            TEXT: None,
            VALUE: round(amount, 2),
            META: json.dumps(meta, ensure_ascii=False),
        })

    if not out:
        df = empty_events()
    else:
        df = pd.DataFrame(out)
        df[TS_UTC] = pd.to_datetime(df[TS_UTC]).dt.tz_localize(tz).dt.tz_convert("UTC")  # local midnight
        df = finalize_events(df, tz)
    df[LOCAL_HOUR] = pd.array([pd.NA] * len(df), dtype="Int64")  # statements have no time of day
    df.attrs.update(file_kind=kind, header_row=h, rows=len(df), skipped_rows=skipped)
    return df


def balance_breaks(df: pd.DataFrame, tolerance: float = 0.01) -> int:
    """How many rows break `previous balance + value == balance` (0 for a complete statement)."""
    bal = df[META].map(lambda m: json.loads(m).get("balance"))
    expected = bal.shift(1) + df[VALUE]
    return int(((expected - bal).abs() > tolerance).iloc[1:].sum())


def summarize_bank(df: pd.DataFrame, top: int = 10) -> dict:
    """Small JSON-friendly summary (the app computes the same from DuckDB)."""
    spend = -df.loc[df[VALUE] < 0, VALUE]
    days = (pd.to_datetime(df["local_date"].max()) - pd.to_datetime(df["local_date"].min())).days + 1 if len(df) else 0
    by = df[df[VALUE] < 0].groupby(ACTOR)[VALUE]
    return {
        "transactions": int(len(df)),
        "spent": round(float(spend.sum()), 2),
        "received": round(float(df.loc[df[VALUE] > 0, VALUE].sum()), 2),
        "avg_daily_spend": round(float(spend.sum()) / days, 2) if days else None,
        "top_by_spend": [(k, round(-float(v), 2)) for k, v in by.sum().sort_values().head(top).items()],
        "top_by_count": [(k, int(v)) for k, v in by.size().sort_values(ascending=False).head(top).items()],
        "first_date": df["local_date"].min() if len(df) else None,
        "last_date": df["local_date"].max() if len(df) else None,
    }
