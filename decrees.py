"""decrees.py - the MUR decrees that approve each ERC sector's ranking.

Each sector (PE1-11, LS1-9, SH1-8) is approved by its own Decreto Direttoriale,
published on a page of mur.gov.it that carries three PDFs: the decree, its
Tabella A (final ranking) and its Tabella B (funded projects). A decree can be
annulled and replaced by a later one (PE7: n.32 -> n.45); only the current
decree of each sector is kept.

Every decree text carries the same table of available funds per sector, in
euros, split into the ring-fenced "under 40" pool and the ordinary pool
(Fondi ordinari); `parse_budgets` reads it.
"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote, urljoin

from common import START, fetch_pdf, num, sector_of

log = logging.getLogger(__name__)

ALL_SECTORS = ([f"PE{i}" for i in range(1, 12)] + [f"LS{i}" for i in range(1, 10)]
               + [f"SH{i}" for i in range(1, 9)])

BUDGET_ROW = re.compile(
    r"\b(?P<sector>(?:PE|LS|SH) ?\d{1,2}) (?P<u40>[\d.]+,\d\d) € "
    r"(?P<ordinary>[\d.]+,\d\d) € (?P<total>[\d.]+,\d\d) €")
ANNULLED = re.compile(r"annullato e sostituito dal decreto n\. ?(\d+)")


def _page_info(sess, url):
    """Return the decree record of one atti-e-normativa page, or None if it has no PDFs."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(sess.get(url, timeout=60).text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" "))
    pdfs = [urljoin(url, a["href"]) for a in soup.find_all("a", href=True)
            if a["href"].lower().split("?")[0].endswith(".pdf")]
    pdfs = list(dict.fromkeys(pdfs))
    kind = {"tabella_a": None, "tabella_b": None, "decree": None}
    for u in pdfs:
        low = unquote(u).lower()
        if "tabella_a" in low or "tabella a" in low:
            kind["tabella_a"] = u
        elif "tabella_b" in low or "tabella b" in low:
            kind["tabella_b"] = u
        elif kind["decree"] is None:
            kind["decree"] = u
    if not (kind["tabella_b"] and kind["decree"]):
        return None
    number = (re.search(r"N° Atto (\d+)", text)
              or re.search(r"Decreto Direttoriale n\.? ?(\d+) del", text))
    date = re.search(r"Data di protocollo (\d\d/\d\d/\d{4})", text)
    replaced = ANNULLED.search(text)
    return dict(
        sector=sector_of(unquote(kind["tabella_b"]).rsplit("/", 1)[-1]),
        decree_number=int(number.group(1)) if number else None,
        date=date.group(1) if date else None,
        page=url, annulled_by=int(replaced.group(1)) if replaced else None, **kind)


def find_decrees(sess):
    """Scrape the PRIN page; return {sector: record} for the current decree of each sector."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(sess.get(START, timeout=60).text, "html.parser")
    pages = sorted({urljoin(START, a["href"]) for a in soup.find_all("a", href=True)
                    if "mur.gov.it" in urljoin(START, a["href"])
                    and "atti-e-normativa" in a["href"]})
    current: Dict[str, dict] = {}
    for p in pages:
        try:
            rec = _page_info(sess, p)
        except Exception as e:
            log.warning("%s: %s", p, e)
            continue
        if rec is None or not rec["sector"]:
            continue
        if rec["annulled_by"]:
            log.info("%s (n.%s) annulled by n.%s: skipped", rec["sector"],
                     rec["decree_number"], rec["annulled_by"])
            continue
        old = current.get(rec["sector"])
        if old and old["decree_number"] > rec["decree_number"]:
            continue
        current[rec["sector"]] = rec
    return current


def download_decrees(sess, decrees, out_dir):
    """Save each sector's decree and Tabella A under out_dir/{decrees,tabella_a}/."""
    failed = []
    for sub, key in (("decrees", "decree"), ("tabella_a", "tabella_a")):
        d = Path(out_dir) / sub
        d.mkdir(parents=True, exist_ok=True)
        for sec, rec in decrees.items():
            if not rec[key]:
                continue
            dest = d / f"{sec}_n{rec['decree_number']}.pdf"
            if not fetch_pdf(sess, rec[key], dest):
                failed.append(rec[key])
    return failed


def parse_budgets(pdf_paths: List[Path]) -> Dict[str, dict]:
    """Funds per sector from the decrees' table; every decree must give the same numbers."""
    from pypdf import PdfReader
    budgets: Dict[str, dict] = {}
    for f in pdf_paths:
        flat = re.sub(r"\s+", " ", "\n".join((p.extract_text() or "")
                                              for p in PdfReader(f).pages))
        found = {m["sector"].replace(" ", ""): dict(under40=num(m["u40"]), ordinary=num(m["ordinary"]),
                                   total=num(m["total"]))
                 for m in BUDGET_ROW.finditer(flat)}
        for sec, b in found.items():
            if abs(b["under40"] + b["ordinary"] - b["total"]) > 0.015:
                raise ValueError(f"{f.name}: {sec} under40 + ordinary != total: {b}")
            if sec in budgets and budgets[sec] != b:
                raise ValueError(f"{f.name}: {sec} budget differs from another decree: "
                                 f"{b} vs {budgets[sec]}")
            budgets[sec] = b
    return budgets


def save_manifest(path, decrees, budgets):
    Path(path).write_text(json.dumps(dict(decrees=decrees, budgets=budgets),
                                     indent=1, ensure_ascii=False, sort_keys=True))


def load_manifest(path) -> Optional[dict]:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


SECTOR_BEGIN, SECTOR_END = "<!-- sectors:begin -->", "<!-- sectors:end -->"


def sector_table(manifest: dict, rows: List[dict]) -> str:
    """Markdown table of the 28 sectors: decree, budget, and what has been parsed."""
    dec, bud = manifest["decrees"], manifest["budgets"]
    parsed = {r["sector"] for r in rows}
    lines = ["| Sector | Status | Decree | Budget (M EUR) | Funded (M EUR) | Projects |",
             "|---|---|---|---:|---:|---:|"]
    for sec in ALL_SECTORS:
        b = bud.get(sec, {}).get("total")
        budget = f"{b / 1e6:.2f}" if b else ""
        if sec in dec:
            d = dec[sec]
            link = f"[n. {d['decree_number']} of {d['date']}]({d['page']})"
        else:
            link = ""
        sel = [r for r in rows if r["sector"] == sec]
        if sec in parsed:
            lines.append(f"| {sec} | parsed | {link} | {budget} | "
                         f"{sum(r['mur_contribution'] for r in sel) / 1e6:.2f} | "
                         f"{len({r['project_code'] for r in sel})} |")
        elif sec in dec:
            lines.append(f"| {sec} | published, not parsed | {link} | {budget} | | |")
        else:
            lines.append(f"| {sec} | not yet published | | {budget} | | |")
    done = sum(sec in parsed for sec in ALL_SECTORS)
    return f"{done} of {len(ALL_SECTORS)} sectors parsed.\n\n" + "\n".join(lines)


def update_readme(path, manifest: dict, rows: List[dict]):
    """Rewrite the text between the sector markers of the README; no markers, no change."""
    p = Path(path)
    text = p.read_text()
    if SECTOR_BEGIN not in text or SECTOR_END not in text:
        log.warning("%s has no sector markers: not updated", p)
        return
    head, rest = text.split(SECTOR_BEGIN, 1)
    tail = rest.split(SECTOR_END, 1)[1]
    p.write_text(f"{head}{SECTOR_BEGIN}\n{sector_table(manifest, rows)}\n{SECTOR_END}{tail}")


def describe_changes(old: Optional[dict], new: dict) -> str:
    """Markdown list of the sectors that are new or whose decree changed between two manifests."""
    old_dec = (old or {}).get("decrees", {})
    lines = []
    for sec in sorted(new["decrees"], key=lambda x: (x[:2], int(x[2:]))):
        rec = new["decrees"][sec]
        if sec not in old_dec:
            lines.append(f"- {sec}: new, decree n. {rec['decree_number']} of {rec['date']} ({rec['page']})")
        elif old_dec[sec]["decree_number"] != rec["decree_number"]:
            lines.append(f"- {sec}: decree n. {old_dec[sec]['decree_number']} replaced by n. "
                         f"{rec['decree_number']} of {rec['date']} ({rec['page']})")
    return "\n".join(lines) if lines else "No sector is new; files of known sectors changed."
