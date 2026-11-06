# SECData

A corpus of public issuers with high-yield bonds or leveraged loans, US and non-US, and each
issuer's minimum filing pack from SEC EDGAR. The packs are the offline source folders for credit
runs in [final-workflow](https://github.com/EricMG13/final-workflow), where an agent answers each
module with `cpos_launch --config host --modules minimum`.

Everything here is public data from EDGAR. Nothing here is analysis: the corpus says which
issuers have the filings, not anything about their credit.

## Corpus of 2026-11-05

| Step | Result |
| --- | --- |
| Funds read | 8 ETFs: 3 high-yield bond funds and 5 loan funds (table below) |
| Issuers in their holdings | 1,505 corporate issuers; 642 with loans; 141 with both bonds and loans |
| First pass | 808 issuers checked, loan issuers first, until 100 usable packs; 119 current 10-K filers |
| Non-US pass | all 207 non-US issuers (39 with loans), checked again with 20-F and 40-F filers accepted |
| Usable packs | 118: 46 loan issuers and 20 non-US issuers (13 foreign private issuers) |
| Packs with three decks on EDGAR | 6; the others use earnings releases for some or all quarters |

**First pass.** All 642 loan issuers were checked before any bond-only issuer, so the 46 loan
issuers are every loan issuer in these funds with a usable pack. Of the 808 issuers checked, 513
had no EDGAR company of the same name (mostly private borrowers), 168 matched a company with no
10-K in the last 400 days, and 19 file 10-Ks but lack a 10-Q or a quarterly results document;
those 19 are recorded in `corpus.json` but have no pack. This pass ran at commit `adecf8f`, which
read 10-K filers only; its result is kept as `corpus-first-pass.json`.

**Non-US pass.** An issuer is non-US when a fund reports a non-US country for it (N-PORT
`invCountry`) and no fund reports the US. Funds report `XX` for a bond whose co-issuers are in
several countries, so `XX` alone counts as unknown. The country is the funds' entry, so some
non-US issuers are run from the US, such as Carnival and Weatherford. This pass checked every
non-US issuer, including the 63 the first pass checked under the 10-K rule alone, and never
reached its cap of 30: 20 non-US issuers have usable packs. Of the 204 it checked (3 were
already in the corpus), 141 had no EDGAR company of the same name, 36 matched no filer of a
current 10-K, 20-F or 40-F, 18 gave usable packs, 8 gave partial packs, and 1 was the same filer
as another. None of the 39 non-US loan issuers has a usable pack.

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

Non-US issuers with usable packs (country as the funds report it):

| Issuer | Country | Annual report | Interim reports | Results documents |
| --- | --- | --- | --- | --- |
| Brightstar Lottery PLC | GB | 20-F 2026-02-24 | 6-K 2026-08-04, 2026-05-12, 2025-11-04 | 3 decks |
| UBS Group AG | CH | 20-F 2026-03-09 | 6-K 2026-10-28, 2026-07-29, 2026-04-29 | 3 decks |
| NCL Corp Ltd. | BM | 10-K 2026-03-02 | 10-Q 2026-10-29, 2026-08-03, 2026-05-04 | 3 releases |
| Bausch Health Companies Inc. | CA | 10-K 2026-02-19 | 10-Q 2026-10-29, 2026-07-30, 2026-04-30 | 3 releases |
| GFL Environmental Inc. | CA | 40-F 2026-02-18 | 6-K 2026-10-30, 2026-07-31, 2026-05-01 | 3 releases |
| TELUS Corp | CA | 40-F 2026-02-12 | 6-K 2026-07-31, 2026-05-08, 2025-11-07 | 3 releases |
| Genmab A/S | DK | 20-F 2026-02-17 | 6-K 2026-11-05, 2026-05-07, 2025-11-06 | 3 releases, in the interim reports |
| Weatherford International plc | BM | 10-K 2026-02-04 | 10-Q 2026-10-21, 2026-07-22, 2026-04-22 | 3 releases |
| Valaris Ltd | BM | 10-K 2026-02-20 | 10-Q 2026-11-03, 2026-08-06, 2026-05-05 | 3 releases |
| Constellium SE | FR | 10-K 2026-02-25 | 10-Q 2026-10-28, 2026-07-29, 2026-04-29 | 3 releases |
| Cimpress plc | IE | 10-K 2026-08-07 | 10-Q 2026-10-29, 2026-05-01, 2026-01-29 | 3 releases, image only |
| Carnival Corp Ltd. | BM | 10-K 2026-01-27 | 10-Q 2026-09-29, 2026-06-26, 2026-03-27 | 3 releases |
| Skeena Resources Ltd | CA | 40-F 2026-03-24 | 6-K 2026-08-13, 2026-05-15, 2025-11-13 | 3 releases |
| Millicom International Cellular SA | LU | 20-F 2026-03-24 | 6-K 2026-11-05, 2026-08-06, 2026-05-14 | 3 releases, in the 6-K documents |
| TransAlta Corp | CA | 40-F 2026-02-27 | 6-K 2026-11-03, 2026-07-31, 2026-05-06 | 3 releases |
| Hudbay Minerals Inc. | CA | 40-F 2026-03-27 | 6-K 2026-07-29, 2026-05-01, 2025-11-13 | 3 releases |
| Eldorado Gold Corp | CA | 40-F 2026-03-27 | 6-K 2026-10-28, 2026-07-30, 2026-04-30 | 3 releases |
| Precision Drilling Corp | CA | 40-F 2026-03-09 | 6-K 2026-10-28, 2026-07-29, 2026-05-01 | 3 releases |
| ATS Corp | CA | 40-F 2026-05-28 | 6-K 2026-11-04, 2026-08-06, 2026-02-04 | 3 releases |
| Baytex Energy Corp. | CA | 40-F 2026-03-05 | 6-K 2026-07-31, 2026-05-08, 2025-10-31 | 3 releases |

Eight foreign issuers file but have partial packs: Barclays and Grifols (one interim report on
EDGAR), Methanex and Vermilion (reports inside their releases, below; none counted), Pelagos
(decks, no interim report), Danaos (two interim reports, no releases), IAMGOLD (no Q3
release by the as-of date) and Trekor (two quarters with only a notice of the results date).

## The minimum pack

For each issuer, as of 2026-11-05:

- the latest 10-K, filed within 400 days;
- the three latest 10-Qs;
- for each of the three latest quarterly results, the deck the issuer filed as an 8-K exhibit
  (EX-99, described as a presentation, slides or deck, on an Item 2.02 or 7.01 8-K filed within
  ten days of the 10-Q or 10-K). Most issuers post decks only on their own websites, which are not
  on EDGAR. For such a quarter the pack holds that quarter's earnings release (EX-99.1) instead.

A foreign private issuer files a 20-F or 40-F instead of a 10-K and furnishes its quarters on
6-K. Its pack has:

- the latest 20-F or 40-F, filed within 400 days;
- the three latest interim reports on 6-K (interim financial statements, an interim MD&A, or a
  quarterly or half-year report), standing in for 10-Qs;
- for each of the three latest results events on 6-K, the deck, else the results release.

6-K exhibits carry generic labels such as EX-99.1, so each document is classified from its text:

- An EX-99 exhibit is read from its first 8 KB. It is an interim report only if its first 400
  characters say so, not if they describe a full year alone, and not if a results headline is
  followed by a mention of "the interim financial statements". It is a release if its first
  1,500 characters report a quarter's or half-year's results.
- A 6-K with no EX-99 exhibit holds its report in the 6-K document itself, which is read from its
  first 32 KB, after the cover page. It can be the interim report, release and deck at once.
- An interim report that announces its results (Genmab, Millicom) is also that quarter's release
  and is stored once. Officers' certifications and offering pro formas are not results.
- 6-Ks filed within ten days are one results event; a new event starts at least 45 days earlier.

In `corpus.json`, `presentations` lists the decks and `releases_instead_of_presentations` the
releases. `complete` means three decks; `complete_with_releases` counts releases in their place.
A foreign issuer's pack has `filer: "foreign private issuer"` and `files_20f_or_40f`. Each pack
folder has `_retrieval.json` with every document's URL, accession and sha256. The final-workflow
launcher ignores `_` names, so the record is not pinned as issuer evidence.

| Packs in `data/2026-11-05/packs` | Count |
| --- | --- |
| Packs | 118: 46 loan issuers, 20 non-US issuers, 13 foreign private issuers |
| Annual reports | 105 10-Ks, 9 40-Fs, 4 20-Fs |
| Interim reports | 315 10-Qs, 39 on 6-K |
| Results documents | 19 decks, 335 releases |
| Document entries / files | 826 / 820: 6 interim reports are also their quarter's release |
| Packs with at least one deck / three decks | 7 / 6 |
| Documents flagged `image_only` | 3, Cimpress's releases (71 characters of text each) |
| Files whose sha256 differs from `_retrieval.json` | 0 |
| Size | 1.3 GB |

## Layout

```text
data/2026-11-05/
  nport/                 N-PORT XML of each fund, as filed, and retrieval.json
  universe.json          corporate bond and loan issuers, grouped by LEI or printed name
  corpus-first-pass.json the first pass: 808 issuers checked, 119 10-K filers
  corpus.json            both passes: every issuer checked, the filers found and their packs
  packs/                 one folder per usable issuer: <cik>-<name>/, and index.json
  contexts/              one final-workflow context/1 file per pack folder
src/secdata/             universe.py (offline), edgar.py and contexts.py (EDGAR access)
tests/                   offline tests; fixtures are recorded EDGAR responses
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
  --universe $D/universe.json --out $D/corpus-first-pass.json
PYTHONPATH=src python3 -m secdata.edgar corpus --non-us --target 30 --as-of 2026-11-05 \
  --universe $D/universe.json --base $D/corpus-first-pass.json --out $D/corpus.json
PYTHONPATH=src python3 -m secdata.edgar packs --corpus $D/corpus.json --out $D/packs
# One issuer only:
PYTHONPATH=src python3 -m secdata.edgar pack --cik 1590895 --as-of 2026-11-05 --out <new folder>
```

- Requests stay under 7 a second; the SEC allows 10. Run one EDGAR command at a time.
- `corpus` saves its file after every issuer, marked `in progress`; the same command resumes it.
- `--non-us` extends a finished corpus given as `--base`; its `--target` counts non-US packs only.
- `packs` writes each pack to a `.partial` folder and renames it when complete, so a rerun keeps
  finished packs and redoes only an interrupted one.
- A deck with fewer than 2,000 visible characters is flagged `image_only`: its slides are images.
- The first command line reproduces the first pass only at commit `adecf8f`; the current code
  would also accept 20-F and 40-F filers in it.

To run final-workflow on a pack, pass the pack folder as `--sources`:

```bash
PYTHONPATH=src .venv/bin/python -m deploy_workflow.owners.cpos_launch \
  --context path/to/context.json --sources ../SECData/data/2026-11-05/packs/<cik>-<name> \
  --config host --modules minimum --out runs/<run-folder>
```

## Run contexts

`data/2026-11-05/contexts/<pack folder>.json` holds one final-workflow `context/1` file per usable
issuer, made by `secdata.contexts` from a final-workflow context used as the template:

```bash
PYTHONPATH=src python3 -m secdata.contexts --corpus $D/corpus.json --as-of 2026-11-05 \
  --template ../final-workflow/runs/cpos-launch-host-czr-001/context.json --out $D/contexts
```

- **Reporting currency:** the unit of the filer's XBRL `Assets` concept, US GAAP or IFRS (111 USD,
  7 CAD). final-workflow refuses a run whose CP-1 reports another currency.
- **Sector and ticker:** EDGAR's SIC description and first ticker. Five issuers have no ticker,
  and FS KKR has no SIC sector.
- **Country:** the funds' N-PORT country, written as a name.
- **Periods:** the latest interim report, snapped to the fiscal quarter grid of the annual
  report's year-end. A fiscal year is named by the year it ends in; for example ATS's quarter to
  September 2026 is `q2-2027`. CHS filed its FY2026 10-K after its last 10-Q, so it is `fy-2026`.

All 118 pass final-workflow's `cpos_launch` preparation with `--config host --modules minimum`:
each context validates and every pack document is pinned and converted.

## How issuers are matched

- **Universe.** Holdings with asset category `DBT` (bond) or `LON` (loan) are kept unless the
  issuer is a government, municipal or fund issuer. CLO tranches (`ABS-CBDO`), equities and cash
  are excluded and counted. Holdings group by LEI, or by printed name where the filing gives no
  LEI. Filed values stay exact decimal strings; a missing value is never shown as zero.
- **Names.** A printed name is compared with EDGAR's company names after dropping co-issuers
  (after `/`), punctuation, legal suffixes and loan maturity dates. The high-yield bond funds cut
  names at exactly 24 characters (291 of HYG's 1,324 holdings; the loan funds print full names),
  so only a 24-character name may match an EDGAR name it begins. Of the 118 usable issuers, 112 match on equal names and 6 on a cut name.
- **Filer.** A matched company counts only if it filed a 10-K, 20-F or 40-F within 400 days of
  the as-of date. This removes former and private companies with old EDGAR records, such as
  earlier Caesars, Nielsen and McAfee registrations.

## Checks

- `python -m pytest`: 42 tests, offline. The fixtures are real EDGAR responses recorded on
  2026-11-05: HYG's N-PORT feed, the name search, the Caesars and American Airlines filing lists
  and 8-K indexes, and GFL Environmental's filing list, 6-K indexes, exhibit heads and 6-K
  documents. The universe test reads the real BKLN filing; its expected counts and sums come from
  a separate regex reading of the XML. Synthetic inputs, which say so, cover the image-only deck,
  missing values, resume, the non-US pass, and 6-K texts modelled on Genmab, Millicom, UBS,
  Methanex, Skeena and Hudbay filings.
- Matches were checked by eye for the 4 cut-name matches and a random 18 of the 96 equal-name
  matches of the first pass, and for all 20 non-US matches; all name the same company or
  its reporting parent (for example Alkermes Inc to Alkermes plc).
- The foreign rules were checked against the filings of all 21 foreign issuers. Each
  usable foreign pack's interim reports were read by title; see the non-US table above.
- Two packs, American Airlines (three decks) and Caesars (three releases), were prepared with
  the final-workflow launcher in host mode: all 7 documents were pinned and converted to text,
  `_retrieval.json` was ignored, and the first module request was issued.

## Limits

- Matching uses names, not LEIs; EDGAR does not publish LEIs. A borrower that is a subsidiary of a
  public company, or whose name EDGAR spells differently, is missed (for example Bell Canada,
  whose parent BCE files the 40-F). A wrong same-name match is possible; `match_basis` records
  how each one was made.
- Most non-US high-yield issuers do not file with the SEC, so the non-US pass found 20 of the
  30 allowed.
- 6-K classification reads titles and the start of each document. A report that follows a
  release in the same document is missed (Methanex, Vermilion), and an unusual title can be
  missed or misread. Interim reports are the three latest on EDGAR: where an issuer did not
  furnish a quarter, an older one is used (Genmab's H1 2026 report is not on EDGAR).
- The funds' holdings dates differ (2026-06-30 to 2026-08-31), and N-PORT holdings are public only
  after a delay.
- Earnings releases are not presentations. Packs with releases for some or all quarters keep
  `complete` false.
- Packs are retrieved documents, not checked analysis. A failed or partial pack is recorded, not
  repaired.
