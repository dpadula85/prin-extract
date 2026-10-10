# prin-extract

Extract the funded projects of the Italian **PRIN 2026** call (MUR, *Tabella B – Progetti finanziati*) from the official PDFs into a searchable table, and filter them by university.

The MUR publishes the results as one PDF per ERC-style sector (PE = Physical Sciences & Engineering, LS = Life Sciences, SH = Social Sciences & Humanities). They are hard to search: one project spans several rows (the coordinating unit and its partners) and the title sits apart from the rows. This tool turns them into a flat table with one row per research unit.

Source: <https://prin.mur.gov.it/Pages/Index/301>

## Contents

| Path | What it is |
|---|---|
| `prin_extract.py` | The script: finds/downloads the PDFs, parses them, writes the tables |
| `prin_pdfs/` | The Tabella B PDFs as downloaded from MUR |
| `prin_out/prin2026_funded_projects.xlsx` | Excel output: `Summary`, one sheet per `--uni`, `All units` |
| `prin_out/all_rows.csv` | Every parsed unit (726 rows) |
| `prin_out/SIENA.csv` | Units of Università degli Studi di Siena (8 projects, 5 as coordinator) |

`prin_pdfs/` currently holds the sectors LS2, LS3, LS4, LS7, PE1–3, PE5–11, SH4–7. Sectors not in that folder (e.g. PE4, LS1, LS5, LS6, SH1–3) are **not** in the tables; the Summary sheet lists which sectors were parsed. The folder also holds `PE7_..._Progetti finanziati.pdf` and `PE7_..._Progetti_finanziati.pdf`, byte-identical copies; the script de-duplicates them.

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
