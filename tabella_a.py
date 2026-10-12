"""tabella_a.py - parse the MUR "Tabella A - Graduatoria finale" of one ERC sector.

Tabella A ranks the projects that the evaluation committee judged fundable,
funded or not; the funded ones are the top of the list and are in Tabella B
(the funded set is not exactly the top k: the under-40 pool funds young PIs
further down the ranking). Columns: rank, project code, title, principal
investigator (PI), total score, and, only for rows tied on the total score at
the cut, the tie-break data: excellence, impact and equity scores, number of
men and women in the team, and the PI's birth date (day and month masked,
"XX/XX/1976").

The PDF content stream lists the table row by row and cell by cell (rank,
code, title lines, name lines, score, tie-break cells), so the cells are read
in stream order. A long title or name is split over several cells, one per
printed line. After the score come, in this order and as far as the tie
requires, excellence, impact, equity, men, women (integers) and the date.
A score that is a whole number is printed without decimals.
"""
import logging
import re
from pathlib import Path
from typing import List, Tuple

log = logging.getLogger(__name__)

CODE = re.compile(r"2026[A-Z0-9]{6}")
NUMBER = re.compile(r"\d+(?:,\d\d)?")
MASKED_DATE = re.compile(r"[\dX]{2}/[\dX]{2}/(\d{4})")
NOISE = re.compile(r"[A-Z]+\d+ [–-] Tabella|n°|Codice|Titolo progetto|Principal|Punteggio|Criterio|"
                   r"Totale|totale|domanda|eccellenza|impatto|Equità|uomini|donne|Data di|Investigator|"
                   r"nascita|PI$")
FOOTNOTE = "I PI con meno di 40 anni"


def _is_caps(word: str) -> bool:
    return word.upper() == word and any(c.isalpha() for c in word)


def split_name(full: str) -> Tuple[str, str]:
    """'Maria Beatrice POZZETTI' -> ('Maria Beatrice', 'POZZETTI'): the surname is the
    first run of all-capital words (given names can follow it)."""
    words = re.sub(r"(?<=\w-) ", "", full).split()
    caps = [_is_caps(w) for w in words]
    if not any(caps):
        return full, ""
    i = caps.index(True)
    j = i
    while j < len(words) and caps[j]:
        j += 1
    return " ".join(words[:i] + words[j:]), " ".join(words[i:j])


def _has_surname_and_given(name: str) -> bool:
    words = name.split()
    return any(_is_caps(w) for w in words) and any(not _is_caps(w) for w in words)


def _title_and_name(body: List[str]) -> Tuple[str, str]:
    """Split a row's text cells into the title and the PI name: the name is the last
    cell, extended backwards until it has both a surname (all-capital word) and a
    given name."""
    k = len(body) - 1
    while k > 0 and not _has_surname_and_given(" ".join(body[k:])):
        k -= 1
    return " ".join(body[:k]), " ".join(body[k:])


def _is_green(rgb) -> bool:
    r, g, b = rgb
    return g > r + 0.15 and g > b + 0.15


def read_cells(path: Path) -> List[Tuple[str, bool]]:
    """Text cells of the PDF in content-stream order, each with whether it is printed in
    green (the PDF marks the code and/or the name of under-40 PIs that way)."""
    from pypdf import PdfReader
    cells: List[Tuple[str, bool]] = []
    fill = (0.0, 0.0, 0.0)

    def operand(operator, args, cm, tm):
        nonlocal fill
        if operator == b"rg":
            fill = tuple(float(a) for a in args)
        elif operator == b"g":
            fill = (float(args[0]),) * 3

    def text(t, cm, tm, font_dict, font_size):
        if t.strip():
            cells.append((re.sub(r"\s+", " ", t.strip()), _is_green(fill)))
    for page in PdfReader(path).pages:
        fill = (0.0, 0.0, 0.0)
        page.extract_text(visitor_operand_before=operand, visitor_text=text)
    return cells


def parse_cells(cells: List[Tuple[str, bool]], sector: str) -> List[dict]:
    rows: List[dict] = []
    cur = None
    for c, green in cells:
        if c.startswith(FOOTNOTE):
            cur = None
        elif CODE.fullmatch(c):
            if cur is not None and cur["numbers"] and cur["numbers"][-1] == str(len(rows) + 1):
                cur["numbers"].pop()  # the next row's rank, printed before its code
            cur = dict(rank=len(rows) + 1, project_code=c, under40=green, body=[], numbers=[])
            rows.append(cur)
        elif cur is None or NOISE.match(c):
            continue
        elif NUMBER.fullmatch(c) or MASKED_DATE.fullmatch(c):
            cur["numbers"].append(c)
        else:
            cur["under40"] = cur["under40"] or green  # LS6 prints only the name in green
            cur["body"].append(c)
    out = []
    for r in rows:
        if not r["body"]:
            raise ValueError(f"{sector} {r['project_code']}: no title or name cells")
        title, name = _title_and_name(r["body"])
        given, surname = split_name(name)
        date = next((MASKED_DATE.fullmatch(x) for x in r["numbers"]
                     if MASKED_DATE.fullmatch(x)), None)
        values = [float(x.replace(",", ".")) for x in r["numbers"] if NUMBER.fullmatch(x)]
        score, rest = (values[0], values[1:]) if values else (None, [])
        if score is None or len(rest) not in (0, 1, 2, 3, 5):
            raise ValueError(f"{sector} {r['project_code']}: unexpected numbers {r['numbers']}")
        tie = rest[:3] + [None] * (3 - len(rest[:3]))
        men, women = (int(rest[3]), int(rest[4])) if len(rest) == 5 else (None, None)
        out.append(dict(
            sector=sector, rank=r["rank"], project_code=r["project_code"],
            title=re.sub(r"(?<=\w-) ", "", title), pi_given=given, pi_surname=surname,
            score=score, excellence=tie[0], impact=tie[1], equity=tie[2], men=men, women=women,
            birth_year=int(date.group(1)) if date else None, under40=r["under40"]))
    return out


def parse_pdf(path: Path, sector: str) -> List[dict]:
    """All ranked rows of one Tabella A PDF."""
    return parse_cells(read_cells(Path(path)), sector)
