"""EDGAR access for the issuer corpus.

The fixtures are real EDGAR responses recorded on 2026-11-05 (HYG's N-PORT feed, EDGAR's name
search, the Caesars and American Airlines filing lists and 8-K exhibit indexes, and GFL
Environmental's filing list, 6-K indexes and the first 8 KB of each 6-K exhibit). The universe
rows in the corpus tests and the documents in the image-only and resume cases are synthetic, and
say so. No test calls the network.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from secdata.edgar import (
    WWW,
    Edgar,
    entity_candidates,
    exhibits,
    fetch_pack,
    latest_nport,
    minimum_pack,
    name_key,
)

F = Path(__file__).resolve().parent / "fixtures/edgar"
CZR = "1590895"


GFL = "1780232"
GFL_URLS = json.loads((F / "gfl-urls.json").read_text())


class Recorded:
    """Recorded responses; `head` is a document's first 8 KB, as `Edgar.head` reads it."""

    def __call__(self, url: str) -> bytes:
        if url in GFL_URLS and "full" in GFL_URLS[url]:
            return (F / GFL_URLS[url]["full"]).read_bytes()
        return recorded_url(url)

    def head(self, url: str) -> bytes:
        if url in GFL_URLS and "head" in GFL_URLS[url]:
            return (F / GFL_URLS[url]["head"]).read_bytes()
        raise AssertionError(f"no recorded head for {url}")


def recorded_url(url: str) -> bytes:
    if "browse-edgar" in url and "S000016772" in url:
        return (F / "hyg-nport-feed.xml").read_bytes()
    if "keysTyped=caesars%20entertainment" in url:
        return (F / "efts-caesars-entertainment.json").read_bytes()
    if url.endswith(f"CIK{int(CZR):010d}.json"):
        return (F / "czr-submissions.json").read_bytes()
    if f"/data/{CZR}/" in url and url.endswith("-index.htm"):
        accession = url.rsplit("/", 1)[1].removesuffix("-index.htm")
        return (F / f"czr-{accession}-index.htm").read_bytes()
    aal = json.loads((F / "aal-urls.json").read_text())
    if url in aal:
        return (F / aal[url]).read_bytes()
    raise AssertionError(f"no recorded response for {url}")


recorded = Recorded()


def test_latest_nport_reads_the_series_feed():
    filing = latest_nport(recorded, "S000016772")
    assert filing["accession"] == "0001410368-26-108075"
    assert filing["filing_date"] == "2026-10-23"
    assert filing["url"].endswith("/data/1100663/000141036826108075/primary_doc.xml")


@pytest.mark.parametrize(
    ("printed", "key"),
    [
        ("TRANSDIGM GR 08/ 08/19/32", "TRANSDIGM GR"),
        ("CAESAR 01/23/30", "CAESAR"),
        ("AES CORP/THE", "AES"),
        ("ALBERTSONS COS/SAFEWAY", "ALBERTSONS COMPANIES"),
        ("Caesars Entertainment, Inc. (CZR)", "CAESARS ENTERTAINMENT"),
        ("SS&C TECHNOLOGIES INC", "SS AND C TECHNOLOGIES"),
    ],
)
def test_name_key_drops_co_issuers_suffixes_tickers_and_loan_dates(printed, key):
    assert name_key(printed) == key


def test_name_search_keeps_only_entities_with_the_same_key():
    found = entity_candidates(recorded, "CAESARS ENTERTAINMENT INC")
    assert [m["cik"] for m in found] == [CZR, "1070794"]
    assert {m["basis"] for m in found} == {"name keys equal"}


def test_pack_takes_the_filed_decks_when_they_exist():
    pack = minimum_pack(recorded, "4515", date(2026, 11, 5))
    assert [(d["form"], d["filing_date"]) for d in pack["annual"] + pack["quarterly"]] == [
        ("10-K", "2026-02-18"),
        ("10-Q", "2026-10-22"),
        ("10-Q", "2026-07-23"),
        ("10-Q", "2026-04-23"),
    ]
    assert [(d["form"], d["period"]) for d in pack["presentations"]] == [
        ("EX-99.2", "2026-09-30"),
        ("EX-99.2", "2026-06-30"),
        ("EX-99.2", "2026-03-31"),
    ]
    assert pack["complete"] and pack["complete_with_releases"] and not pack["gaps"]


def test_pack_keeps_each_quarters_release_when_its_deck_is_not_on_edgar():
    pack = minimum_pack(recorded, CZR, date(2026, 11, 5))
    assert pack["presentations"] == []
    assert [(d["form"], d["period"]) for d in pack["releases_instead_of_presentations"]] == [
        ("EX-99.1", "2026-09-30"),
        ("EX-99.1", "2026-06-30"),
        ("EX-99.1", "2026-03-31"),
    ]
    assert not pack["complete"] and pack["complete_with_releases"]
    assert pack["gaps"] == ["3 of 3 quarters have a release, not a presentation, on EDGAR"]
    # The XBRL presentation linkbase is listed in the index but is not an EX-99 deck.
    rows = exhibits(recorded, CZR, "0001590895-26-000032")
    assert any("PRESENTATION" in r["description"] and r["type"] == "EX-101.PRE" for r in rows)


def test_pack_uses_only_filings_up_to_the_as_of_date():
    pack = minimum_pack(recorded, CZR, date(2026, 8, 1))
    assert pack["quarterly"][0]["filing_date"] == "2026-07-28"
    assert [d["period"] for d in pack["releases_instead_of_presentations"]] == [
        "2026-06-30",
        "2026-03-31",
        "2025-12-31",
    ]


def test_foreign_private_issuer_pack_reads_6k_interim_reports_and_releases():
    """GFL files a 40-F and furnishes each quarter on 6-K with generic EX-99 labels."""
    pack = minimum_pack(recorded, GFL, date(2026, 11, 5))
    assert pack["filer"] == "foreign private issuer" and not pack["files_10k"]
    assert [(d["form"], d["filing_date"]) for d in pack["annual"]] == [("40-F", "2026-02-18")]
    assert [d["filing_date"] for d in pack["quarterly"]] == [
        "2026-10-30",
        "2026-07-31",
        "2026-05-01",
    ]
    assert {d["form"] for d in pack["quarterly"]} == {"6-K-EX-99.1"}
    assert [d["filing_date"] for d in pack["releases_instead_of_presentations"]] == [
        "2026-10-28",
        "2026-07-29",
        "2026-04-29",
    ]
    assert pack["files_20f_or_40f"] and pack["complete_with_releases"] and not pack["complete"]
    assert pack["gaps"][1:] == ["3 of 3 quarters have a release, not a presentation, on EDGAR"]


def synthetic_foreign_filer(sixk):
    """Synthetic EDGAR responses for CIK 1: a 20-F, then one 6-K per (date, EX-99.1 text)."""
    rows = [(d, "6-K", t) for d, t in sorted(sixk, reverse=True)] + [("2026-02-17", "20-F", "")]
    accessions = [f"0000000001-26-{i:06d}" for i in range(len(rows))]
    recent = {
        "form": [r[1] for r in rows],
        "filingDate": [r[0] for r in rows],
        "reportDate": [r[0] for r in rows],
        "accessionNumber": accessions,
        "primaryDocument": ["main.htm"] * len(rows),
    }
    pages = {
        f"https://data.sec.gov/submissions/CIK{1:010d}.json": json.dumps(
            {"filings": {"recent": recent}}
        ).encode()
    }
    for accession, (_, _, text) in zip(accessions, rows, strict=True):
        folder = f"/Archives/edgar/data/1/{accession.replace('-', '')}"
        row = f'<tr><td>1</td><td>EX-99.1</td><td><a href="{folder}/ex.htm">ex.htm</a></td>'
        pages[f"{WWW}{folder}/{accession}-index.htm"] = (
            f"<table>{row}<td>EX-99.1</td></tr>".encode()
        )
        pages[f"{WWW}{folder}/ex.htm"] = f"<p>{text}</p>".encode()
        pages[f"{WWW}{folder}/main.htm"] = b"<p>Form</p>"
    return pages.__getitem__


RESULTS_IN_REPORT = "Example Announces Financial Results for the {}; Interim Report for the {}"


def test_foreign_interim_report_that_announces_results_is_also_the_release(tmp_path):
    """Synthetic filings shaped like Genmab's: each quarter's results are announced in its interim
    report, and an offering 6-K's pro forma cites interim statements but is not a results report."""
    pro_forma = "UNAUDITED PRO FORMA CONDENSED COMBINED FINANCIAL INFORMATION, from the interim "
    get = synthetic_foreign_filer(
        [
            ("2026-11-05", RESULTS_IN_REPORT.format("Nine Months of 2026", "Nine Months")),
            ("2026-08-06", RESULTS_IN_REPORT.format("First Half of 2026", "Six Months")),
            ("2026-05-12", pro_forma + "condensed consolidated financial statements"),
            ("2026-05-07", RESULTS_IN_REPORT.format("First Quarter of 2026", "Three Months")),
        ]
    )
    pack = minimum_pack(get, "1", date(2026, 11, 5))
    expected = ["2026-11-05", "2026-08-06", "2026-05-07"]
    assert [d["filing_date"] for d in pack["quarterly"]] == expected
    assert pack["releases_instead_of_presentations"] == pack["quarterly"]
    assert pack["complete_with_releases"]
    calls = []
    files = fetch_pack(lambda url: calls.append(url) or get(url), pack, tmp_path / "p")
    assert len(files) == 7 and len(calls) == 4  # Each combined document is fetched once.
    assert files[4]["file"] == files[1]["file"] and files[4]["sha256"] == files[1]["sha256"]


def test_blank_user_agent_is_refused():
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        Edgar(" ")


def test_fetch_flags_an_image_only_deck(tmp_path):
    """Synthetic documents: a deck page with slide images and no text."""
    deck = {
        "form": "EX-99.2",
        "filing_date": "2026-10-22",
        "report_date": "2026-10-22",
        "accession": "0000000000-26-000001",
        "url": "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/deck.htm",
        "period": "2026-09-30",
    }
    pack = {"annual": [], "quarterly": [], "presentations": [deck]}
    pack["releases_instead_of_presentations"] = []
    files = fetch_pack(lambda url: b"<html><img src='slide1.jpg'></html>", pack, tmp_path / "p")
    assert files[0]["image_only"] and files[0]["visible_text_chars"] == 0
    record = json.loads((tmp_path / "p/_retrieval.json").read_text())
    assert record["files"][0]["sha256"] == files[0]["sha256"]


def issuer(key, name, kind, value, country="US"):
    fund = {"Fund": {"holdings": 1, "value_usd": value, "values_missing": 0}}
    return {"key": key, "names": [name], "kinds": [kind], "funds": fund, "countries": [country]}


def test_corpus_checks_loan_issuers_first_stops_at_the_target_and_merges_one_filer():
    """Synthetic universe rows over the recorded EDGAR responses."""
    from secdata.edgar import corpus

    universe = {
        "funds": [{"seriesName": "Fund"}],
        "issuers": [
            issuer("A", "AMERICAN AIRLINES INC", "bond", "900"),
            issuer("C1", "CAESARS ENTERTAINMENT INC", "loan", "10"),
            issuer("C2", "Caesars Entertainment, Inc.", "loan", "5"),
        ],
    }
    one = corpus(recorded, universe, 1, date(2026, 11, 5), lambda line: None)
    assert [c["key"] for c in one["checked"]] == ["C1"]  # Loans first; stop once 1 is usable.
    assert one["issuers"][0]["cik"] == CZR and one["complete_with_releases"] == 1
    assert one["complete_with_three_presentations"] == 0
    both = corpus(recorded, universe, 5, date(2026, 11, 5), lambda line: None)
    assert [c["key"] for c in both["checked"]] == ["C1", "C2", "A"]
    assert both["checked"][1]["result"].startswith("same SEC filer")
    caesars = next(c for c in both["issuers"] if c["cik"] == CZR)
    assert caesars["issuer_keys"] == ["C1", "C2"]
    assert both["complete_with_three_presentations"] == 1  # American Airlines' filed decks.
    assert both["issuers"][0]["cik"] == "4515"


def test_corpus_resumes_from_a_saved_partial_result_without_rechecking():
    from secdata.edgar import corpus

    universe = {
        "funds": [{"seriesName": "Fund"}],
        "issuers": [
            issuer("A", "AMERICAN AIRLINES INC", "bond", "900"),
            issuer("C1", "CAESARS ENTERTAINMENT INC", "loan", "10"),
        ],
    }
    saved = []
    first = corpus(recorded, universe, 1, date(2026, 11, 5), lambda line: None, saved.append)
    assert saved[-1]["status"] == "in progress" and first["status"] == "done"
    asked = []

    def counting(url):
        asked.append(url)
        return recorded(url)

    resumed = corpus(counting, universe, 2, date(2026, 11, 5), lambda line: None, prior=saved[-1])
    assert [c["key"] for c in resumed["checked"]] == ["C1", "A"]
    assert not any("caesars" in u or f"CIK{int(CZR):010d}" in u for u in asked)
    assert resumed["complete_with_releases"] == 2


def test_non_us_pass_extends_a_finished_corpus_and_counts_only_non_us_packs():
    """Synthetic universe rows over the recorded EDGAR responses. GFL was checked by the first
    pass under the 10-K rule; the non-US pass checks it again and skips US issuers."""
    from secdata.edgar import corpus

    universe = {
        "funds": [{"seriesName": "Fund"}],
        "issuers": [
            issuer("A", "AMERICAN AIRLINES INC", "bond", "900"),
            issuer("C1", "CAESARS ENTERTAINMENT INC", "loan", "10", country="GB"),
            issuer("G", "GFL ENVIRONMENTAL INC", "bond", "50", country="CA"),
        ],
    }
    base = corpus(recorded, universe, 1, date(2026, 11, 5), lambda line: None)
    base["checked"].append({"key": "G", "names": ["GFL ENVIRONMENTAL INC"], "result": "earlier"})
    extended = corpus(recorded, universe, 2, date(2026, 11, 5), lambda line: None, None, base, True)
    assert [(c["key"], c.get("pass")) for c in extended["checked"]] == [
        ("C1", None),
        ("G", None),
        ("G", "non-US"),
    ]
    assert extended["non_us_complete_with_releases"] == 2 and extended["non_us_target"] == 2
    assert extended["target_complete"] == 1  # The first pass's target, unchanged.
    gfl = next(c for c in extended["issuers"] if c["cik"] == GFL)
    assert gfl["countries"] == ["CA"] and gfl["pack"]["filer"] == "foreign private issuer"


def test_visible_text_ignores_scripts_styles_and_tags():
    from secdata.edgar import visible_text_chars

    page = b"<html><style>p{}</style><script>x()</script><p>Net  revenues</p><img src=a></html>"
    assert visible_text_chars(page) == len("Net revenues")


def test_packs_redo_an_interrupted_download_and_keep_finished_ones(tmp_path):
    """Synthetic corpus and documents; checks the resume behaviour, not EDGAR."""
    from secdata.edgar import fetch_packs

    doc = {"form": "10-K", "filing_date": "2026-02-17", "report_date": "2025-12-31"}
    pack = {"annual": [{**doc, "accession": "a", "url": "https://x/10k.htm"}], "quarterly": []}
    pack.update(presentations=[], releases_instead_of_presentations=[])
    pack.update(complete=False, complete_with_releases=True)
    result = {
        "issuers": [
            {"cik": "1", "entity": "Example Co, Inc.", "kinds": ["loan"], "pack": pack},
            {
                "cik": "2",
                "entity": "Partial Co",
                "kinds": ["bond"],
                "pack": {**pack, "complete_with_releases": False},
            },
        ]
    }
    (tmp_path / "1-example-co-inc.partial").mkdir(parents=True)
    calls = []
    index = fetch_packs(lambda url: calls.append(url) or b"<p>annual</p>", result, tmp_path)
    assert [i["folder"] for i in index] == ["1-example-co-inc"] and calls == ["https://x/10k.htm"]
    assert not (tmp_path / "1-example-co-inc.partial").exists()
    again = fetch_packs(lambda url: pytest.fail("finished pack refetched"), result, tmp_path)
    assert again == index
    assert json.loads((tmp_path / "index.json").read_text()) == index
