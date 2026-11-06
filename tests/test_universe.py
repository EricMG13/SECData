"""Issuer universe from N-PORT holdings.

The BKLN filing is real (data/2026-11-05). Its expected counts and sums come from a separate regex
reading of the raw XML, not from the module's parser. The small filings below are synthetic: they
cover missing-LEI, default, restricted and missing-value cases in a controlled form.
"""

import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

from secdata.universe import main, universe

ROOT = Path(__file__).resolve().parents[1]
BKLN = ROOT / "data/2026-11-05/nport/BKLN-2026-08-31-NPORT.xml"
NOT_CORPORATE = rb"<issuerCat>(UST|USGA|USGSE|MUN|NUSS|PF|RF)</issuerCat>"


def test_real_loan_fund_counts_and_sums_match_an_independent_reading():
    raw = BKLN.read_bytes()
    blocks = re.findall(rb"<invstOrSec>(.*?)</invstOrSec>", raw, re.DOTALL)
    kept = [
        b
        for b in blocks
        if re.search(rb"<assetCat>(DBT|LON)</assetCat>", b)
        and re.search(rb"<issuerCat>|<issuerConditional", b)
        and not re.search(NOT_CORPORATE, b)
    ]
    loans = sum(b"<assetCat>LON</assetCat>" in b for b in kept)
    leis = Counter(
        m[1].decode() for b in kept if (m := re.search(rb"<lei>([A-Z0-9]{20})</lei>", b))
    )
    lei, holdings = leis.most_common(1)[0]
    value = sum(
        Decimal(re.search(rb"<valUSD>([^<]+)</valUSD>", b)[1].decode())
        for b in kept
        if f"<lei>{lei}</lei>".encode() in b
    )
    result = universe({BKLN.name: raw})
    (fund,) = result["funds"]
    assert fund["holdings"] == len(blocks)
    assert fund["kept"] == {"loan": loans, "bond": len(kept) - loans} and loans > 100
    assert sum(result["excluded_holdings"].values()) == len(blocks) - len(kept)
    assert sum(i["holdings"] for i in result["issuers"]) == len(kept)
    (entry,) = (i for i in result["issuers"] if i["key"] == lei)
    held = entry["funds"]["Invesco Senior Loan ETF"]
    assert held["holdings"] == holdings and Decimal(held["value_usd"]) == value


def nport(series: str, *holdings: str) -> bytes:
    return (
        '<edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><formData><genInfo>'
        f"<regName>Synthetic Trust</regName><regCik>0000000001</regCik>"
        f"<seriesName>{series}</seriesName><seriesId>S000000001</seriesId>"
        "<repPdDate>2026-06-30</repPdDate></genInfo><invstOrSecs>"
        + "".join(holdings)
        + "</invstOrSecs></formData></edgarSubmission>"
    ).encode()


def holding(name, lei, asset, value, *, cat="CORP", default="N", restricted="N"):
    value_tag = f"<valUSD>{value}</valUSD>" if value is not None else ""
    return (
        f"<invstOrSec><name>{name}</name><lei>{lei}</lei><cusip>123456AB7</cusip>"
        f"{value_tag}<assetCat>{asset}</assetCat><issuerCat>{cat}</issuerCat>"
        f"<invCountry>US</invCountry><isRestrictedSec>{restricted}</isRestrictedSec>"
        f"<debtSec><maturityDt>2030-01-15</maturityDt><isDefault>{default}</isDefault></debtSec>"
        "</invstOrSec>"
    )


def test_bonds_and_loans_join_by_lei_and_flags_are_kept():
    lei = "ABCDEFGHIJKLMNOPQRST"
    bonds = nport(
        "Synthetic High Yield ETF",
        holding("Casino Co", lei, "DBT", "100.50", restricted="Y"),
        holding("No Lei Corp", "N/A", "DBT", "5", default="Y"),
        holding("US Treasury", "N/A", "DBT", "999", cat="UST"),
    )
    loans = nport(
        "Synthetic Loan ETF",
        holding("CASINO CO TL B", lei, "LON", "20"),
        holding("No Lei Corp", "N/A", "LON", None),
    )
    result = universe({"hy.xml": bonds, "loan.xml": loans})
    by_key = {i["key"]: i for i in result["issuers"]}
    casino = by_key[lei]
    assert casino["bonds_and_loans"] and casino["restricted_holdings"] == 1
    assert casino["funds"]["Synthetic High Yield ETF"]["value_usd"] == "100.50"
    assert casino["names"] == ["CASINO CO TL B", "Casino Co"]
    no_lei = by_key["name:NO LEI CORP"]
    assert no_lei["holdings_in_default"] == 1 and no_lei["bonds_and_loans"]
    # A missing value is counted as missing and never shown as zero.
    assert no_lei["funds"]["Synthetic Loan ETF"] == {
        "holdings": 1,
        "value_usd": None,
        "values_missing": 1,
    }
    assert result["excluded_holdings"] == {"DBT / UST": 1}
    assert result["issuers"][0]["key"] in {lei, "name:NO LEI CORP"}  # held by both funds


def test_cli_writes_once_and_refuses_a_non_nport_file(tmp_path, capsys):
    out = tmp_path / "universe.json"
    assert main(["--nport", str(BKLN), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["schema"] == "issuer-universe/1"
    assert "issuers:" in capsys.readouterr().out
    assert main(["--nport", str(BKLN), "--out", str(out)]) == 2
    bad = tmp_path / "not-nport.xml"
    bad.write_text("<root/>")
    assert main(["--nport", str(bad), "--out", str(tmp_path / "other.json")]) == 2
    assert "genInfo" in capsys.readouterr().err
