"""Run contexts for final-workflow: one context/1 file per usable corpus issuer.

A final-workflow context file is the template; this fills its dated and issuer fields from the
issuer's pack and from EDGAR. Every value comes from an SEC record:

- the reporting currency is the unit of the filer's XBRL ``Assets`` concept (US GAAP or IFRS);
- the sector is EDGAR's SIC description and the ticker the first EDGAR ticker;
- the country is the funds' N-PORT country, written as a name;
- the periods come from the pack: the annual report's fiscal year-end, and the latest interim
  report snapped to that year's quarter grid. A fiscal year is named by the year it ends in, so
  ATS's quarter to September 2026 (year ending March 2027) is ``q2-2027``.
"""

import argparse
import copy
import json
import os
import re
import sys
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from secdata.edgar import DATA, UA_VARIABLE, Edgar, Get, pack_folder

SNAP = timedelta(days=7)  # 52-53 week years end a quarter up to a week before the month end.
LAG = timedelta(days=7)  # A 6-K's "report date" can be its filing date, after the quarter end.
COUNTRIES = {
    "US": "United States", "CA": "Canada", "GB": "United Kingdom", "BM": "Bermuda",
    "IE": "Ireland", "FR": "France", "DK": "Denmark", "LU": "Luxembourg", "CH": "Switzerland",
    "NL": "Netherlands", "KY": "Cayman Islands", "JE": "Jersey", "DE": "Germany", "MH": "Marshall Islands",
    "PA": "Panama", "LR": "Liberia", "AU": "Australia", "IL": "Israel", "SG": "Singapore",
    "XX": "",
}  # fmt: skip


def _months_after(day: date, months: int) -> date:
    """The month end ``months`` after ``day``'s month end."""
    year, month = divmod(day.month - 1 + months, 12)
    first_next = date(day.year + year + (month + 1) // 12, (month + 1) % 12 + 1, 1)
    return first_next - timedelta(days=1)


def periods(annual_end: date, interim_report: date, interim_filed: date) -> tuple[str, str]:
    """(current_period, prior_period) labels from the fiscal year-end and the latest interim."""
    reference = min(interim_report, interim_filed - LAG)
    grid = [_months_after(annual_end, 3 * k) for k in range(1, 8)]
    ends = [g for g in grid if g <= reference + SNAP]
    year_label = annual_end.year
    if not ends:
        return f"fy-{year_label}", f"fy-{year_label - 1}"
    k = len(ends)  # Quarters since the year-end; 4 would be the next year-end.
    quarter, years_on = (k - 1) % 4 + 1, (k - 1) // 4
    if quarter == 4:  # The latest interim is the next year's last quarter: label it that year.
        return f"fy-{year_label + years_on + 1}", f"fy-{year_label + years_on}"
    return f"q{quarter}-{year_label + years_on + 1}", f"fy-{year_label + years_on}"


def currency(get: Get, cik: str) -> str:
    """The unit of the filer's latest XBRL ``Assets`` fact, US GAAP first, then IFRS."""
    for taxonomy in ("us-gaap", "ifrs-full"):
        url = f"{DATA}/api/xbrl/companyconcept/CIK{int(cik):010d}/{taxonomy}/Assets.json"
        try:
            units = json.loads(get(url))["units"]
        except urllib.error.HTTPError as error:
            if error.code == 404:
                continue
            raise
        latest = max(units, key=lambda u: max(f["end"] for f in units[u]))
        return str(latest)
    raise ValueError(f"contexts: CIK {cik} has no XBRL Assets fact to read a currency from")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")


def contexts(
    get: Get, corpus: dict[str, Any], template: dict[str, Any], as_of: str
) -> dict[str, dict[str, Any]]:
    """One context per usable issuer, keyed by its pack folder name."""
    out: dict[str, dict[str, Any]] = {}
    taken: set[str] = set()
    for entry in corpus["issuers"]:
        pack = entry["pack"]
        if not pack["complete_with_releases"]:
            continue
        submissions = json.loads(get(f"{DATA}/submissions/CIK{int(entry['cik']):010d}.json"))
        tickers = [t for t in submissions.get("tickers", []) if t]
        name = re.sub(r"\s*\([^)]*\)\s*$", "", entry["entity"]).strip()
        issuer_id = slug(tickers[0]) if tickers else slug(name)
        if issuer_id in taken:
            issuer_id = f"{issuer_id}-{entry['cik']}"
        taken.add(issuer_id)
        annual, latest = pack["annual"][0], pack["quarterly"][0]
        current, prior = periods(
            date.fromisoformat(annual["report_date"]),
            date.fromisoformat(latest["report_date"] or latest["filing_date"]),
            date.fromisoformat(latest["filing_date"]),
        )
        codes = [c for c in entry["countries"] if c != "XX"]
        context = copy.deepcopy(template)
        context["run"].update(
            as_of=as_of,
            cutoff=as_of,
            current_period=current,
            prior_period=prior,
            reporting_currency=currency(get, entry["cik"]),
        )
        context["identity"].update(
            issuer_name=name,
            issuer_id=issuer_id,
            ticker=tickers[0] if tickers else "",
            sector=submissions.get("sicDescription", ""),
            country=COUNTRIES.get(codes[0], codes[0]) if codes else "",
            listed_equity=bool(tickers),
            parent_name="",
            borrower_name="",
            sponsor="",
            guarantors=[],
            aliases=[],
        )
        out[pack_folder(entry)] = context
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m secdata.contexts")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True, help="a final-workflow context/1")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--out", type=Path, required=True, help="new folder")
    args = parser.parse_args(argv)
    try:
        get = Edgar(os.environ.get(UA_VARIABLE, ""))
        made = contexts(
            get,
            json.loads(args.corpus.read_text()),
            json.loads(args.template.read_text()),
            args.as_of,
        )
        args.out.mkdir(parents=True)
        for folder, context in made.items():
            (args.out / f"{folder}.json").write_text(json.dumps(context, indent=2) + "\n")
        print(f"{len(made)} contexts in {args.out}")
    except (ValueError, OSError, urllib.error.URLError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
