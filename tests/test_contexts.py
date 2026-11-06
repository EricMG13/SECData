"""Run contexts for final-workflow. Dates are those of real corpus issuers; the EDGAR responses in
the last test are synthetic and say so."""

import json
from datetime import date

import pytest

from secdata.contexts import contexts, periods


@pytest.mark.parametrize(
    ("annual_end", "report", "filed", "expected"),
    [
        ("2025-12-31", "2026-09-30", "2026-10-28", ("q3-2026", "fy-2025")),  # Calendar year.
        ("2025-12-31", "2026-10-30", "2026-10-30", ("q3-2026", "fy-2025")),  # 6-K dated as filed.
        ("2026-03-31", "2026-09-27", "2026-11-04", ("q2-2027", "fy-2026")),  # ATS, 52 weeks.
        ("2026-01-31", "2026-08-01", "2026-08-27", ("q2-2027", "fy-2026")),  # Dycom.
        ("2026-06-30", "2026-09-30", "2026-10-29", ("q1-2027", "fy-2026")),  # Cimpress.
        ("2025-12-31", "2026-06-30", "2026-07-31", ("q2-2026", "fy-2025")),
    ],
)
def test_periods_name_the_fiscal_quarter_and_the_year_it_ends_in(
    annual_end, report, filed, expected
):
    assert (
        periods(
            date.fromisoformat(annual_end), date.fromisoformat(report), date.fromisoformat(filed)
        )
        == expected
    )


def test_contexts_fill_the_template_from_pack_and_edgar():
    """Synthetic EDGAR responses for two issuers; one has no ticker and reports in CAD under IFRS."""
    import urllib.error

    def doc(form, report, filed):
        return {"form": form, "report_date": report, "filing_date": filed}

    def entry(cik, entity, countries, usable=True):
        pack = {
            "complete_with_releases": usable,
            "annual": [doc("10-K", "2025-12-31", "2026-02-20")],
        }
        pack["quarterly"] = [doc("10-Q", "2026-09-30", "2026-10-29")]
        return {"cik": cik, "entity": entity, "countries": countries, "pack": pack}

    corpus = {"issuers": [
        entry("1", "Example Co, Inc. (EXA)", ["US"]),
        entry("2", "Maple Corp", ["CA", "XX"]),
        entry("3", "Partial Co", ["US"], usable=False),
    ]}  # fmt: skip
    responses = {
        "/submissions/CIK0000000001.json": {"tickers": ["EXA"], "sicDescription": "Airlines"},
        "/submissions/CIK0000000002.json": {"tickers": [], "sicDescription": "Refuse Systems"},
        "/us-gaap/Assets.json1": {"units": {"USD": [{"end": "2026-09-30"}]}},
        "/ifrs-full/Assets.json2": {"units": {"CAD": [{"end": "2025-12-31"}]}},
    }

    def get(url):
        cik = url.split("CIK")[1][:10].lstrip("0")
        for key, value in responses.items():
            if url.endswith(key) or (
                key[-1].isdigit() and url.endswith(key[:-1]) and key[-1] == cik
            ):
                return json.dumps(value).encode()
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    template = {"schema": "context/1", "run": {"as_of": "", "pathway": "credit_snapshot"}}
    template["identity"] = {"issuer_name": "", "issuer_id": "", "ticker": "", "country": ""}
    made = contexts(get, corpus, template, "2026-11-05")
    assert sorted(made) == ["1-example-co-inc-exa", "2-maple-corp"]
    a, b = made["1-example-co-inc-exa"], made["2-maple-corp"]
    assert a["identity"]["issuer_name"] == "Example Co, Inc."  # The ticker suffix is dropped.
    assert (
        a["identity"]["issuer_id"],
        a["identity"]["ticker"],
        a["run"]["reporting_currency"],
    ) == ("exa", "EXA", "USD")
    assert (
        b["identity"]["issuer_id"],
        b["identity"]["country"],
        b["run"]["reporting_currency"],
    ) == ("maple-corp", "Canada", "CAD")
    assert a["run"]["current_period"] == "q3-2026" and a["run"]["cutoff"] == "2026-11-05"
    assert template["run"]["as_of"] == ""  # The template is copied, not changed.
