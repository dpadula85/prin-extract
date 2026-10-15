"""focus.py - the funded units of one group of disciplines (GSD 2024), subsector by subsector.

A GSD code is "AA/NAME-NN" (03/CHEM-05: area 03, chemistry; GSD CHEM-05). data/focus.txt lists
code prefixes, one per line ("03/CHEM" = the seven chemistry GSDs, "02" = all of physics);
every GSD that starts with a prefix and has at least one funded unit leader gets its own row
in the tables below and its own page in report/focus.pdf (report.py).

The only GSD data are those of the unit leaders (PI and partner-unit leaders) found in the
MUR directory of university staff (gsd.py): the other members of a team, and leaders at
research bodies, are not in it, so a GSD is seen through its leaders only. The staff of the
directory is known by CUN area, not by GSD, so no measure is normalised by the staff of a GSD.
"""
import logging
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import analysis as an
import gsd
from analysis import DATA, PI_COLOR, RU_COLOR, tex

log = logging.getLogger(__name__)

FOCUS = DATA / "focus.txt"
LEVELS = {"Ordinario": "po", "Associato": "pa", "Ricercatore": "ru"}  # the others are fixed-term (rtd)


def focus_prefixes() -> List[str]:
    """GSD code prefixes of data/focus.txt; blank lines and lines starting with # are ignored."""
    if not FOCUS.exists():
        return []
    lines = [l.strip() for l in FOCUS.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l and not l.startswith("#")]


def slug(prefix: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in prefix.lower())


def leaders(d: an.Data, cache: pd.DataFrame) -> pd.DataFrame:
    """Every funded unit whose leader was found at the university of the unit, with the leader's
    GSD, sub-sector (SSD), career level, and whether the project's PI is under 40."""
    c = cache[cache["status"] == "found"][["name", "institution", "gsd", "ssd", "role"]]
    u = d.units.merge(c.rename(columns={"role": "career"}), on=["name", "institution"], how="inner")
    u["level"] = u["career"].map(LEVELS).fillna("rtd")
    u["area"] = u["gsd"].str[:2]
    young = d.ranking.set_index("project_code")["under40"]
    u["pi_under40"] = u["project_code"].map(young).fillna(False).astype(bool)
    return u


def tables(d: an.Data, cache: pd.DataFrame, prefix: str) -> Dict[str, pd.DataFrame]:
    """Aggregates of the leaders whose GSD starts with `prefix`: `profile` and `ssd` (one row
    per GSD / SSD), `sectors` (units by GSD and ERC sector), `partners` (units of the same
    projects, by the CUN area of their leader), `institutions` (money by GSD and institution)."""
    allu = leaders(d, cache)
    sel = allu[allu["gsd"].str.startswith(prefix)]
    codes = sorted(sel["gsd"].unique())

    def profile(group: str, rows: pd.DataFrame) -> pd.DataFrame:
        t = rows.groupby(group).agg(
            units=("name", "size"), pi_units=("role", lambda s: int((s == "PI").sum())),
            projects=("project_code", "nunique"), institutions=("cf", "nunique"),
            erc_sectors=("sector", "nunique"), mur_total=("mur_contribution", "sum"),
            women=("gender", lambda s: int((s == "F").sum())))
        t["ru_units"] = t["units"] - t["pi_units"]
        t["pi_money"] = rows[rows["role"] == "PI"].groupby(group)["mur_contribution"].sum().reindex(t.index).fillna(0.0)
        t["ru_money"] = t["mur_total"] - t["pi_money"]
        t["budget_share_pct"] = 100 * t["mur_total"] / d.budget
        t["mean_k_eur_per_unit"] = t["mur_total"] / t["units"] / 1e3
        t["women_pct"] = 100 * t["women"] / t["units"]
        t["pi_under40"] = rows[(rows["role"] == "PI") & rows["pi_under40"]].groupby(group).size().reindex(t.index).fillna(0).astype(int)
        for k in ("po", "pa", "rtd", "ru"):
            t[k] = rows[rows["level"] == k].groupby(group).size().reindex(t.index).fillna(0).astype(int)
        return t

    prof = pd.concat([profile("gsd", sel), profile("all", sel.assign(all="All"))])
    ssd = profile("ssd", sel)
    sectors = sel.pivot_table(index="gsd", columns="sector", values="name", aggfunc="count", fill_value=0)
    money = sel.pivot_table(index="gsd", columns="sector", values="mur_contribution", aggfunc="sum", fill_value=0.0)
    rows = []
    for g in codes:
        mine = set(sel.loc[sel["gsd"] == g, "project_code"])
        others = allu[allu["project_code"].isin(mine) & (allu["gsd"] != g)]
        n_units = int(d.units["project_code"].isin(mine).sum())
        rows.append(dict(gsd=g, units_in_projects=n_units, other_units=n_units - int((sel["gsd"] == g).sum()),
                         other_found=len(others),
                         **{a: int((others["area"] == a).sum()) for a in sorted(allu["area"].unique())}))
    partners = pd.DataFrame(rows).set_index("gsd")
    inst = (sel.groupby(["gsd", "short_name"]).agg(units=("name", "size"), mur_total=("mur_contribution", "sum"))
            .reset_index().sort_values(["gsd", "mur_total"], ascending=[True, False]))
    return dict(profile=prof, ssd=ssd, sectors=sectors, money=money, partners=partners, institutions=inst,
                units=sel.sort_values(["gsd", "sector"]))


def coverage(d: an.Data, cache: pd.DataFrame, prefix: str) -> Dict[str, int]:
    """In the ERC sectors that have at least one leader of the focus, how many unit leaders there
    are and for how many the GSD was found."""
    allu = leaders(d, cache)
    secs = set(allu.loc[allu["gsd"].str.startswith(prefix), "sector"])
    units = d.units[d.units["sector"].isin(secs)]
    found = allu[allu["sector"].isin(secs)]
    return dict(sectors=len(secs), leaders=len(units), found=len(found))


def partner_areas(t: Dict[str, pd.DataFrame]) -> List[str]:
    """CUN area codes with at least one other unit in the projects of the GSDs (the columns of the
    partners figure)."""
    p = t["partners"].drop(columns=["units_in_projects", "other_units", "other_found"])
    return [a for a in p.columns if p[a].sum() > 0]


def _annotated_matrix(fig, ax, m: pd.DataFrame, cmap: str):
    im = ax.imshow(m.to_numpy(), cmap=cmap, aspect="auto", vmin=0)
    ax.set_xticks(range(m.shape[1]), [tex(str(c)) for c in m.columns], rotation=45, ha="right")
    ax.set_yticks(range(m.shape[0]), [tex(str(i)) for i in m.index])
    ax.tick_params(which="minor", length=0)
    top = m.to_numpy().max()
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = int(m.iat[i, j])
            if v:
                ax.text(j, i, str(v), ha="center", va="center", fontsize=18,
                        color="white" if v > 0.55 * top else "black")
    return im


def figures(d: an.Data, t: Dict[str, pd.DataFrame], prefix: str, fig_dir: Path):
    """focus_<slug>_money (PI and partner money by GSD), _sectors (units by GSD and ERC sector)
    and _partners (units of the same projects by CUN area of their leader)."""
    s = slug(prefix)
    prof = t["profile"].drop(index="All")
    n = len(prof)
    fig, ax = an._axes(small=True)
    y = np.arange(n)[::-1]
    ax.barh(y, 100 * prof["pi_money"] / d.budget, color=PI_COLOR, label="as coordinator (PI)")
    ax.barh(y, 100 * prof["ru_money"] / d.budget, left=100 * prof["pi_money"] / d.budget, color=RU_COLOR,
            label="as partner (RU)")
    ax.set_yticks(y, [tex(f"{g} ({int(u)})") for g, u in zip(prof.index, prof["units"])])
    ax.yaxis.set_minor_locator(plt.NullLocator())
    ax.set_xlabel(r"Share of total budget / \%")
    ax.legend(title=tex(f"{an._stamp(d)}; units of the leaders found (number)"), loc="lower center",
              bbox_to_anchor=(0.5, 1.01), ncol=2, fontsize=20, title_fontsize=20)
    an._save(fig, ax, fig_dir, f"focus_{s}_money")

    fig, ax = an._axes(small=True)
    fig.set_size_inches(14, 9)
    _annotated_matrix(fig, ax, t["sectors"], "Blues")
    ax.set_xlabel(r"ERC sector")
    ax.set_title(tex(f"{an._stamp(d)}; funded units by GSD of the leader"), fontsize=22)
    an._save(fig, ax, fig_dir, f"focus_{s}_sectors")

    p = t["partners"].drop(columns=["units_in_projects", "other_units", "other_found"])
    p = p.loc[:, p.sum() > 0]
    fig, ax = an._axes(small=True)
    fig.set_size_inches(14, 9)
    _annotated_matrix(fig, ax, p, "Oranges")
    ax.set_xticks(range(p.shape[1]), list(p.columns), rotation=0)
    ax.set_xlabel(r"CUN area of the other leaders")
    ax.set_title(tex(f"{an._stamp(d)}; other units of the same projects"), fontsize=22)
    an._save(fig, ax, fig_dir, f"focus_{s}_partners")


def run(out_dir: Path) -> None:
    """Tables to prin_out/analysis/focus_<slug>_*.csv and figures to prin_out/figures/ for every
    prefix of data/focus.txt; nothing if the file or the GSD cache is missing."""
    prefixes = focus_prefixes()
    if not prefixes or not gsd.CACHE.exists():
        return
    d = an.load(out_dir)
    cache = gsd.load_cache()
    for prefix in prefixes:
        t = tables(d, cache, prefix)
        if t["units"].empty:
            log.warning("focus %r: no funded unit leader has a GSD starting with it", prefix)
            continue
        for name in ("profile", "ssd", "sectors", "money", "partners", "institutions"):
            t[name].to_csv(out_dir / "analysis" / f"focus_{slug(prefix)}_{name}.csv", encoding="utf-8-sig")
        figures(d, t, prefix, out_dir / "figures")
