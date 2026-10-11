"""gsd.py - disciplinary group (GSD 2024) of the leaders of the funded units.

The MUR tables give a leader's name and institution only. The GSD (gruppo scientifico
disciplinare) of a university professor or researcher is looked up, one leader at a time,
in the staff search of the MUR portal Cerca Università (https://cercauniversita.mur.gov.it):
first among professors and permanent researchers, then among fixed-term researchers. A
result counts only if the university of the record matches the institution of the leader.
Leaders of research bodies (CNR, INAF, ...) and of other institutions that are not
universities are not in that directory.

Each answer is cached in cache/gsd_lookup.csv (not versioned: it names individuals), so a
run asks the portal only about leaders it has not seen. Only aggregates are written to
prin_out/analysis/ by analysis.py.

    python3 gsd.py             # look up every funded leader not in the cache
    python3 gsd.py --limit 20  # first 20 only, to try it
"""
import argparse as arg
import html
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

from gender import _reorder
from tabella_a import split_name

log = logging.getLogger(__name__)

URL = "https://cercauniversita.mur.gov.it/"
CACHE = Path(__file__).with_name("cache") / "gsd_lookup.csv"
FIELDS = "filtri_ricerca_docenti_form[%s]"
# "00": professors and permanent researchers; "RD": fixed-term researchers (all types).
ROLES = ("00", "RD")
COLUMNS = ["name", "institution", "status", "role", "university", "gsd", "ssd", "n_candidates"]
PAUSE = 1.5


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9 ]+", " ", s)


def search_names(name: str) -> tuple:
    """(surname, first given name) of a Tabella B name 'SURNAME Given Second'."""
    surname = " ".join(w for w in name.split() if w.upper() == w)
    given, _ = split_name(" ".join(_reorder(name)))
    return surname, given.split()[0] if given else ""


class Portal:
    """The search form of the portal, with the session token it asks for."""

    def __init__(self, pause: float = PAUSE):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "Mozilla/5.0 (prin-extract, aggregate statistics)"
        self.pause = pause
        self.token = None

    def _token(self) -> str:
        page = self.session.get(URL, timeout=30)
        page.raise_for_status()
        m = re.search(r'name="filtri_ricerca_docenti_form\[_token\]" value="([^"]+)"', page.text)
        if m is None:
            raise RuntimeError("search form of %s has no token: the page layout changed" % URL)
        return m.group(1)

    def query(self, surname: str, given: str, role: str) -> List[List[str]]:
        """Rows (role, name, university, department, GSD 2024, SSD 2024) of the search."""
        if self.token is None:
            self.token = self._token()
        form = {FIELDS % "_token": self.token, FIELDS % "cognome": surname, FIELDS % "nome": given,
                FIELDS % "ruolo": role, FIELDS % "statoRuolo": "0", FIELDS % "servizioAltroAteneo": "0"}
        time.sleep(self.pause)
        resp = self.session.post(URL, data=form, timeout=30)
        resp.raise_for_status()
        if "Risultati di ricerca" not in resp.text:
            raise RuntimeError("no result block for %s %s: the page layout changed" % (surname, given))
        block = resp.text.split("Risultati di ricerca")[-1].split("Altre risorse")[0]
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", block, flags=re.S):
            cells = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()
                     for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
            if len(cells) >= 6:
                rows.append(cells)
        return rows


GENERIC = {"UNIV", "UNIVERSITA", "DEGLI", "STUDI", "DI", "DEL", "DELLA", "DELLE", "DELL", "E", "LA", "LIBERA"}


def _university_words(s: str) -> frozenset:
    """Words of a university name without the generic ones and the single letters, so that
    'Univ. "Campus Bio-Medico" di ROMA' and 'Università "Campus Bio-Medico" di ROMA' agree
    and 'L'AQUILA' agrees with 'dell'AQUILA'."""
    return frozenset(w for w in _norm(s).split() if w not in GENERIC and len(w) > 1)


def same_university(institution: str, university: str, extra: str = "") -> bool:
    """Whether every word of the portal's university name is in the institution name, so
    that 'ROMA "La Sapienza"' matches 'Università degli Studi di ROMA "La Sapienza"', while a
    polytechnic is not taken for the university of the same city. `extra` adds the short name
    and city of the institution, since the PDF names are cut ("IULM-MI") or spell out an acronym."""
    inst, uni = _university_words(institution + " " + extra), _university_words(university)
    if not uni or ("POLITECNICO" in inst) != ("POLITECNICO" in uni):
        return False
    return uni <= inst


def resolve(portal: Portal, name: str, institution: str, extra: str = "") -> Dict[str, object]:
    """The GSD record of one leader: status 'found', 'ambiguous' (several records at that
    university), 'other_university' (found only elsewhere) or 'not_found'."""
    surname, given = search_names(name)
    seen = 0
    for role in ROLES:
        rows = portal.query(surname, given, role)
        seen += len(rows)
        here = [r for r in rows if same_university(institution, r[2], extra)]
        # the search matches a leading part of the given name: keep the exact surname
        here = [r for r in here if _norm(r[1]).startswith(_norm(surname) + " ")]
        # 'MILANO' and 'MILANO-BICOCCA' both fit 'MILANO-BICOCCA': keep the most specific name
        if here:
            longest = max(len(_university_words(r[2])) for r in here)
            here = [r for r in here if len(_university_words(r[2])) == longest]
        if len(here) == 1:
            r = here[0]
            return dict(status="found", role=r[0], university=r[2], gsd=r[4], ssd=r[5], n_candidates=len(rows))
        if len(here) > 1:
            return dict(status="ambiguous", role="", university="", gsd="", ssd="", n_candidates=len(here))
    status = "other_university" if seen else "not_found"
    return dict(status=status, role="", university="", gsd="", ssd="", n_candidates=seen)


def load_cache(path: Path = CACHE) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return pd.DataFrame(columns=COLUMNS)


def lookup_all(units: pd.DataFrame, limit: Optional[int] = None, path: Path = CACHE) -> pd.DataFrame:
    """Look up the leaders of `units` (columns name, institution) not yet in the cache."""
    cache = load_cache(path)
    done = set(zip(cache["name"], cache["institution"]))
    todo = units.drop_duplicates(["name", "institution"])
    todo = todo[[k not in done for k in zip(todo["name"], todo["institution"])]]
    if limit is not None:
        todo = todo.head(limit)
    log.info("%d leaders to look up, %d already cached", len(todo), len(done))
    inst = pd.read_csv(Path(__file__).with_name("data") / "institutions.csv", dtype={"cf": str}).set_index("cf")
    extra = (inst["short_name"] + " " + inst["city"]).to_dict()
    portal, new = Portal(), []
    path.parent.mkdir(exist_ok=True)
    for k, (_, row) in enumerate(todo.iterrows(), 1):
        rec = dict(name=row["name"], institution=row["institution"], **resolve(portal, row["name"], row["institution"], extra.get(row["cf"], "")))
        new.append(rec)
        if k % 25 == 0 or k == len(todo):
            out = pd.concat([cache, pd.DataFrame(new)], ignore_index=True)[COLUMNS]
            out.to_csv(path, index=False)
            log.info("%d/%d looked up", k, len(todo))
    return pd.concat([cache, pd.DataFrame(new)], ignore_index=True)[COLUMNS] if new else cache


def main(argv=None) -> int:
    ap = arg.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("prin_out"),
                    help="directory written by prin_extract.py")
    ap.add_argument("--limit", type=int, help="look up this many leaders only")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    units = pd.read_csv(args.out / "all_rows.csv", dtype={"cf": str})
    table = lookup_all(units, args.limit)
    print(table["status"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
