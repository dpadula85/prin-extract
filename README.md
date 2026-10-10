# prin-extract

Extract the funded projects of the Italian **PRIN 2026** call (MUR, *Tabella B – Progetti finanziati*) from the official PDFs into a searchable table, and filter them by university.

The MUR publishes the results as one PDF per ERC-style sector (PE = Physical Sciences & Engineering, LS = Life Sciences, SH = Social Sciences & Humanities). They are hard to search: one project spans several rows (the coordinating unit and its partners) and the title sits apart from the rows. This tool turns them into a flat table with one row per research unit.

Source: <https://prin.mur.gov.it/Pages/Index/301>

## Contents

| Path | What it is |
|---|---|
| `prin_extract.py` | The script: finds/downloads the PDFs, parses them, writes the tables |
| `prin_pdfs/` | The Tabella B PDFs as downloaded from MUR; `decrees/` and `tabella_a/` hold each sector's decree and ranking |
| `prin_out/decrees.json` | Current decree of each sector (links, number, date) and the funds per sector |
| `common.py`, `decrees.py` | Shared helpers; decree scraping, funds table, README sector table |
| `prin_out/prin2026_funded_projects.xlsx` | Excel output: `Summary`, one sheet per `--uni`, `All units` |
| `prin_out/all_rows.csv` | Every parsed unit (726 rows) |
| `prin_out/SIENA.csv` | Units of Università degli Studi di Siena (8 projects, 5 as coordinator) |

## Sectors

Each ERC sector is approved by its own decree (*Decreto Direttoriale*), which carries the final ranking (Tabella A), the funded projects (Tabella B) and the funds available to the sector, split into the ring-fenced under-40 pool and the ordinary pool. A decree can be annulled and replaced (PE7: n. 32, replaced by n. 45); only the current one is listed. Sectors that are not parsed are **not** in the tables. The table is rewritten by the script.

<!-- sectors:begin -->
18 of 28 sectors parsed.

| Sector | Status | Decree | Budget (M EUR) | Funded (M EUR) | Projects |
|---|---|---|---:|---:|---:|
| PE1 | parsed | [n. 29 of 05/10/2026](https://www.mur.gov.it/it/atti-e-normativa/decreto-direttoriale-n29-del-05-10-2026) | 5.52 | 5.52 | 5 |
| PE2 | parsed | [n. 30 of 05/10/2026](https://www.mur.gov.it/it/atti-e-normativa/decreto-direttoriale-n-30-del-05-10-2026) | 7.32 | 6.99 | 6 |
| PE3 | parsed | [n. 31 of 05/10/2026](https://www.mur.gov.it/it/atti-e-normativa/decreto-direttoriale-n31-del-05-10-2026) | 5.98 | 5.14 | 5 |
| PE4 | not yet published | | 7.15 | | |
| PE5 | parsed | [n. 47 of 08/10/2026](https://www.mur.gov.it/it/atti-e-normativa/decreto-direttoriale-n47-del-08-10-2026) | 8.22 | 8.22 | 8 |
| PE6 | parsed | [n. 48 of 08/10/2026](https://www.mur.gov.it/it/atti-e-normativa/decreto-direttoriale-n-48-del-08-10-2026) | 7.42 | 6.95 | 6 |
| PE7 | parsed | [n. 45 of 06/10/2026](https://www.mur.gov.it/it/atti-e-normativa/bando-prin-2026-ddg-6-ottobre-2026-n-45-macrosettore-pe-settore-pe7-approvazione) | 11.79 | 11.45 | 11 |
| PE8 | parsed | [n. 33 of 05/10/2026](https://www.mur.gov.it/it/atti-e-normativa/decreto-direttoriale-n33-del-05-10-2026) | 16.69 | 16.46 | 14 |
| PE9 | parsed | [n. 34 of 05/10/2026](https://www.mur.gov.it/it/atti-e-normativa/decreto-direttoriale-n34-del-05-10-2026) | 4.97 | 4.29 | 4 |
| PE10 | parsed | [n. 35 of 05/10/2026](https://www.mur.gov.it/it/atti-e-normativa/decreto-direttoriale-n35-del-05-10-2026) | 9.41 | 9.24 | 9 |
| PE11 | parsed | [n. 36 of 05/10/2026](https://www.mur.gov.it/it/atti-e-normativa/decreto-direttoriale-n36-del-05-10-2026) | 6.49 | 6.49 | 6 |
| LS1 | not yet published | | 6.88 | | |
| LS2 | parsed | [n. 37 of 06/10/2026](https://www.mur.gov.it/it/atti-e-normativa/bando-prin-2026-ddg-6-ottobre-2026-n-37-macrosettore-ls-settore-ls2-approvazione) | 6.53 | 5.43 | 5 |
| LS3 | parsed | [n. 38 of 06/10/2026](https://www.mur.gov.it/it/atti-e-normativa/bando-prin-2026-ddg-6-ottobre-2026-n-38-macrosettore-ls-settore-ls3-approvazione) | 5.66 | 4.67 | 4 |
| LS4 | parsed | [n. 42 of 06/10/2026](https://www.mur.gov.it/it/atti-e-normativa/bando-prin-2026-ddg-6-ottobre-2026-n-42-macrosettore-ls-settore-ls4-approvazione) | 12.94 | 12.09 | 12 |
| LS5 | not yet published | | 9.77 | | |
| LS6 | not yet published | | 7.81 | | |
| LS7 | parsed | [n. 39 of 06/10/2026](https://www.mur.gov.it/it/atti-e-normativa/bando-prin-2026-ddg-6-ottobre-2026-n-39-macrosettore-ls-settore-ls7-approvazione) | 17.88 | 17.88 | 17 |
| LS8 | not yet published | | 8.39 | | |
| LS9 | not yet published | | 15.11 | | |
| SH1 | not yet published | | 10.58 | | |
| SH2 | not yet published | | 11.87 | | |
| SH3 | not yet published | | 9.36 | | |
| SH4 | parsed | [n. 40 of 06/10/2026](https://www.mur.gov.it/it/atti-e-normativa/bando-prin-2026-ddg-6-ottobre-2026-n-40-macrosettore-sh-settore-sh4-approvazione) | 9.62 | 8.12 | 8 |
| SH5 | parsed | [n. 41 of 06/10/2026](https://www.mur.gov.it/it/atti-e-normativa/bando-prin-2026-ddg-6-ottobre-2026-n-41-macrosettore-sh-settore-sh5-approvazione) | 10.50 | 10.22 | 9 |
| SH6 | parsed | [n. 44 of 06/10/2026](https://www.mur.gov.it/it/atti-e-normativa/bando-prin-2026-ddg-6-ottobre-2026-n-44-macrosettore-sh-settore-sh6-approvazione) | 9.37 | 9.25 | 9 |
| SH7 | parsed | [n. 49 of 09/10/2026](https://www.mur.gov.it/it/atti-e-normativa/decreto-direttoriale-n-49-del-09-10-2026) | 7.70 | 7.00 | 6 |
| SH8 | not yet published | | 8.96 | | |
<!-- sectors:end -->

`prin_pdfs/` also holds `PE7_..._Progetti finanziati.pdf` and `PE7_..._Progetti_finanziati.pdf`, byte-identical copies of the same table; the script de-duplicates them.

## Install

```
pip install requests beautifulsoup4 pypdf openpyxl pandas
```

## Usage

```
# download the PDFs and filter for one or more universities
python3 prin_extract.py --uni SIENA --uni PISA --uni 80002070524 --csv

# offline, using the PDFs already in prin_pdfs/
python3 prin_extract.py --uni SIENA --no-download --csv
```

Options: `--uni` (repeatable, required), `--pdf-dir` (default `prin_pdfs`), `--out` (default `prin_out`), `--no-download`, `--csv`.

`--uni` takes either a case-insensitive substring of the institution name or an 11-digit tax code (codice fiscale), matched exactly. Prefer the tax code: `MILANO` also matches Politecnico and Bicocca, whereas `80012650158` is only Statale.

## Output columns

`sector`, `project_code`, `title`, `role` (PI = coordinating unit, RU = partner unit), `name` (unit leader), `institution`, `cf` (institution tax code), `mur_contribution` (EUR), `total_cost` (EUR), `coordinator` (name and institution of the project's PI).

## How it works

1. `find_pdf_urls` scrapes the PRIN page and the MUR "atti e normativa" pages it links to, keeping PDFs whose name contains `tabella` and `finanziati`. `fetch_pdf` accepts only files that really start with `%PDF-` (the server sometimes answers with an HTML page); failed downloads are listed so they can be saved manually and parsed with `--no-download`.
2. `pypdf` extracts the text, whitespace is flattened, and two regular expressions are applied: `ROW` matches a unit (`n  PI|RU  name  CODE_unit  institution  tax code  four amounts`) and `TITLE` matches `n. CODE - title`. Project code links the two.
3. The sector is taken from the PDF file name; duplicate (project, unit) pairs across files are dropped, keeping the newest file and warning if copies differ.
4. Rows are filtered by `--uni` and written to xlsx (values only, no macros) and optionally CSV.

## Checks and limits

- For each PDF the number of parsed units equals the number of `CODE_unit` identifiers in its text, and the number of titles equals the number of projects, so the regexes miss no rows in the PDFs present.
- The parsing is automatic and depends on the PDF layout: verify any figure you rely on against the official tables.
- Amounts are those of the Tabella B columns "Costo totale" and "Contributo MUR"; the other two money columns (co-financing, contribution) are matched but not exported.

The PDFs are public documents of the Ministero dell'Università e della Ricerca; the script is released under the MIT licence.
