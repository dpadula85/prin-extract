#!/usr/bin/env python3
"""
PRIN 2026 - extract funded projects (MUR "Tabella B") and filter by university.

Setup:   pip install requests beautifulsoup4 pypdf openpyxl
Run:     python prin_extract.py --uni SIENA --uni "PISA" --uni 80002070524
         python prin_extract.py --uni SIENA --pdf-dir ./prin_pdfs   # offline, PDFs already downloaded

--uni accepts a substring of the institution name (case-insensitive) or the
11-digit codice fiscale (exact, preferred: "MILANO" also matches Politecnico
and Bicocca; the CF 80012650158 is only Statale).

Output (in --out, default ./prin_out):
  prin2026_funded_projects.xlsx   plain Excel file (opens in Excel, LibreOffice, Google Sheets):
                                  "Summary" sheet, one sheet per --uni, and "All units"
  add --csv to also write all_rows.csv and one CSV per --uni
"""
import argparse, csv, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, unquote

START = "https://prin.mur.gov.it/Pages/Index/301"

ROW = re.compile(
    r"\b(?P<n>\d{1,2}) (?P<role>PI|RU) (?P<name>.+?) "
    r"(?P<code>20\d{2}[A-Z0-9]{6})_(?P<unit>\d{3}) (?P<inst>.+?) "
    r"(?P<cf>\d{11}) (?P<cofin>[\d.]+,\d\d) (?P<contrib>[\d.]+,\d\d) "
    r"(?P<cost>[\d.]+,\d\d) (?P<mur>[\d.]+,\d\d)"
)
TITLE = re.compile(
    r"\b\d{1,2}\. (?P<code>20\d{2}[A-Z0-9]{6}) - (?P<title>.+?)"
    r"(?= Totale| \d{1,2}\. 20\d{2}[A-Z0-9]{6} - | n° Nome| Cofinanziament| "
    r"(?:PE|LS|SH)\d+ - Tabella|$)"
)


def num(s):
    return float(s.replace(".", "").replace(",", "."))


def parse_text(text, sector=""):
    """Return (rows, titles) from the raw text of one Tabella B PDF."""
    flat = re.sub(r"\s+", " ", text)
    rows = []
    for m in ROW.finditer(flat):
        d = m.groupdict()
        rows.append(dict(
            sector=sector, project_code=d["code"], unit=int(d["unit"]),
            role=d["role"], name=d["name"].strip(), institution=d["inst"].strip(),
            cf=d["cf"], mur_contribution=num(d["mur"]), total_cost=num(d["cost"]),
        ))
    titles = {m["code"]: m["title"].strip() for m in TITLE.finditer(flat)}
    return rows, titles


def find_pdf_urls():
    import requests
    from bs4 import BeautifulSoup
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (prin-extract)"
    soup = BeautifulSoup(s.get(START, timeout=60).text, "html.parser")
    pages = {urljoin(START, a["href"]) for a in soup.find_all("a", href=True)
             if "mur.gov.it" in urljoin(START, a["href"]) and "atti-e-normativa" in a["href"]}
    pdfs = set()
    for p in sorted(pages):
        try:
            sp = BeautifulSoup(s.get(p, timeout=60).text, "html.parser")
        except Exception as e:
            print(f"! {p}: {e}", file=sys.stderr); continue
        for a in sp.find_all("a", href=True):
            u = urljoin(p, a["href"])
            name = unquote(u).lower()
            if name.endswith(".pdf") and "tabella" in name and "finanziati" in name:
                pdfs.add(u)
    return sorted(pdfs), s


def fetch_pdf(sess, url, dest, tries=3):
    """Download url to dest; only accept real PDFs (server sometimes returns HTML)."""
    if dest.exists() and dest.read_bytes()[:5] == b"%PDF-":
        return True
    for i in range(tries):
        try:
            r = sess.get(url, timeout=120,
                         headers={"Referer": START, "Accept": "application/pdf,*/*"})
            if r.ok and r.content[:5] == b"%PDF-":
                dest.write_bytes(r.content)
                return True
            print(f"  try {i+1}: {dest.name} -> HTTP {r.status_code}, "
                  f"{r.headers.get('content-type')}, not a PDF", file=sys.stderr)
        except Exception as e:
            print(f"  try {i+1}: {dest.name} -> {e}", file=sys.stderr)
        time.sleep(2 * (i + 1))
    return False


HEAD = [("sector", "Sector", 8), ("project_code", "Project code", 14), ("title", "Title", 60),
        ("role", "Role", 7), ("name", "Name", 26), ("institution", "Institution", 42),
        ("cf", "Tax code", 14), ("mur_contribution", "MUR contribution (EUR)", 20),
        ("total_cost", "Total cost (EUR)", 17), ("coordinator", "Project coordinator", 46)]


def write_xlsx(path, uni_results, all_rows):
    """uni_results: list of (label, rows). Values only: no macros, no formulas."""
    import datetime
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    arial, bold = Font(name="Arial", size=10), Font(name="Arial", size=10, bold=True)
    head_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1F4E78")
    key = lambda r: (r["sector"], r["project_code"], r["unit"])

    def table(ws, headers, widths, data_rows, money_cols=()):
        ws.append(headers)
        for c in ws[1]:
            c.font, c.fill = head_font, head_fill
            c.alignment = Alignment(wrap_text=True, vertical="center")
        for row in data_rows:
            ws.append(row)
        for r in ws.iter_rows(min_row=2):
            for c in r:
                c.font = arial
                c.alignment = Alignment(vertical="top", wrap_text=True)
                if c.column in money_cols:
                    c.number_format = "#,##0"
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        if data_rows:
            ws.auto_filter.ref = ws.dimensions

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    summ = []
    for label, rows in uni_results:
        summ.append([label, len({r["project_code"] for r in rows}),
                     sum(r["role"] == "PI" for r in rows), sum(r["role"] == "RU" for r in rows),
                     sum(r["mur_contribution"] for r in rows)])
    table(ws, ["University (filter used)", "Projects", "Units as PI (coordinator)",
               "Units as RU (partner)", "MUR contribution (EUR)"],
          [28, 11, 24, 21, 22], summ, money_cols=(5,))
    n = ws.max_row + 2
    notes = ["PI = principal investigator (coordinating institution); RU = research unit (partner).",
             "Source: MUR PRIN 2026, 'Tabella B - Progetti finanziati' PDFs (prin.mur.gov.it).",
             f"Generated {datetime.date.today().isoformat()} by prin_extract.py. "
             "Parsed automatically from PDFs: verify against the official tables.",
             "Sectors included: " + ", ".join(sorted({r["sector"] for r in all_rows}))]
    for i, t in enumerate(notes):
        c = ws.cell(row=n + i, column=1, value=t)
        c.font = arial
        c.alignment = Alignment(wrap_text=False)

    used = {"Summary", "All units"}
    for label, rows in uni_results:
        name = re.sub(r"[\[\]:*?/\\]", "_", label)[:31] or "uni"
        base, k = name, 2
        while name in used:
            name = f"{base[:28]}_{k}"; k += 1
        used.add(name)
        table(wb.create_sheet(name), [h[1] for h in HEAD], [h[2] for h in HEAD],
              [[r.get(h[0], "") for h in HEAD] for r in sorted(rows, key=key)], money_cols=(8, 9))
    table(wb.create_sheet("All units"), [h[1] for h in HEAD], [h[2] for h in HEAD],
          [[r.get(h[0], "") for h in HEAD] for r in sorted(all_rows, key=key)], money_cols=(8, 9))
    wb.save(path)


def dedupe(rows):
    """Drop duplicate units (same project_code + unit) using pandas; report conflicts."""
    import pandas as pd
    df = pd.DataFrame(rows)
    key = ["project_code", "unit"]
    cmp = ["role", "name", "institution", "cf", "mur_contribution", "total_cost"]
    dup = df[df.duplicated(key, keep=False)]
    if dup.empty:
        print("No duplicate rows.")
        return rows
    conflicts = dup.drop_duplicates(key + cmp)
    conflicts = conflicts[conflicts.duplicated(key, keep=False)]
    before = len(df)
    # if two copies differ, keep the one from the most recently downloaded file
    df = (df.sort_values("mtime", kind="stable").drop_duplicates(key, keep="last")
            .sort_values(["sector", "project_code", "unit"]))
    print(f"Removed {before - len(df)} duplicate rows ({before} -> {len(df)}). "
          f"Files involved: {', '.join(sorted(dup['source'].unique()))}")
    if len(conflicts):
        print("! Copies with DIFFERENT content (kept the newest file) - check which PDF is current:",
              file=sys.stderr)
        print(conflicts[["source"] + key + cmp].to_string(index=False), file=sys.stderr)
    return df.drop(columns=["mtime"]).to_dict("records")


def sector_of(name):
    m = re.search(r"(?<![A-Z0-9])(PE\d+|LS\d+|SH\d+|CYB)(?!\d)", name.upper())
    return m.group(1) if m else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uni", action="append", required=True)
    ap.add_argument("--pdf-dir", default="prin_pdfs")
    ap.add_argument("--out", default="prin_out")
    ap.add_argument("--no-download", action="store_true", help="only parse PDFs already in --pdf-dir")
    ap.add_argument("--csv", action="store_true", help="also write CSV files")
    a = ap.parse_args()

    from pypdf import PdfReader
    pdf_dir, out = Path(a.pdf_dir), Path(a.out)
    pdf_dir.mkdir(exist_ok=True); out.mkdir(exist_ok=True)

    if not a.no_download:
        urls, sess = find_pdf_urls()
        print(f"Found {len(urls)} Tabella B PDFs")
        failed = []
        for u in urls:
            f = pdf_dir / Path(unquote(u)).name.replace("[1]", "")
            if not fetch_pdf(sess, u, f):
                failed.append(u)
        if failed:
            print("\n! Could not download these as PDFs. Open them in a browser, save into "
                  f"{pdf_dir}/ and re-run with --no-download:", file=sys.stderr)
            for u in failed:
                print("   ", u, file=sys.stderr)
            print(file=sys.stderr)

    rows, titles = [], {}
    for f in sorted(pdf_dir.glob("*.pdf")):
        if f.read_bytes()[:5] != b"%PDF-":
            print(f"! skipping {f.name}: not a PDF (HTML error page?) - delete it and re-download",
                  file=sys.stderr)
            continue
        try:
            text = "\n".join((p.extract_text() or "") for p in PdfReader(f).pages)
        except Exception as e:
            print(f"! skipping {f.name}: {e}", file=sys.stderr)
            continue
        r, t = parse_text(text, sector_of(f.name))
        for x in r:
            x["source"], x["mtime"] = f.name, f.stat().st_mtime
        rows += r; titles.update(t)
        print(f"{f.name}: {len(r)} units, {len(t)} titles")

    rows = dedupe(rows)
    print("Sectors parsed:", ", ".join(sorted({r["sector"] for r in rows})))
    coord = {r["project_code"]: f'{r["name"]} ({r["institution"]})' for r in rows if r["role"] == "PI"}
    for r in rows:
        r["title"] = titles.get(r["project_code"], "")
        r["coordinator"] = coord.get(r["project_code"], "")
    cols = ["sector", "project_code", "title", "role", "name", "institution", "cf",
            "mur_contribution", "total_cost", "coordinator"]

    def write(path, data):
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(data)

    if a.csv:
        write(out / "all_rows.csv", rows)
    results = []
    for u in a.uni:
        key = u.lower()
        sel = [r for r in rows if (r["cf"] == u if u.isdigit() else key in r["institution"].lower())]
        if a.csv:
            write(out / f"{re.sub(r'[^A-Za-z0-9]+', '_', u)}.csv", sel)
        results.append((u, sel))
        projects = {r["project_code"] for r in sel}
        pis = sum(r["role"] == "PI" for r in sel)
        print(f"\n== {u}: {len(projects)} projects ({pis} as coordinator), "
              f"{sum(r['mur_contribution'] for r in sel):,.0f} EUR MUR")
        for r in sorted(sel, key=lambda x: (x["sector"], x["project_code"])):
            print(f'  {r["sector"]:4} {r["project_code"]} {r["role"]} {r["name"]}  | {r["title"][:70]}')

    xlsx = out / "prin2026_funded_projects.xlsx"
    write_xlsx(xlsx, results, rows)
    print(f"\nWrote {xlsx}")


if __name__ == "__main__":
    main()
