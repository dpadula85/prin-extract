"""institutions.py - rows of data/institutions.csv for institutions that are not in it yet.

The table gives each institution (tax code) a short name, city, region, coordinates and
type. A new institution is added with its short name from the name in the PDF, its type
from keywords of the name, and its city, region and coordinates from a search of the name
in OpenStreetMap (Nominatim). These are guesses to be checked: the pull request lists the
added rows. A failed search leaves city, region and coordinates empty.
"""
import logging
import re
import time
from pathlib import Path
from typing import List

import pandas as pd
import requests

log = logging.getLogger(__name__)

TABLE = Path(__file__).with_name("data") / "institutions.csv"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
COLUMNS = ["cf", "short_name", "city", "region", "lat", "lon", "kind"]


def guess_kind(name: str) -> str:
    n = name.lower()
    if "telematic" in n:
        return "telematic"
    if "accademia" in n:
        return "afam"
    if n.startswith("scuola") or "istituto universitario" in n or "institute" in n:
        return "school"
    if n.startswith("istituto nazionale") or "consiglio nazionale" in n:
        return "research_body"
    if "università degli studi" in n or "politecnico" in n or "università per stranieri" in n:
        return "public_university"
    return "private_university"


def guess_short_name(name: str) -> str:
    s = re.sub(r"^(Università|Univ\.)\s+(degli Studi|della|del|di|dell')?\s*(di|del|della|dell')?\s*", "", name.strip(), flags=re.I)
    return s.strip(' "').title() if s.isupper() else s.strip(' "')


def geocode(name: str) -> dict:
    """City, region, latitude and longitude of the first OpenStreetMap match, or empty."""
    time.sleep(1.1)
    try:
        r = requests.get(NOMINATIM, timeout=30, headers={"User-Agent": "prin-extract (aggregate statistics)"},
                         params=dict(q=name + ", Italia", format="json", addressdetails=1, limit=1, countrycodes="it"))
        r.raise_for_status()
        hit = r.json()[0]
    except (requests.RequestException, IndexError, ValueError) as e:
        log.warning("no location found for %s: %s", name, e)
        return dict(city="", region="", lat="", lon="")
    a = hit["address"]
    city = next((a[k] for k in ("city", "town", "village", "municipality") if k in a), "")
    return dict(city=city, region=a.get("state", ""), lat=round(float(hit["lat"]), 3), lon=round(float(hit["lon"]), 3))


def record_missing(units: pd.DataFrame, path: Path = TABLE) -> List[str]:
    """Add the institutions of `units` (columns cf, institution) missing from the table;
    return their names."""
    t = pd.read_csv(path, dtype={"cf": str}, keep_default_na=False)
    new = units[~units["cf"].isin(t["cf"])].drop_duplicates("cf")
    if new.empty:
        return []
    rows = []
    for cf, name in zip(new["cf"], new["institution"]):
        kind = guess_kind(name)
        loc = geocode(name) if kind != "national_research_body" else dict(city="", region="", lat="", lon="")
        rows.append(dict(cf=cf, short_name=guess_short_name(name), kind=kind, **loc))
        log.warning("institution added to data/institutions.csv, to check: %s -> %s", name, rows[-1])
    pd.concat([t, pd.DataFrame(rows)[COLUMNS]], ignore_index=True).sort_values("short_name").to_csv(path, index=False)
    return list(new["institution"])
