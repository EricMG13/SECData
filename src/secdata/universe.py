"""Prospective issuer universe from fund holdings filed on SEC Form N-PORT.

Reads N-PORT XML filings, for example those of high-yield bond ETFs and loan ETFs, keeps corporate
bonds (`DBT`) and loans (`LON`), and groups them by issuer: the LEI when the filing gives one, else
the printed issuer name. Values stay exact decimal strings as filed; a missing value is counted as
missing, never as zero. Whether an issuer files 10-K reports with the SEC, and so has the free
filings the `minimum` module set needs, is a later step that needs EDGAR access; it is recorded
here as not run.
"""

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

NS = {"n": "http://www.sec.gov/edgar/nport"}
KINDS = {"DBT": "bond", "LON": "loan"}
# Government, municipal and fund issuers (N-PORT issuerCat codes) are not corporate credits.
# shortcut: LON and the government codes follow the N-PORT XML specification but no retained real
# filing holds them yet; an unexpected code lands in excluded_holdings with its value, never
# silently. Confirm them on the first real loan ETF filing.
NOT_CORPORATE = frozenset({"UST", "USGA", "USGSE", "MUN", "NUSS", "PF", "RF"})
LEI = re.compile(r"[A-Z0-9]{20}")


def _text(element: ET.Element, path: str) -> str:
    return (element.findtext(path, default="", namespaces=NS) or "").strip()


def fund_holdings(raw: bytes) -> tuple[dict[str, str], list[dict[str, str]]]:
    """The filing's fund identity and every holding, as printed."""
    root = ET.fromstring(raw)
    info = root.find(".//n:genInfo", NS)
    if info is None:
        raise ValueError("nport: no genInfo; not an N-PORT filing")
    fund = {k: _text(info, f"n:{k}") for k in ("regName", "regCik", "seriesName", "seriesId")}
    fund["holdings_date"] = _text(info, "n:repPdDate")
    fund["sha256"] = hashlib.sha256(raw).hexdigest()
    holdings = []
    for item in root.iterfind(".//n:invstOrSec", NS):
        conditional = item.find("n:issuerConditional", NS)
        category = _text(item, "n:issuerCat") or (
            f"{conditional.get('issuerCat', '')}: {conditional.get('desc', '')}"
            if conditional is not None
            else ""
        )
        isin = item.find("n:identifiers/n:isin", NS)
        holdings.append(
            {
                "name": _text(item, "n:name"),
                "lei": _text(item, "n:lei"),
                "cusip": _text(item, "n:cusip"),
                "isin": "" if isin is None else isin.get("value", ""),
                "asset": _text(item, "n:assetCat"),
                "issuer_category": category,
                "country": _text(item, "n:invCountry"),
                "value_usd": _text(item, "n:valUSD"),
                "restricted": _text(item, "n:isRestrictedSec"),
                "default": _text(item, "n:debtSec/n:isDefault"),
                "maturity": _text(item, "n:debtSec/n:maturityDt"),
            }
        )
    return fund, holdings


def universe(filings: dict[str, bytes]) -> dict[str, Any]:
    """Corporate bond and loan issuers across the filings, most widely held first."""
    funds: list[dict[str, Any]] = []
    issuers: dict[str, dict[str, Any]] = {}
    excluded: Counter[str] = Counter()
    for name, raw in filings.items():
        fund, holdings = fund_holdings(raw)
        kept: Counter[str] = Counter()
        for row in holdings:
            kind = KINDS.get(row["asset"])
            category = row["issuer_category"]
            if kind is None or not category or category.split(":")[0] in NOT_CORPORATE:
                excluded[f"{row['asset'] or 'no assetCat'} / {category or 'no issuerCat'}"] += 1
                continue
            kept[kind] += 1
            lei = row["lei"] if LEI.fullmatch(row["lei"]) else ""
            key = lei or "name:" + " ".join(row["name"].upper().split())
            entry = issuers.setdefault(
                key,
                {
                    "key": key,
                    "lei": lei,
                    "names": set(),
                    "cusip6": set(),
                    "countries": set(),
                    "issuer_categories": set(),
                    "kinds": set(),
                    "funds": {},
                    "holdings": 0,
                    "restricted_holdings": 0,
                    "holdings_in_default": 0,
                    "maturities": set(),
                },
            )
            entry["names"].add(row["name"])
            entry["cusip6"].update({row["cusip"][:6]} if len(row["cusip"]) == 9 else set())
            entry["countries"].add(row["country"])
            entry["issuer_categories"].add(category)
            entry["kinds"].add(kind)
            entry["holdings"] += 1
            entry["restricted_holdings"] += row["restricted"] == "Y"
            entry["holdings_in_default"] += row["default"] == "Y"
            entry["maturities"].update({row["maturity"]} if row["maturity"] else set())
            held = entry["funds"].setdefault(
                fund["seriesName"], {"holdings": 0, "value_usd": Decimal(0), "values_missing": 0}
            )
            held["holdings"] += 1
            if row["value_usd"]:
                held["value_usd"] += Decimal(row["value_usd"])
            else:
                held["values_missing"] += 1
        funds.append({**fund, "file": name, "holdings": len(holdings), "kept": dict(kept)})
    rows = []
    for entry in issuers.values():
        maturities = sorted(entry.pop("maturities"))
        rows.append(
            {
                **{k: sorted(v) if isinstance(v, set) else v for k, v in entry.items()},
                "bonds_and_loans": entry["kinds"] == {"bond", "loan"},
                "maturity_range": [maturities[0], maturities[-1]] if maturities else [],
                "funds": {
                    # Null when no holding of the issuer in that fund has a filed value.
                    series: {
                        **held,
                        "value_usd": str(held["value_usd"])
                        if held["holdings"] > held["values_missing"]
                        else None,
                    }
                    for series, held in entry["funds"].items()
                },
                "sec_registrant": None,
                "sec_check": "not run: needs EDGAR access to confirm 10-K filings",
            }
        )
    rows.sort(
        key=lambda r: (
            -len(r["funds"]),
            -sum(Decimal(f["value_usd"] or 0) for f in r["funds"].values()),
            r["key"],
        )
    )
    return {
        "schema": "issuer-universe/1",
        "funds": funds,
        "excluded_holdings": dict(sorted(excluded.items())),
        "issuers": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m secdata.universe",
        description="Build a prospective corporate bond and loan issuer list from N-PORT XML.",
    )
    parser.add_argument("--nport", type=Path, nargs="+", required=True, help="N-PORT XML files")
    parser.add_argument(
        "--out", type=Path, required=True, help="JSON file to write; must not exist"
    )
    args = parser.parse_args(argv)
    try:
        result = universe({p.name: p.read_bytes() for p in args.nport})
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    except (ValueError, OSError, ET.ParseError) as error:
        print(error, file=sys.stderr)
        return 2
    issuers = result["issuers"]
    print(
        f"Funds: {len(result['funds'])}; issuers: {len(issuers)}; "
        f"with bonds and loans: {sum(r['bonds_and_loans'] for r in issuers)}; "
        f"excluded holdings: {sum(result['excluded_holdings'].values())}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
