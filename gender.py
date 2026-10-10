"""gender.py - binary gender of a person inferred from the first given name.

The MUR tables give names only. The inference is a statistical proxy to be used
in aggregate, never as an attribute of an individual, and it is binary. A
reviewed table (data/given_names.csv: given name, F or M, and whether the entry
was curated by hand or follows the Italian ending rule -a feminine, -o
masculine) covers every name seen so far. A name missing from the table falls
back on the ending rule and is left unresolved if that does not apply
(names ending in -e or -i, foreign names).
"""
import logging
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

from tabella_a import split_name

log = logging.getLogger(__name__)

TABLE = Path(__file__).with_name("data") / "given_names.csv"


def load_table(path: Path = TABLE) -> dict:
    t = pd.read_csv(path)
    return dict(zip(t["given"], t["gender"]))


def first_given_from_surname_first(name: str) -> str:
    """'DAL CORSO Francesco Maria' (Tabella B order) -> 'Francesco'."""
    given, _ = split_name(" ".join(_reorder(name)))
    return given.split()[0] if given else ""


def _reorder(name: str) -> List[str]:
    """Move the leading all-capital surname words of 'SURNAME Given' behind the given names."""
    words = name.split()
    k = 0
    while k < len(words) and words[k].upper() == words[k]:
        k += 1
    return words[k:] + words[:k]


def infer(given: str, table: Optional[dict] = None) -> Optional[str]:
    """'F', 'M', or None when neither the table nor the ending rule decides."""
    table = load_table() if table is None else table
    if given in table:
        return table[given]
    if given.lower().endswith("a"):
        return "F"
    if given.lower().endswith("o"):
        return "M"
    return None


def unresolved(givens: Iterable[str], table: Optional[dict] = None) -> List[str]:
    """Given names that are not in the reviewed table, for the maintainer to add."""
    table = load_table() if table is None else table
    return sorted({g for g in givens if g and g not in table})
