# SECData

A corpus of US public issuers with high-yield bonds or leveraged loans, and each issuer's minimum
filing pack from SEC EDGAR. The packs are the offline source folders for credit runs in
[final-workflow](https://github.com/EricMG13/final-workflow), where an agent answers each module
with `cpos_launch --config host --modules minimum`.

Everything here is public data from EDGAR. Nothing here is analysis: the corpus says which
issuers have the filings, not anything about their credit.

## Corpus of 2026-11-05

| Step | Result |
| --- | --- |
| Funds read | 8 ETFs: 3 high-yield bond funds and 5 loan funds (table below) |
| Issuers in their holdings | 1,505 corporate issuers; 642 with loans; 141 with both bonds and loans |
| Issuers checked against EDGAR | 808, loan issuers first, until 100 usable packs were found |
| Current 10-K filers found | 119 |
| Usable packs | 100: 46 loan issuers (22 with bonds and loans, 24 loans only) and 54 bond-only issuers |
| Packs with three decks on EDGAR | 4; the other 96 use earnings releases for some or all quarters |

All 642 loan issuers were checked before any bond-only issuer, so the 46 loan issuers are every
loan issuer in these funds with a usable pack. Of the 808 issuers checked, 513 had no EDGAR company
of the same name (mostly private borrowers), 168 matched a company with no 10-K in the last 400
days, and 19 file 10-Ks but lack a 10-Q or a quarterly results document; those 19 are recorded in
`corpus.json` but have no pack.

| Ticker | Fund | Holdings date | N-PORT accession | Bonds kept | Loans kept |
| --- | --- | --- | --- | --- | --- |
| HYG | iShares iBoxx $ High Yield Corporate Bond ETF | 2026-08-31 | 0001410368-26-108075 | 1,319 | 0 |
| USHY | iShares Broad USD High Yield Corporate Bond ETF | 2026-07-31 | 0001410368-26-099899 | 1,896 | 1 |
| JNK | State Street SPDR Bloomberg High Yield Bond ETF | 2026-06-30 | 0001410368-26-089139 | 1,228 | 1 |
| BKLN | Invesco Senior Loan ETF | 2026-08-31 | 0001378872-26-001974 | 50 | 122 |
| SRLN | State Street Blackstone Senior Loan ETF | 2026-06-30 | 0001410368-26-089164 | 320 | 388 |
| FLBL | Franklin Senior Loan ETF | 2026-06-30 | 0000940400-26-035132 | 34 | 239 |
| SEIX | Virtus Seix Senior Loan ETF | 2026-07-31 | 0000940400-26-038960 | 8 | 248 |
| FLRT | Pacer Aristotle Pacific Floating Rate High Income ETF | 2026-07-31 | 0000894189-26-028988 | 30 | 173 |

## The minimum pack

For each issuer, as of 2026-11-05:

- the latest 10-K, filed within 400 days;
- the three latest 10-Qs;
- for each of the three latest quarterly results, the deck the issuer filed as an 8-K exhibit
  (EX-99, described as a presentation, slides or deck, on an Item 2.02 or 7.01 8-K filed within
  ten days of the 10-Q or 10-K). Most issuers post decks only on their own websites, which are not
  on EDGAR. For such a quarter the pack holds that quarter's earnings release (EX-99.1) instead.

In `corpus.json`, `presentations` lists the decks and `releases_instead_of_presentations` the
releases. `complete` means three decks; `complete_with_releases` counts releases in their place.
Each pack folder has `_retrieval.json` with every document's URL, accession and sha256. The
final-workflow launcher ignores `_` names, so the record is not pinned as issuer evidence.

| Packs in `data/2026-11-05/packs` | Count |
| --- | --- |
| Packs | 100 (46 loan issuers) |
| Documents | 700: 100 10-Ks, 300 10-Qs, 13 decks, 287 releases |
| Packs with at least one deck / three decks | 5 / 4 |
| Decks flagged `image_only` | 0 |
| Documents whose sha256 differs from `_retrieval.json` | 0 |
| Size | 1.1 GB |

## Layout

```text
data/2026-11-05/
  nport/        N-PORT XML of each fund, as filed, and retrieval.json
  universe.json corporate bond and loan issuers, grouped by LEI or printed name
  corpus.json   every issuer checked, the 119 filers found, and each filer's pack selection
  packs/        one folder per usable issuer: <cik>-<name>/, and index.json
src/secdata/    universe.py (offline) and edgar.py (EDGAR access)
tests/          offline tests; fixtures are recorded EDGAR responses
```

## Commands

Python 3.11 or later; the code uses only the standard library. The EDGAR commands need
`SEC_USER_AGENT` set to a name and contact e-mail in the launching environment, as the SEC asks of
automated clients. Nothing writes that value to a file.

```bash
export SEC_USER_AGENT="Your name you@example.com"
D=data/2026-11-05
PYTHONPATH=src python3 -m secdata.edgar nport \
  --tickers HYG USHY JNK BKLN SRLN FLBL SEIX FLRT --out $D/nport
PYTHONPATH=src python3 -m secdata.universe --nport $D/nport/*.xml --out $D/universe.json
PYTHONPATH=src python3 -m secdata.edgar corpus --target 100 --as-of 2026-11-05 \
  --universe $D/universe.json --out $D/corpus.json
PYTHONPATH=src python3 -m secdata.edgar packs --corpus $D/corpus.json --out $D/packs
# One issuer only:
PYTHONPATH=src python3 -m secdata.edgar pack --cik 1590895 --as-of 2026-11-05 --out <new folder>
```

- Requests stay under 7 a second; the SEC allows 10. Run one EDGAR command at a time.
- `corpus` saves its file after every issuer, marked `in progress`; the same command resumes it.
- `packs` writes each pack to a `.partial` folder and renames it when complete, so a rerun keeps
  finished packs and redoes only an interrupted one.
- A deck with fewer than 2,000 visible characters is flagged `image_only`: its slides are images.

To run final-workflow on a pack, pass the pack folder as `--sources`:

```bash
PYTHONPATH=src .venv/bin/python -m deploy_workflow.owners.cpos_launch \
  --context path/to/context.json --sources ../SECData/data/2026-11-05/packs/<cik>-<name> \
  --config host --modules minimum --out runs/<run-folder>
```

## How issuers are matched

- **Universe.** Holdings with asset category `DBT` (bond) or `LON` (loan) are kept unless the
  issuer is a government, municipal or fund issuer. CLO tranches (`ABS-CBDO`), equities and cash
  are excluded and counted. Holdings group by LEI, or by printed name where the filing gives no
  LEI. Filed values stay exact decimal strings; a missing value is never shown as zero.
- **Names.** A printed name is compared with EDGAR's company names after dropping co-issuers
  (after `/`), punctuation, legal suffixes and loan maturity dates. The high-yield bond funds cut
  names at exactly 24 characters (291 of HYG's 1,324 holdings; the loan funds print full names),
  so only a 24-character name may match an EDGAR name it begins. 96 of the 100 usable issuers
  match on equal names and 4 on a cut name.
- **Filer.** A matched company counts only if it filed a 10-K within 400 days of the as-of date.
  This removes former and private companies with old EDGAR records, such as earlier Caesars,
  Nielsen and McAfee registrations.

## Checks

- `python -m pytest`: 20 tests, offline. The fixtures are real EDGAR responses recorded on
  2026-11-05 (HYG's N-PORT feed, the name search, and the Caesars and American Airlines filing
  lists and 8-K indexes). The universe test reads the real BKLN filing; its expected counts and
  sums come from a separate regex reading of the XML. Synthetic inputs are used only for the
  image-only deck, missing-value and resume cases, and say so.
- Matches were checked by eye for the 4 cut-name matches and a random 18 of the 96 equal-name
  matches; all name the same company or its reporting parent (for example Alkermes Inc to
  Alkermes plc).
- Two packs, American Airlines (three decks) and Caesars (three releases), were prepared with
  the final-workflow launcher in host mode: all 7 documents were pinned and converted to text,
  `_retrieval.json` was ignored, and the first module request was issued.

## Limits

- Matching uses names, not LEIs; EDGAR does not publish LEIs. A borrower that is a subsidiary of a
  public company, or whose name EDGAR spells differently, is missed. A wrong same-name match is
  possible; `match_basis` records how each one was made.
- The funds' holdings dates differ (2026-06-30 to 2026-08-31), and N-PORT holdings are public only
  after a delay.
- Earnings releases are not presentations. For 96 issuers the pack has releases for some or all
  quarters; `complete` stays false for them.
- Packs are retrieved documents, not checked analysis. A failed or partial pack is recorded, not
  repaired.
