"""SEC EDGAR access for the issuer corpus: fund N-PORT filings, issuer matching and minimum packs.

Every request names its sender from the SEC_USER_AGENT environment variable, because the SEC asks
automated clients for a contact; nothing here stores it. Requests stay below the SEC's rate
limit and retry a bounded number of times. Nothing here performs analysis.

The minimum pack for one issuer is the latest 10-K, the three latest 10-Qs and the three latest
quarterly presentations filed as 8-K exhibits. A presentation the issuer posts only on its own
website is not on EDGAR and is recorded as a gap.
"""

import argparse
import gzip
import hashlib
import html
import html.parser
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

Get = Callable[[str], bytes]
UA_VARIABLE = "SEC_USER_AGENT"
INTERVAL = 0.15  # Seconds between requests: under 7 per second; the SEC allows 10.
RETRIES = 3
RETRYABLE = frozenset({429, 500, 502, 503, 504})
WWW, DATA, EFTS = "https://www.sec.gov", "https://data.sec.gov", "https://efts.sec.gov"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
# An earnings deck filed as an exhibit. The XBRL "presentation linkbase" is not an EX-99 exhibit.
PRESENTATION = re.compile(r"presentation|slides|deck|earnings call|webcast", re.IGNORECASE)
NEAR_PERIODIC = timedelta(days=10)  # An earnings 8-K is filed close to its 10-Q or 10-K.
MIN_DECK_TEXT = 2000  # Fewer visible characters than this: slides are images, not text.
HEAD_BYTES = 8192
FOREIGN_ANNUAL = ("20-F", "40-F")
# Foreign private issuers furnish quarterly results on 6-K with generic exhibit labels, so the
# exhibit's opening text decides what it is.
INTERIM = re.compile(
    r"interim (condensed )?(consolidated )?financial statements|condensed (consolidated )?interim"
    r"|management.s discussion and analysis|interim report|quarterly report"
    r"|half[- ]year(ly)? (financial )?report",
    re.IGNORECASE,
)
RESULTS = re.compile(
    r"reports? .{0,80}(first|second|third|fourth|q[1-4]|quarter|half[- ]year|full[- ]year)"
    r".{0,40}results|results for (the )?(first|second|third|fourth) quarter"
    r"|(quarter|half[- ]year|nine months|interim) .{0,20}results",
    re.IGNORECASE,
)
DECK_TEXT = re.compile(r"(investor|earnings|results|financial) presentation", re.IGNORECASE)
CERTIFICATION = re.compile(r"certification of interim filings|52-109F", re.IGNORECASE)
EVENT_GAP = timedelta(days=45)  # Two quarters' results are at least this far apart.


class Edgar:
    """Rate-limited, retrying HTTPS GET for SEC hosts."""

    def __init__(self, user_agent: str) -> None:
        if not user_agent.strip():
            raise ValueError(f"edgar: set {UA_VARIABLE} to a name and contact e-mail")
        self.user_agent = user_agent
        self.last = 0.0

    def __call__(self, url: str) -> bytes:
        return self.fetch(url, None)

    def head(self, url: str) -> bytes:
        """The document's first bytes, enough to read its title. EDGAR ignores Range requests,
        so the connection is closed after reading them."""
        return self.fetch(url, HEAD_BYTES)

    def fetch(self, url: str, limit: int | None) -> bytes:
        headers = {"User-Agent": self.user_agent}
        if limit is None:
            headers["Accept-Encoding"] = "gzip"
        for attempt in range(RETRIES + 1):
            time.sleep(max(0.0, self.last + INTERVAL - time.monotonic()))
            self.last = time.monotonic()
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    body: bytes = response.read() if limit is None else response.read(limit)
                    gzipped = response.headers.get("Content-Encoding") == "gzip"
                    return gzip.decompress(body) if gzipped else body
            except urllib.error.HTTPError as error:
                if error.code not in RETRYABLE or attempt == RETRIES:
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == RETRIES:
                    raise
            time.sleep(2 ** (attempt + 1))
        raise AssertionError("unreachable")


def latest_nport(get: Get, series_id: str) -> dict[str, str]:
    """The series' most recent public N-PORT filing and its XML document."""
    feed = get(
        f"{WWW}/cgi-bin/browse-edgar?action=getcompany&CIK={series_id}&type=NPORT-P"
        "&dateb=&owner=include&count=10&output=atom"
    )
    entry = ET.fromstring(feed).find("a:entry/a:content", ATOM)
    if entry is None:
        raise ValueError(f"edgar: no NPORT-P filing for series {series_id}")
    fields = {child.tag.split("}")[1]: (child.text or "").strip() for child in entry}
    folder = fields["filing-href"].rsplit("/", 1)[0]
    return {
        "series_id": series_id,
        "accession": fields["accession-number"],
        "filing_date": fields["filing-date"],
        "url": f"{folder}/primary_doc.xml",
    }


def fund_series(get: Get, tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Ticker to registrant CIK and series, from the SEC's fund ticker file."""
    table = json.loads(get(f"{WWW}/files/company_tickers_mf.json"))
    rows = {r[3]: dict(zip(table["fields"], r, strict=True)) for r in table["data"]}
    missing = [t for t in tickers if t not in rows]
    if missing:
        raise ValueError(f"edgar: no fund series for {', '.join(missing)}")
    return {t: rows[t] for t in tickers}


SUFFIXES = frozenset(
    {
        "INC",
        "INCORPORATED",
        "CORP",
        "CORPORATION",
        "CO",
        "COMPANY",
        "LLC",
        "LP",
        "LTD",
        "LIMITED",
        "PLC",
        "SA",
        "NV",
        "AG",
        "SE",
        "SARL",
        "THE",
        "DE",
    }
)
ABBREVIATIONS = {
    "HLDGS": "HOLDINGS",
    "HLDG": "HOLDING",
    "INTL": "INTERNATIONAL",
    "GRP": "GROUP",
    "SVCS": "SERVICES",
    "MFG": "MANUFACTURING",
    "COS": "COMPANIES",
    "ENTMT": "ENTERTAINMENT",
    "COMMS": "COMMUNICATIONS",
}


def name_key(name: str) -> str:
    """Comparable form of an issuer name: first co-issuer only, no punctuation, legal suffix or
    loan maturity date (loan holdings are often printed as "CAESAR 01/23/30")."""
    upper = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", " ", name.upper())
    first = re.sub(r"\s*\([A-Z0-9.,\- ]+\)\s*$", "", upper).split("/")[0]
    words = re.sub(r"[^A-Z0-9 ]", " ", first.replace("&", " AND ")).split()
    words = [ABBREVIATIONS.get(w, w) for w in words]
    while words and (words[-1] in SUFFIXES or words[-1].isdigit()):
        words.pop()
    return " ".join(words)


def entity_candidates(get: Get, name: str) -> list[dict[str, str]]:
    """EDGAR entities whose name has the same key. The high-yield bond funds print issuer names
    cut at exactly 24 characters (291 of 1,324 HYG holdings), so only such a name may match an
    entity whose key it begins."""
    key = name_key(name)
    if len(key) < 3:
        return []
    query = urllib.parse.quote(key.lower())
    hits = json.loads(get(f"{EFTS}/LATEST/search-index?keysTyped={query}"))["hits"]["hits"]
    truncated = len(name) == 24 and len(key) >= 10
    found = []
    for hit in hits:
        entity = hit["_source"]["entity"]
        other = name_key(entity)
        if other == key or (truncated and other.startswith(key)):
            basis = "name keys equal" if other == key else "truncated name begins entity name"
            found.append({"cik": hit["_id"], "entity": entity, "basis": basis})
    return found


def filings(get: Get, cik: str) -> list[dict[str, str]]:
    recent = json.loads(get(f"{DATA}/submissions/CIK{int(cik):010d}.json"))["filings"]["recent"]
    return [dict(zip(recent, values, strict=True)) for values in zip(*recent.values(), strict=True)]


def exhibits(get: Get, cik: str, accession: str) -> list[dict[str, str]]:
    """The documents an EDGAR filing index lists: type, description and URL."""
    folder = f"{WWW}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
    page = get(f"{folder}/{accession}-index.htm").decode("utf-8", "replace")
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.DOTALL):
        cells = [
            html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
            for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        ]
        link = re.search(r'href="(/Archives/[^"]+)"', row)
        if len(cells) >= 4 and link:
            rows.append(
                {
                    "description": cells[1],
                    "document": cells[2].split()[0] if cells[2] else "",
                    "type": cells[3],
                    "url": WWW + link[1],
                }
            )
    return rows


def minimum_pack(get: Get, cik: str, as_of: date) -> dict[str, Any]:
    """Select the latest 10-K, the three latest 10-Qs and, for each of the three latest quarterly
    results, the deck filed as an 8-K exhibit. Where a quarter's deck is not on EDGAR, that
    quarter's earnings release (EX-99.1) is kept instead and labelled as a release."""
    rows = [f for f in filings(get, cik) if f["filingDate"] <= as_of.isoformat()]
    folder = f"{WWW}/Archives/edgar/data/{int(cik)}"

    def document(f: dict[str, str]) -> dict[str, str]:
        return {
            "form": f["form"],
            "filing_date": f["filingDate"],
            "report_date": f["reportDate"],
            "accession": f["accessionNumber"],
            "url": f"{folder}/{f['accessionNumber'].replace('-', '')}/{f['primaryDocument']}",
        }

    annual = [document(f) for f in rows if f["form"] == "10-K"][:1]
    if not annual and any(f["form"] in FOREIGN_ANNUAL for f in rows):
        return foreign_pack(get, cik, rows, as_of, document)
    quarterly = [document(f) for f in rows if f["form"] == "10-Q"][:3]
    results = sorted(annual + quarterly, key=lambda d: d["filing_date"], reverse=True)[:3]
    earnings = [
        f for f in rows if f["form"] == "8-K" and {"2.02", "7.01"} & set(f["items"].split(","))
    ]
    decks: list[dict[str, str]] = []
    releases: list[dict[str, str]] = []
    missing = []
    for period in results:
        filed = date.fromisoformat(period["filing_date"])
        deck = release = None
        for f in earnings:
            if abs(date.fromisoformat(f["filingDate"]) - filed) > NEAR_PERIODIC:
                continue
            for exhibit in exhibits(get, cik, f["accessionNumber"]):
                found = {**document(f), "form": exhibit["type"], "url": exhibit["url"]}
                found["period"] = period["report_date"]
                label = f"{exhibit['description']} {exhibit['document']}"
                if exhibit["type"].startswith("EX-99") and PRESENTATION.search(label):
                    deck = deck or found
                elif exhibit["type"] == "EX-99.1" and "2.02" in f["items"]:
                    release = release or found
            if deck:
                break
        if deck:
            decks.append(deck)
        elif release:
            releases.append(release)
        else:
            missing.append(period["report_date"])
    gaps = []
    if not annual:
        gaps.append("no 10-K filed by the as-of date")
    if len(quarterly) < 3:
        gaps.append(f"{len(quarterly)} of 3 10-Qs")
    if releases:
        gaps.append(f"{len(releases)} of 3 quarters have a release, not a presentation, on EDGAR")
    if missing:
        gaps.append(f"no quarterly results document on EDGAR for {', '.join(missing)}")
    stale = not annual or (as_of - date.fromisoformat(annual[0]["filing_date"])).days > 400
    if annual and stale:
        gaps.append("latest 10-K older than 400 days")
    filings_complete = not stale and len(quarterly) == 3
    return {
        "cik": str(int(cik)),
        "annual": annual,
        "quarterly": quarterly,
        "presentations": decks,
        "releases_instead_of_presentations": releases,
        "files_10k": not stale,
        "complete": filings_complete and len(decks) == 3,
        "complete_with_releases": filings_complete and len(decks) + len(releases) == 3,
        "gaps": gaps,
    }


def foreign_pack(
    get: Get,
    cik: str,
    rows: list[dict[str, str]],
    as_of: date,
    document: Callable[[dict[str, str]], dict[str, str]],
) -> dict[str, Any]:
    """A foreign private issuer's pack: the latest 20-F or 40-F, the three latest interim reports
    furnished on 6-K (financial statements or MD&A, standing in for 10-Qs) and, for the three
    latest results events, the deck, else the results release. 6-Ks filed within ten days are one
    results event; two events at least 45 days apart are two quarters."""
    head: Get = getattr(get, "head", get)
    annual = [document(f) for f in rows if f["form"] in FOREIGN_ANNUAL][:1]
    events: list[dict[str, Any]] = []
    for f in rows:
        filed = date.fromisoformat(f["filingDate"])
        reported = [e for e in events if e["interim"]]
        # Stop after the third quarter's window: its release often comes days before its report.
        if (as_of - filed).days > 400 or (
            len(reported) >= 3 and reported[2]["date"] - filed > NEAR_PERIODIC
        ):
            break
        if f["form"] != "6-K":
            continue
        found: dict[str, dict[str, str]] = {}
        for exhibit in exhibits(get, cik, f["accessionNumber"]):
            if not exhibit["type"].startswith("EX-99") or exhibit["document"].endswith(".pdf"):
                continue
            opening = visible_text(head(exhibit["url"]))[:1500]
            label = f"{exhibit['description']} {exhibit['document']} {opening}"
            kind = (
                None
                if CERTIFICATION.search(opening)
                else "deck"
                if PRESENTATION.search(f"{exhibit['description']} {exhibit['document']}")
                or DECK_TEXT.search(opening)
                else "interim"
                if INTERIM.search(label)
                else "release"
                if RESULTS.search(label)
                else None
            )
            if kind and kind not in found:
                item = {**document(f), "form": f"6-K-{exhibit['type']}", "url": exhibit["url"]}
                found[kind] = {**item, "period": f["reportDate"]}
        if not found:
            continue
        latest = events[-1] if events else None
        if latest and (latest["date"] - filed) <= NEAR_PERIODIC:
            for kind, item in found.items():
                latest[kind] = latest.get(kind) or item
        elif not latest or (latest["date"] - filed) >= EVENT_GAP:
            events.append({"date": filed, "interim": None, "deck": None, "release": None, **found})
    # As for a 10-K filer: the three latest interim reports, wherever they fall, and the deck or
    # release of the three latest results events, which can include the full-year results.
    quarterly = [e["interim"] for e in events if e["interim"]][:3]
    decks = [e["deck"] for e in events[:3] if e["deck"]]
    releases = [e["release"] for e in events[:3] if not e["deck"] and e["release"]]
    stale = not annual or (as_of - date.fromisoformat(annual[0]["filing_date"])).days > 400
    gaps = ["interim results furnished on 6-K, not 10-Q (foreign private issuer)"]
    if not annual:
        gaps.append("no 20-F or 40-F filed by the as-of date")
    elif stale:
        gaps.append(f"latest {annual[0]['form']} older than 400 days")
    if len(quarterly) < 3:
        gaps.append(f"{len(quarterly)} of 3 interim reports on 6-K")
    if releases:
        gaps.append(f"{len(releases)} of 3 quarters have a release, not a presentation, on EDGAR")
    filings_complete = not stale and len(quarterly) == 3
    return {
        "cik": str(int(cik)),
        "filer": "foreign private issuer",
        "annual": annual,
        "quarterly": quarterly,
        "presentations": decks,
        "releases_instead_of_presentations": releases,
        "files_10k": False,
        "files_20f_or_40f": not stale,
        "complete": filings_complete and len(decks) == 3,
        "complete_with_releases": filings_complete and len(decks) + len(releases) == 3,
        "gaps": gaps,
    }


class _VisibleText(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.hidden += tag in ("script", "style")

    def handle_endtag(self, tag: str) -> None:
        self.hidden -= tag in ("script", "style") and self.hidden > 0

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def visible_text(raw: bytes) -> str:
    """Visible text of an HTML document, whitespace collapsed."""
    parser = _VisibleText()
    parser.feed(raw.decode("utf-8", "replace"))
    parser.close()
    return " ".join("".join(parser.parts).split())


def visible_text_chars(raw: bytes) -> int:
    return len(visible_text(raw))


def fetch_pack(get: Get, pack: dict[str, Any], folder: Path) -> list[dict[str, Any]]:
    """Download the pack's documents into a new folder, with a retrieval record."""
    folder.mkdir(parents=True)
    record = []
    for item in (
        pack["annual"]
        + pack["quarterly"]
        + pack["presentations"]
        + pack["releases_instead_of_presentations"]
    ):
        raw = get(item["url"])
        period = item["report_date"] or item["filing_date"]
        name = f"{item['form']}_{period}_{item['url'].rsplit('/', 1)[1]}"
        (folder / name).write_bytes(raw)
        entry = {**item, "file": name, "sha256": hashlib.sha256(raw).hexdigest()}
        if "EX-99" in item["form"]:
            entry["visible_text_chars"] = visible_text_chars(raw)
            entry["image_only"] = entry["visible_text_chars"] < MIN_DECK_TEXT
        record.append(entry)
    retrieval = {"retrieved": date.today().isoformat(), "pack": pack, "files": record}
    # The launcher ignores "_" names, so the record is never pinned as issuer evidence.
    (folder / "_retrieval.json").write_text(json.dumps(retrieval, indent=2) + "\n")
    return record


def pack_folder(entry: dict[str, Any]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", entry["entity"].lower()).strip("-")[:40].strip("-")
    return f"{entry['cik']}-{slug}"


def fetch_packs(get: Get, result: dict[str, Any], out: Path) -> list[dict[str, Any]]:
    """Download the pack of every corpus issuer usable for the `minimum` set. A pack is written to
    a temporary folder and renamed when complete, so a rerun keeps finished packs and redoes only
    an interrupted one."""
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for entry in result["issuers"]:
        if not entry["pack"]["complete_with_releases"]:
            continue
        folder = out / pack_folder(entry)
        if not folder.exists():
            partial = out / (folder.name + ".partial")
            if partial.exists():
                shutil.rmtree(partial)  # This command's own unfinished download.
            fetch_pack(get, entry["pack"], partial)
            partial.rename(folder)
        files = json.loads((folder / "_retrieval.json").read_text())["files"]
        index.append(
            {
                "cik": entry["cik"],
                "entity": entry["entity"],
                "folder": folder.name,
                "kinds": entry["kinds"],
                "documents": len(files),
                "presentations": len(entry["pack"]["presentations"]),
                "releases": len(entry["pack"]["releases_instead_of_presentations"]),
                "image_only_decks": sum(bool(f.get("image_only")) for f in files),
            }
        )
        print(f"{len(index):4d} {folder.name}", flush=True)
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return index


def corpus(
    get: Get,
    universe: dict[str, Any],
    target: int,
    as_of: date,
    log: Callable[[str], None],
    save: Callable[[dict[str, Any]], None] | None = None,
    prior: dict[str, Any] | None = None,
    non_us: bool = False,
) -> dict[str, Any]:
    """Issuers with current SEC annual reports (10-K, or 20-F or 40-F for a foreign private
    issuer) and complete minimum packs, loan issuers first. The target counts packs complete with
    releases standing in for decks that are not on EDGAR; packs with three decks are counted
    separately as `complete`. `save` receives the result after every issuer, marked in progress;
    `prior` is such a result to resume from.

    With `non_us`, `prior` is a finished corpus to extend: only issuers that no fund lists in the
    US are checked, including those an earlier pass checked under the 10-K rule alone, and the
    target counts usable packs of such issuers, those already in `prior` included."""
    countries = {r["key"]: r["countries"] for r in universe["issuers"]}
    pass_name = "non-US" if non_us else None

    def foreign(keys: list[str]) -> bool:
        return all("US" not in countries[k] for k in keys)

    def counted(c: dict[str, Any]) -> bool:
        return bool(c["pack"]["complete_with_releases"]) and (
            not non_us or foreign(c["issuer_keys"])
        )

    candidates = sorted(
        (r for r in universe["issuers"] if not non_us or foreign([r["key"]])),
        key=lambda r: (
            "loan" not in r["kinds"],
            -len(r["funds"]),
            -sum(Decimal(f["value_usd"] or 0) for f in r["funds"].values()),
        ),
    )
    chosen: dict[str, dict[str, Any]] = {c["cik"]: c for c in (prior or {}).get("issuers", [])}
    checked: list[dict[str, Any]] = list((prior or {}).get("checked", []))
    done = {c["key"] for c in checked if c.get("pass") == pass_name}
    done |= {k for c in chosen.values() for k in c["issuer_keys"]}
    main_target = (prior or {}).get("target_complete", target) if non_us else target
    non_us_target = target if non_us else (prior or {}).get("non_us_target")
    seen: dict[str, list[dict[str, str]]] = {}  # One EDGAR name search per distinct name key.

    def result(status: str) -> dict[str, Any]:
        rows = sorted(
            chosen.values(),
            key=lambda c: (
                not c["pack"]["complete_with_releases"],
                not c["pack"]["complete"],
                "loan" not in c["kinds"],
            ),
        )
        for c in rows:
            c["countries"] = sorted({x for k in c["issuer_keys"] for x in countries[k]})
        usable = [c for c in rows if c["pack"]["complete_with_releases"]]
        value = {
            "schema": "issuer-corpus/1",
            "status": status,
            "as_of": as_of.isoformat(),
            "universe_funds": [f["seriesName"] for f in universe["funds"]],
            "target_complete": main_target,
            "complete_with_releases": len(usable),
            "complete_with_three_presentations": sum(c["pack"]["complete"] for c in rows),
            "loan_issuers_complete_with_releases": sum("loan" in c["kinds"] for c in usable),
            "non_us_complete_with_releases": sum(foreign(c["issuer_keys"]) for c in usable),
            "filers_checked": len(rows),
            "issuers": rows,
            "checked": checked,
        }
        if non_us_target is not None:
            value["non_us_target"] = non_us_target
        return value

    for issuer in candidates:
        if sum(counted(c) for c in chosen.values()) >= target:
            break
        if issuer["key"] in done:
            continue
        names = issuer["names"]
        outcome: dict[str, Any] = {"key": issuer["key"], "names": names, "kinds": issuer["kinds"]}
        if pass_name:
            outcome["pass"] = pass_name
        for n in names:
            if name_key(n) not in seen:
                seen[name_key(n)] = entity_candidates(get, n)
        matches = [m for n in names for m in seen[name_key(n)]]
        for match in {m["cik"]: m for m in matches}.values():
            if match["cik"] in chosen:
                chosen[match["cik"]]["issuer_keys"].append(issuer["key"])
                outcome["result"] = f"same SEC filer as {match['entity']}"
                break
            try:
                pack = minimum_pack(get, match["cik"], as_of)
            except urllib.error.HTTPError as error:
                # A missing record is this issuer's outcome; other failures stop the run, which
                # the saved result lets the same command resume.
                if error.code != 404:
                    raise
                outcome.setdefault("errors", []).append(f"CIK {match['cik']}: {error}")
                continue
            if pack["files_10k"] or pack.get("files_20f_or_40f"):
                chosen[match["cik"]] = {
                    "cik": match["cik"],
                    "entity": match["entity"],
                    "issuer_keys": [issuer["key"]],
                    "nport_names": names,
                    "kinds": issuer["kinds"],
                    "funds": issuer["funds"],
                    "match_basis": match["basis"],
                    "pack": pack,
                }
                outcome["result"] = (
                    "complete pack"
                    if pack["complete"]
                    else "complete with releases"
                    if pack["complete_with_releases"]
                    else "partial pack"
                )
                break
        else:
            outcome["result"] = (
                "no matching filer of a current 10-K, 20-F or 40-F"
                if matches
                else "no EDGAR name match"
            )
        checked.append(outcome)
        log(f"{len(checked):4d} {outcome['result']:<24} {names[0]}")
        if save is not None:
            save(result("in progress"))
    return result("done")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m secdata.edgar")
    command = parser.add_subparsers(dest="command", required=True)
    nport = command.add_parser("nport", help="fetch the latest N-PORT filing of each fund")
    nport.add_argument("--tickers", nargs="+", required=True)
    nport.add_argument("--out", type=Path, required=True, help="new folder")
    build = command.add_parser("corpus", help="match a universe to filers with full packs")
    build.add_argument("--universe", type=Path, required=True)
    build.add_argument("--target", type=int, default=100)
    build.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    build.add_argument("--out", type=Path, required=True, help="JSON file; resumed if in progress")
    build.add_argument(
        "--non-us", action="store_true", help="extend --base with issuers no fund lists in the US"
    )
    build.add_argument("--base", type=Path, help="finished corpus that --non-us extends")
    every = command.add_parser("packs", help="download the pack of every usable corpus issuer")
    every.add_argument("--corpus", type=Path, required=True)
    every.add_argument("--out", type=Path, required=True, help="folder; finished packs are kept")
    pack = command.add_parser("pack", help="download one issuer's minimum pack")
    pack.add_argument("--cik", required=True)
    pack.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    pack.add_argument("--out", type=Path, required=True, help="new folder")
    args = parser.parse_args(argv)
    try:
        get = Edgar(os.environ.get(UA_VARIABLE, ""))
        if args.command == "nport":
            series = fund_series(get, args.tickers)
            args.out.mkdir(parents=True)
            record = []
            for ticker, row in series.items():
                filing = latest_nport(get, row["seriesId"])
                raw = get(filing["url"])
                held = ET.fromstring(raw).findtext(".//{*}genInfo/{*}repPdDate") or "undated"
                name = f"{ticker}-{held}-NPORT.xml"
                (args.out / name).write_bytes(raw)
                record.append(
                    {
                        "ticker": ticker,
                        **filing,
                        "file": name,
                        "holdings_date": held,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                )
                print(f"{ticker}: {name} ({filing['accession']})", flush=True)
            retrieval = {"retrieved": date.today().isoformat(), "filings": record}
            (args.out / "retrieval.json").write_text(json.dumps(retrieval, indent=2) + "\n")
        elif args.command == "corpus":
            universe = json.loads(args.universe.read_text())
            if args.non_us != (args.base is not None):
                raise ValueError("edgar: --non-us and --base go together")
            target_field = "non_us_target" if args.non_us else "target_complete"
            prior = json.loads(args.out.read_text()) if args.out.exists() else None
            if prior is not None and (
                prior.get("status") != "in progress"
                or (prior["as_of"], prior.get(target_field))
                != (args.as_of.isoformat(), args.target)
            ):
                raise ValueError(f"edgar: {args.out} is finished or for another request")
            if prior is None and args.base is not None:
                prior = json.loads(args.base.read_text())
                if prior.get("status") != "done" or prior["as_of"] != args.as_of.isoformat():
                    raise ValueError(f"edgar: {args.base} is not a finished corpus of that date")

            def save(value: dict[str, Any]) -> None:
                partial = args.out.with_name(args.out.name + ".partial")
                partial.write_text(json.dumps(value, indent=2) + "\n")
                os.replace(partial, args.out)

            result = corpus(
                get,
                universe,
                args.target,
                args.as_of,
                lambda s: print(s, flush=True),
                save,
                prior,
                args.non_us,
            )
            save(result)
            print(
                f"Complete with releases: {result['complete_with_releases']} "
                f"(loan issuers {result['loan_issuers_complete_with_releases']}, "
                f"non-US {result['non_us_complete_with_releases']}); "
                f"with three presentations: {result['complete_with_three_presentations']}"
            )
        elif args.command == "packs":
            index = fetch_packs(get, json.loads(args.corpus.read_text()), args.out)
            print(f"{len(index)} packs in {args.out}")
        else:
            files = fetch_pack(get, minimum_pack(get, args.cik, args.as_of), args.out)
            print(f"Fetched {len(files)} documents into {args.out}")
    except (ValueError, OSError, urllib.error.URLError, ET.ParseError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
