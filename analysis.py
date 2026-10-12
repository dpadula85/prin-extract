"""analysis.py - who gets the PRIN 2026 money: tables and figures from the parsed PDFs.

Inputs are the outputs of prin_extract.py (prin_out/all_rows.csv, ranking.csv,
decrees.json) and the hand-checked tables in data/ (institution -> city, region
and type; given name -> gender; region boundaries). Everything refers to the
sectors parsed so far, never to the whole call.

Definitions (euros):
  budget       sum, over the parsed sectors, of the funds the decrees make
               available to the sector (under-40 pool + ordinary pool)
  share        MUR contribution received by an institution or region,
               divided by `budget`, in percent
  PI / RU      coordinating unit / partner unit of a project; a project's
               money is the sum of its units' MUR contributions

National research bodies (CNR, INAF, INFN, INGV) are multi-site and have no
region: they form their own bucket in the regional tables and are left off
the maps. Gender is inferred from the first given name (gender.py) and is
used only in aggregate.

Tables go to prin_out/analysis/*.csv, figures to prin_out/figures/*.{pdf,png}.
"""
import argparse as arg
import datetime
import json
import logging
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import cm, colors
from matplotlib.patches import Polygon
from matplotlib.ticker import MaxNLocator
from scipy import stats

import gender
import gsd
import institutions
from style import new_axes, save_centered

log = logging.getLogger(__name__)

DATA = Path(__file__).with_name("data")
NATIONAL = "National research bodies"
KIND_LABELS = {"public_university": "Public univ.", "private_university": "Private univ.",
               "telematic": "Telematic univ.", "school": "Advanced schools",
               "research_body": "Research bodies", "national_research_body": "National bodies",
               "afam": "AFAM"}
MACRO_AREA = {"North": ["Piemonte", "Valle d'Aosta/Vallée d'Aoste", "Liguria", "Lombardia",
                         "Trentino-Alto Adige/Südtirol", "Veneto", "Friuli-Venezia Giulia", "Emilia-Romagna"],
              "Centre": ["Toscana", "Umbria", "Marche", "Lazio"],
              "South and Islands": ["Abruzzo", "Molise", "Campania", "Puglia", "Basilicata", "Calabria",
                                    "Sicilia", "Sardegna"]}
PI_COLOR, RU_COLOR, GREY = "#1f4e78", "#c8782a", "#9a9a9a"
U40_COLOR = "#3f8d15"  # the green the MUR tables print under-40 PIs in
SMALL = {"xtick.labelsize": 22, "ytick.labelsize": 22, "font.size": 28}


USE_LATEX = True


def _axes(small: bool = False, tick: Optional[int] = None):
    """Axes in the house style; `small` lowers the font sizes for figures with many labels.
    The sizes are applied after `new_axes`, which resets the rcParams it owns."""
    fig, ax = new_axes(USE_LATEX)
    if small or tick:
        plt.rcParams.update(SMALL)
        ax.tick_params(axis="both", which="major", labelsize=tick or SMALL["xtick.labelsize"])
        for label in (ax.xaxis.label, ax.yaxis.label):  # created with the axes at the full size
            label.set_fontsize(SMALL["font.size"])
    return fig, ax


def tex(s: str) -> str:
    """Escape the characters LaTeX treats specially in a label."""
    for a, b in (("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#")):
        s = s.replace(a, b)
    return s


@dataclass
class Data:
    units: pd.DataFrame
    ranking: pd.DataFrame
    budgets: pd.DataFrame
    budget: float
    sectors: list


def load(out_dir: Path) -> Data:
    """Units joined with the institution table, ranking with inferred gender, budgets."""
    units = pd.read_csv(out_dir / "all_rows.csv", dtype={"cf": str})
    inst = pd.read_csv(DATA / "institutions.csv", dtype={"cf": str})
    if institutions.record_missing(units, DATA / "institutions.csv"):
        inst = pd.read_csv(DATA / "institutions.csv", dtype={"cf": str})
    units = units.merge(inst, on="cf", how="left")
    units["region"] = units["region"].fillna(NATIONAL)
    ranking = pd.read_csv(out_dir / "ranking.csv")
    manifest = json.loads((out_dir / "decrees.json").read_text())
    budgets = pd.DataFrame(manifest["budgets"]).T.rename_axis("sector").reset_index()
    sectors = sorted(units["sector"].unique(), key=lambda x: (x[:2], int(x[2:])))
    budget = float(budgets.loc[budgets["sector"].isin(sectors), "total"].sum())
    table = gender.load_table()
    ranking["gender"] = [gender.infer(g.split()[0], table) if isinstance(g, str) and g else None
                         for g in ranking["pi_given"]]
    units["gender"] = [gender.infer(gender.first_given_from_surname_first(n), table)
                       for n in units["name"]]
    missing = gender.unresolved(
        [g.split()[0] for g in ranking["pi_given"].dropna()]
        + [gender.first_given_from_surname_first(n) for n in units["name"]], table)
    if missing:
        log.warning("given names not in data/given_names.csv, added: %s", ", ".join(missing))
        review = gender.record_missing(missing)
        if review:
            log.warning("given names to review in data/given_names.csv: %s", ", ".join(review))
    return Data(units, ranking, budgets, budget, sectors)


# ---------------------------------------------------------------- tables

def _money(df: pd.DataFrame, by, budget: float) -> pd.DataFrame:
    """Per group: projects, PI/RU units, MUR money split by role, share of the budget."""
    g = df.groupby(by)
    t = pd.DataFrame({
        "projects": g["project_code"].nunique(),
        "pi_units": g["role"].agg(lambda r: int((r == "PI").sum())),
        "ru_units": g["role"].agg(lambda r: int((r == "RU").sum())),
        "mur_total": g["mur_contribution"].sum(),
        "mur_pi": g.apply(lambda x: x.loc[x["role"] == "PI", "mur_contribution"].sum(),
                          include_groups=False),
    })
    t["mur_ru"] = t["mur_total"] - t["mur_pi"]
    t["share_of_budget_pct"] = 100 * t["mur_total"] / budget
    return t.sort_values("mur_total", ascending=False)


def institution_table(d: Data) -> pd.DataFrame:
    """One row per institution: money, roles, the number of sectors with a funded unit,
    and its rank by funding overall and among institutions of the same type."""
    t = _money(d.units, "cf", d.budget)
    info = d.units.drop_duplicates("cf").set_index("cf")[["short_name", "city", "region", "kind"]]
    t = info.join(t).sort_values("mur_total", ascending=False)
    t["n_sectors"] = d.units.groupby("cf")["sector"].nunique()
    t["rank"] = np.arange(1, len(t) + 1)
    t["rank_in_type"] = t.groupby("kind").cumcount() + 1
    return t


def institution_sector_table(d: Data) -> pd.DataFrame:
    """Long table, one row per institution and sector in which it has funded units."""
    g = d.units.groupby(["cf", "short_name", "sector"])
    t = g.agg(projects=("project_code", "nunique"), mur=("mur_contribution", "sum"),
              pi_units=("role", lambda r: int((r == "PI").sum())),
              ru_units=("role", lambda r: int((r == "RU").sum()))).reset_index()
    t["share_of_budget_pct"] = 100 * t["mur"] / d.budget
    return t.sort_values(["short_name", "sector"])


def region_table(d: Data) -> pd.DataFrame:
    regions = [f["properties"]["region"] for f in
               json.loads((DATA / "italy_regions.geojson").read_text())["features"]]
    t = _money(d.units, "region", d.budget)
    t = t.reindex(regions + [NATIONAL]).fillna(0.0)
    t["pi_share_of_region_pct"] = 100 * t["mur_pi"] / t["mur_total"].where(t["mur_total"] > 0)
    return t


def macro_area_table(d: Data) -> pd.DataFrame:
    """The regional money grouped into North, Centre, South and Islands (national bodies
    left out), with the share of it that came from coordinating units."""
    units = d.units.copy()
    units["area"] = units["region"].map({r: a for a, rs in MACRO_AREA.items() for r in rs})
    t = _money(units[units["area"].notna()], "area", d.budget).reindex(list(MACRO_AREA))
    t["pi_share_of_region_pct"] = 100 * t["mur_pi"] / t["mur_total"]
    return t


def sector_table(d: Data) -> pd.DataFrame:
    rows = []
    for sec in d.sectors:
        funded = d.units[d.units["sector"] == sec]
        rk = d.ranking[d.ranking["sector"] == sec]
        b = d.budgets.set_index("sector").loc[sec]
        last = rk.loc[rk["funded"], "score"].min()
        first_out = rk.loc[~rk["funded"], "score"].max()
        rows.append(dict(sector=sec, budget=b["total"], funded=funded["mur_contribution"].sum(),
                         n_funded=funded["project_code"].nunique(), n_ranked=len(rk),
                         last_funded_score=last, best_unfunded_score=first_out))
    t = pd.DataFrame(rows).set_index("sector")
    t["used_pct"] = 100 * t["funded"] / t["budget"]
    return t


def concentration(inst: pd.DataFrame) -> Dict[str, float]:
    """Gini coefficient and top-10 share of the money, among institutions with funding."""
    x = np.sort(inst["mur_total"].to_numpy())
    cum = np.concatenate([[0.0], np.cumsum(x)]) / x.sum()
    p = np.linspace(0.0, 1.0, len(cum))
    return dict(gini=float(1 - 2 * np.trapezoid(cum, p)), n_institutions=int(len(x)),
                top10_share=float(x[-10:].sum() / x.sum()))


def wilson(k: int, n: int):
    if n == 0:
        return np.nan, np.nan, np.nan
    ci = stats.binomtest(k, n).proportion_ci(method="wilson")
    return k / n, ci.low, ci.high


def gender_table(d: Data) -> pd.DataFrame:
    """Female share (of persons with an inferred gender) in each group, Wilson 95% interval."""
    rk, un = d.ranking.copy(), d.units.copy()
    rk["macro"], un["macro"] = rk["sector"].str[:2], un["sector"].str[:2]
    groups = {"PI, funded": rk[rk["funded"]], "Partner-unit leaders, funded": un[un["role"] == "RU"]}
    rows = []
    for label, df in groups.items():
        for macro in ["PE", "LS", "SH", "All"]:
            sel = df if macro == "All" else df[df["macro"] == macro]
            known = sel["gender"].dropna()
            f, lo, hi = wilson(int((known == "F").sum()), len(known))
            rows.append(dict(group=label, macro=macro, n=len(sel), n_known=len(known),
                             female_share=f, low=lo, high=hi))
    return pd.DataFrame(rows)


REGION_CONTEXT = {"population": "population_regions.csv", "staff": "university_staff.csv"}


def region_context_table(regions: pd.DataFrame) -> pd.DataFrame:
    """Per region, the share of the total budget (as in the regional map) beside the share of
    the resident population (1 January 2026) and of the professors and researchers (2025) of
    the Italian regions. The budget shares do not add up to 100: national research bodies
    and the budget not yet assigned are not regions. The ratio is the budget share divided by
    the other share."""
    pop = pd.read_csv(DATA / REGION_CONTEXT["population"], index_col=0)["population"]
    st = pd.read_csv(DATA / REGION_CONTEXT["staff"], index_col=0)
    reg = regions.drop(NATIONAL)
    t = pd.DataFrame({"mur_total": reg["mur_total"], "population": pop.reindex(reg.index),
                      "staff": (st["professors"] + st["researchers"]).reindex(reg.index)})
    t["budget_share_pct"] = reg["share_of_budget_pct"]
    for col in ("population", "staff"):
        t[f"{col}_share_pct"] = 100 * t[col] / t[col].sum()
    t["budget_over_population"] = t["budget_share_pct"] / t["population_share_pct"]
    t["budget_over_staff"] = t["budget_share_pct"] / t["staff_share_pct"]
    return t


def under40_table(d: Data) -> pd.DataFrame:
    """Per sector: the ring-fenced under-40 pool, the MUR money that went to the funded
    projects of under-40 PIs, and how many of those were funded below the best unfunded
    over-40 project of the ranking (a lower bound on the projects only the pool can have
    funded). The ranking lists only fundable projects, not everything submitted, so no
    success rate by age group can be formed from it."""
    budgets = d.budgets.set_index("sector")
    rows = []
    for sec in d.sectors:
        r = d.ranking[d.ranking["sector"] == sec]
        young = r[r["under40"]]
        best_out = r.loc[~r["funded"] & ~r["under40"], "rank"].min()
        funded_young = young[young["funded"]]["project_code"]
        rows.append(dict(
            sector=sec, ranked_under40=len(young), funded_under40=int(young["funded"].sum()),
            ranked_over40=len(r) - len(young), funded_over40=int(r[~r["under40"]]["funded"].sum()),
            pool=budgets.loc[sec, "under40"], ordinary=budgets.loc[sec, "ordinary"],
            money_under40_projects=d.units.loc[d.units["project_code"].isin(funded_young),
                                               "mur_contribution"].sum(),
            funded_below_ordinary_cut=int((young["funded"] & (young["rank"] > best_out)).sum())
            if not np.isnan(best_out) else 0))
    return pd.DataFrame(rows).set_index("sector")


# --------------------------------------------------------------- figures

def _save(fig, ax, fig_dir: Path, name: str):
    save_centered(fig, ax, fig_dir / f"{name}.pdf")
    fig.savefig(fig_dir / f"{name}.png", dpi=150)
    plt.close(fig)


def _stamp(d: Data) -> str:
    return f"{len(d.sectors)} of 28 sectors"


def fig_institutions(d: Data, inst: pd.DataFrame, fig_dir: Path, n: int = 20):
    top = inst.head(n)[::-1]
    fig, ax = _axes(small=True)
    y = np.arange(len(top))
    ax.barh(y, 100 * top["mur_pi"] / d.budget, color=PI_COLOR, label="as coordinator (PI)")
    ax.barh(y, 100 * top["mur_ru"] / d.budget, left=100 * top["mur_pi"] / d.budget,
            color=RU_COLOR, label="as partner (RU)")
    ax.set_yticks(y, [tex(s) for s in top["short_name"]])
    ax.yaxis.set_minor_locator(plt.NullLocator())
    ax.set_xlabel(r"Share of budget / \%")
    ax.set_title(tex(f"Top {n} institutions, {_stamp(d)}"), fontsize=24)
    ax.legend(loc="lower right")
    _save(fig, ax, fig_dir, "institutions_share")


def fig_budget_drop(d: Data, inst: pd.DataFrame, fig_dir: Path, n_named: int = 10):
    """Budget not yet assigned once the k best-funded institutions are accounted for, in
    percent of the budget of the parsed sectors."""
    ranked = inst.sort_values("mur_total", ascending=False)
    left = 100 * (1 - np.concatenate([[0.0], np.cumsum(ranked["mur_total"].to_numpy())]) / d.budget)
    k = np.arange(len(left))
    fig, ax = _axes(small=True)
    ax.step(k, left, where="post", color=PI_COLOR, lw=3)
    for j, y_text in zip(range(1, n_named + 1), np.linspace(97, 43, n_named)):
        ax.annotate(tex(rf"{ranked['short_name'].iloc[j - 1]} ({left[j - 1] - left[j]:.1f}%)"),
                    (j, (left[j - 1] + left[j]) / 2), xytext=(0.27 * len(ranked), y_text),
                    textcoords="data", fontsize=22, va="center",
                    arrowprops=dict(arrowstyle="-", color="0.5", lw=1.0, shrinkA=3, shrinkB=2,
                                    relpos=(0, 0.5)))
    ax.set_xlabel(r"Institutions accounted for, best funded first / 1")
    ax.set_ylabel(r"Budget left / \% of total")
    ax.set_xlim(0, len(ranked)), ax.set_ylim(0, 102)
    top = d.budget / 1e6
    sec = ax.secondary_yaxis("right", functions=(lambda y: y * top / 100, lambda m: 100 * m / top))
    sec.set_ylabel(r"Budget left / M EUR", fontsize=SMALL["font.size"])
    sec.tick_params(labelsize=SMALL["xtick.labelsize"])
    _save(fig, ax, fig_dir, "budget_by_institution")


DIRECTIONS = ((1, 0, "left", "center"), (-1, 0, "right", "center"), (0, 1, "center", "bottom"),
              (0, -1, "center", "top"), (0.7, 0.7, "left", "bottom"), (-0.7, 0.7, "right", "bottom"),
              (0.7, -0.7, "left", "top"), (-0.7, -0.7, "right", "top"))


def _overlap(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(w, 0.0) * max(h, 0.0)


def _place_labels(fig, ax, xy, radius_pts, which, labels, fontsize=18, colors=None, backing=False):
    """Write `labels` next to the nodes `which` (indices into `xy`, the data coordinates of
    all nodes; `radius_pts` their marker radii in points) at the first of eight positions
    that overlaps no earlier label, no node and not the axes frame; the largest nodes are
    labelled first. Falls back on the least-overlapping position."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    scale = fig.dpi / 72.0
    centres = ax.transData.transform(np.asarray(xy))
    radii = np.asarray(radius_pts, dtype=float) * scale
    frame = ax.get_window_extent(renderer)
    nodes = [(c[0] - r, c[1] - r, c[0] + r, c[1] + r) for c, r in zip(centres, radii)]
    placed = []
    for k in sorted(range(len(which)), key=lambda k: -radii[which[k]]):
        i = which[k]
        probe = ax.text(0, 0, labels[k], fontsize=fontsize)
        box = probe.get_window_extent(renderer)
        probe.remove()
        best = None
        for dx, dy, ha, va in DIRECTIONS:
            gap = radii[i] + 3 * scale
            ax_, ay_ = centres[i][0] + dx * gap, centres[i][1] + dy * gap
            x0 = ax_ - {"left": 0, "center": box.width / 2, "right": box.width}[ha]
            y0 = ay_ - {"bottom": 0, "center": box.height / 2, "top": box.height}[va]
            cand = (x0, y0, x0 + box.width, y0 + box.height)
            penalty = sum(_overlap(cand, o) for o in placed)
            penalty += sum(_overlap(cand, n) for j, n in enumerate(nodes) if j != i)
            penalty += 10 * (box.width * box.height - _overlap(cand, (frame.x0, frame.y0, frame.x1, frame.y1)))
            if best is None or penalty < best[0]:
                best = (penalty, dx, dy, ha, va, cand)
                if penalty == 0:
                    break
        _, dx, dy, ha, va, cand = best
        placed.append(cand)
        gap_pts = radius_pts[i] + 3
        ax.annotate(labels[k], tuple(xy[i]), xytext=(dx * gap_pts, dy * gap_pts),
                    textcoords="offset points", ha=ha, va=va, fontsize=fontsize, zorder=6,
                    color=None if colors is None else colors[k],
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.8) if backing else None)


def _draw_regions(ax, values: Optional[pd.Series], cmap, norm, label_values: bool):
    feats = json.loads((DATA / "italy_regions.geojson").read_text())["features"]
    for f in feats:
        name = f["properties"]["region"]
        v = 0.0 if values is None else float(values.get(name, 0.0))
        face = "#f2f2f2" if values is None or v <= 0 else cmap(norm(v))
        biggest, area = None, -1.0
        for poly in f["geometry"]["coordinates"]:
            ring = np.asarray(poly[0])
            ax.add_patch(Polygon(ring, closed=True, facecolor=face, edgecolor="white", lw=1.2))
            x, y = ring[:, 0], ring[:, 1]
            a = 0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])
            if abs(a) > area:
                area, biggest = abs(a), (ring, a)
        if label_values and v > 0:
            ring, a = biggest
            x, y = ring[:, 0], ring[:, 1]
            w = x[:-1] * y[1:] - x[1:] * y[:-1]
            cx, cy = np.sum((x[:-1] + x[1:]) * w) / (6 * a), np.sum((y[:-1] + y[1:]) * w) / (6 * a)
            dark = norm(v) > 0.55
            ax.text(cx, cy, f"{v:.1f}", ha="center", va="center", fontsize=18,
                    color="white" if dark else "black")
    ax.set_xlim(6.4, 18.8), ax.set_ylim(35.9, 47.3)
    ax.set_aspect(1 / np.cos(np.deg2rad(41.5)))
    ax.set_xticks([]), ax.set_yticks([])
    ax.xaxis.set_minor_locator(plt.NullLocator()), ax.yaxis.set_minor_locator(plt.NullLocator())
    ax.tick_params(which="both", top=False, right=False, length=0)


def fig_map_regions(d: Data, regions: pd.DataFrame, fig_dir: Path):
    vals = regions["share_of_budget_pct"].drop(NATIONAL)
    cmap, norm = plt.get_cmap("Blues"), colors.Normalize(0, float(vals.max()))
    fig, ax = _axes(small=True)
    _draw_regions(ax, vals, cmap, norm, label_values=True)
    cb = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, shrink=0.8)
    cb.set_label(r"Share of budget / \%")
    nat = regions.loc[NATIONAL, "share_of_budget_pct"]
    ax.set_title(tex(f"{_stamp(d)}; national bodies not shown: {nat:.1f}% of budget"), fontsize=22)
    _save(fig, ax, fig_dir, "map_regions_share")


def _city_table(d: Data, inst: pd.DataFrame) -> pd.DataFrame:
    sited = inst[inst["region"] != NATIONAL].join(
        d.units.drop_duplicates("cf").set_index("cf")[["lat", "lon"]])
    return sited.groupby("city").agg(lat=("lat", "first"), lon=("lon", "first"),
                                     mur=("mur_total", "sum")).sort_values("mur", ascending=False)


def _bubble_size(mur, scale_to) -> np.ndarray:
    return 2.2e3 * np.asarray(mur, dtype=float) / scale_to


def fig_map_cities(d: Data, inst: pd.DataFrame, fig_dir: Path, highlight: Optional[str] = None,
                   n_labels: int = 10):
    city = _city_table(d, inst)
    fig, ax = _axes(small=True)
    _draw_regions(ax, None, None, None, label_values=False)
    sizes = _bubble_size(city["mur"], city["mur"].max())
    colors_ = [RU_COLOR if c == highlight else PI_COLOR for c in city.index]
    ax.scatter(city["lon"], city["lat"], s=sizes, color=colors_, alpha=0.65, edgecolor="white",
               lw=1.0, zorder=3)
    for ref in (2.0, 10.0):
        ax.scatter([], [], s=_bubble_size(ref * 1e6, city["mur"].max()), color=PI_COLOR, alpha=0.65,
                   edgecolor="white", label=rf"{ref:.0f} M EUR")
    ax.legend(loc="lower left", labelspacing=2.2, borderpad=1.2, fontsize=20)
    which = list(range(min(n_labels, len(city))))
    if highlight in city.index and city.index.get_loc(highlight) not in which:
        which.append(city.index.get_loc(highlight))
    _place_labels(fig, ax, city[["lon", "lat"]].to_numpy(), np.sqrt(sizes / np.pi), which,
                  [tex(city.index[i]) for i in which],
                  colors=[RU_COLOR if city.index[i] == highlight else None for i in which])
    ax.set_title(tex(f"Area $\\propto$ MUR funding, {_stamp(d)}"), fontsize=22)
    _save(fig, ax, fig_dir, "map_cities_funding")


def fig_sectors(d: Data, sec: pd.DataFrame, u40: pd.DataFrame, fig_dir: Path):
    """One bar per sector, in percent of the total budget of the parsed sectors: the budget
    available to the sector (outline) and the money funded, split into the projects of
    under-40 PIs (green, on top) and the others (blue)."""
    fig, ax = _axes(small=True)
    x = np.arange(len(sec))
    pct = lambda v: 100 * v / d.budget
    young = u40.loc[sec.index, "money_under40_projects"]
    other = sec["funded"] - young
    ax.bar(x, pct(other), color=PI_COLOR, width=0.7, label="funded, other projects", zorder=2)
    ax.bar(x, pct(young), bottom=pct(other), color=U40_COLOR, width=0.7,
           label=tex("funded, under-40 PIs' projects"), zorder=2)
    ax.bar(x, pct(sec["budget"]), width=0.85, facecolor="none", edgecolor="#555555", lw=2.0,
           label="available", zorder=3)
    ax.set_xticks(x, sec.index, rotation=90)
    ax.xaxis.set_minor_locator(plt.NullLocator())
    ax.set_ylabel(r"Share of total budget / \%")
    ax.set_ylim(0, 1.3 * pct(sec["budget"]).max())
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc="upper right", fontsize=20)
    _save(fig, ax, fig_dir, "sector_budgets")


def fig_ranking(d: Data, sec: pd.DataFrame, fig_dir: Path):
    fig, ax = _axes(small=True)
    x = np.arange(len(sec))
    ax.bar(x, sec["n_funded"], color=PI_COLOR, label="funded")
    ax.bar(x, sec["n_ranked"] - sec["n_funded"], bottom=sec["n_funded"], color=GREY,
           label="ranked, not funded")
    ax.set_xticks(x, sec.index, rotation=90)
    ax.xaxis.set_minor_locator(plt.NullLocator())
    ax.set_ylabel(r"Projects / 1")
    ax.legend(loc="upper right")
    _save(fig, ax, fig_dir, "sector_ranking")


def fig_money(d: Data, fig_dir: Path):
    """Histogram of the MUR contribution per unit, in the style of plot_dist.py: unfilled
    hatched bars, Sturges bins, counts; the dashed line marks the median."""
    xmax = 50 * np.ceil(d.units["mur_contribution"].max() / 1e3 / 50)
    for role, color, name in (("PI", PI_COLOR, "coordinating"), ("RU", RU_COLOR, "partner")):
        v = d.units.loc[d.units["role"] == role, "mur_contribution"].to_numpy() / 1e3
        fig, ax = _axes()
        ax.hist(v, bins=np.linspace(0, xmax, int(np.log2(len(v)) + 1) + 1), histtype="bar",
                rwidth=0.75, hatch="//", fill=False, color=color, edgecolor=color)
        ax.axvline(np.median(v), color="k", lw=1.5, ls="--")
        ax.yaxis.set_major_locator(MaxNLocator(5))
        ax.set_xlabel(r"MUR contribution per unit / k EUR")
        ax.set_ylabel(r"Count")
        ax.set_xlim(0, xmax)
        _save(fig, ax, fig_dir, f"money_per_unit_{name}")


def fig_kinds(d: Data, fig_dir: Path):
    t = _money(d.units, "kind", d.budget).reindex(list(KIND_LABELS)).dropna(subset=["mur_total"])
    fig, ax = _axes(small=True)
    y = np.arange(len(t))[::-1]
    ax.barh(y, t["mur_pi"] / d.budget * 100, color=PI_COLOR, label="as coordinator (PI)")
    ax.barh(y, t["mur_ru"] / d.budget * 100, left=t["mur_pi"] / d.budget * 100,
            color=RU_COLOR, label="as partner (RU)")
    ax.set_yticks(y, [tex(KIND_LABELS[k]) for k in t.index])
    ax.yaxis.set_minor_locator(plt.NullLocator())
    ax.set_xlabel(r"Share of budget / \%")
    ax.legend(loc="lower right")
    _save(fig, ax, fig_dir, "institution_types")


def shared_projects(d: Data) -> Counter:
    """Number of funded projects shared by each pair of nodes, a node being a city or the
    national research bodies taken together (a pair is counted once per project)."""
    place = d.units.assign(node=np.where(d.units["region"] == NATIONAL, NATIONAL, d.units["city"]))
    shared: Counter = Counter()
    for _, g in place.groupby("project_code"):
        for a, b in combinations(sorted(set(g["node"])), 2):
            shared[(a, b)] += 1
    return shared


def fig_collaboration(d: Data, inst: pd.DataFrame, fig_dir: Path, min_shared: int = 8,
                      highlight: Optional[str] = None):
    """Collaboration graph on the map: nodes are cities (area ~ funding), a link joins two
    cities with at least `min_shared` projects in common (width ~ number of projects); the
    links of the highlighted city are drawn whatever their weight. National bodies have no
    place: they are one node in the sea."""
    city = _city_table(d, inst)
    pos = {c: (r["lon"], r["lat"]) for c, r in city.iterrows()}
    pos[NATIONAL] = (11.2, 38.9)
    place = d.units.assign(node=np.where(d.units["region"] == NATIONAL, NATIONAL, d.units["city"]))
    shared = shared_projects(d)
    nat_mur = float(place.loc[place["node"] == NATIONAL, "mur_contribution"].sum())
    fig, ax = _axes(small=True)
    _draw_regions(ax, None, None, None, label_values=False)
    shown = {e: w for e, w in shared.items() if w >= min_shared or highlight in e}
    for (a, b), w in sorted(shown.items(), key=lambda kv: (highlight in kv[0], kv[1])):
        hot = highlight in (a, b)
        ax.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]], color=RU_COLOR if hot else "#4d6d8c",
                lw=(0.8 + 0.35 * w) if hot else 0.15 * w ** 0.9, alpha=0.85 if hot else 0.5,
                solid_capstyle="round", zorder=2.5 if hot else 2)
    names = list(city.index) + [NATIONAL]
    mur = np.concatenate([city["mur"].to_numpy(), [nat_mur]])
    sizes = _bubble_size(mur, city["mur"].max())
    xy = np.array([pos[n] for n in names])
    for k, n in enumerate(names):
        ax.scatter(*xy[k], s=sizes[k], marker="D" if n == NATIONAL else "o", zorder=3,
                   color=RU_COLOR if n == highlight else (GREY if n == NATIONAL else PI_COLOR),
                   alpha=0.8, edgecolor="white", lw=1.0)
    nat = names.index(NATIONAL)
    _place_labels(fig, ax, xy, np.sqrt(sizes / np.pi), [nat], [tex("National bodies")], backing=True)
    note = f"; {highlight} in orange" if highlight else ""
    ax.set_title(tex(f"{min_shared}+ shared projects{note}, {_stamp(d)}"), fontsize=22)
    _save(fig, ax, fig_dir, "collaboration_map")


def fig_region_roles(d: Data, regions: pd.DataFrame, areas: pd.DataFrame, fig_dir: Path):
    """Per macro-area and region, the share of its funding that came from coordinating (PI)
    and from partner (RU) units."""
    reg = regions.drop(NATIONAL)
    reg = reg[reg["mur_total"] > 0].sort_values("pi_share_of_region_pct", ascending=False)
    label = lambda n, r: f"{n} ({int(r['pi_units'] + r['ru_units'])})"
    rows = ([(label(a, r), r) for a, r in areas.iterrows()] + [None]
            + [(label(n.split("/")[0], r), r) for n, r in reg.iterrows()])
    fig, ax = _axes(small=True)
    fig.set_size_inches(12, 12)
    y = np.arange(len(rows))[::-1]
    for yy, row in zip(y, rows):
        if row is None:
            continue
        pi = row[1]["pi_share_of_region_pct"]
        ax.barh(yy, pi, color=PI_COLOR, label="as coordinator (PI)" if yy == y[0] else None)
        ax.barh(yy, 100 - pi, left=pi, color=RU_COLOR, label="as partner (RU)" if yy == y[0] else None)
    ax.set_yticks([yy for yy, r in zip(y, rows) if r is not None],
                  [tex(r[0]) for r in rows if r is not None])
    ax.yaxis.set_minor_locator(plt.NullLocator())
    ax.set_xlabel(r"Share of the region's funding / \%")
    ax.set_xlim(0, 100)
    ax.set_title(r"(number of funded units)", fontsize=20)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.07), ncol=2, fontsize=20)
    _save(fig, ax, fig_dir, "regions_roles")


def fig_breadth(d: Data, inst: pd.DataFrame, fig_dir: Path, highlight: Optional[str] = None,
                n_labels: int = 9):
    """Funding of each institution against the number of sectors in which it has funded units."""
    fig, ax = _axes(small=True)
    rng = np.random.default_rng(0)
    x = inst["n_sectors"].to_numpy() + rng.uniform(-0.18, 0.18, len(inst))
    y = inst["share_of_budget_pct"].to_numpy()
    hot = (inst["city"] == highlight).to_numpy()
    ax.scatter(x[~hot], y[~hot], s=120, color=PI_COLOR, alpha=0.7, edgecolor="white", lw=1.0, zorder=3)
    ax.scatter(x[hot], y[hot], s=160, color=RU_COLOR, alpha=0.9, edgecolor="white", lw=1.0, zorder=4)
    which = sorted(set(range(min(n_labels, len(inst)))) | set(np.flatnonzero(hot)))
    _place_labels(fig, ax, np.column_stack([x, y]), np.full(len(inst), np.sqrt(120 / np.pi)), which,
                  [tex(inst["short_name"].iloc[i]) for i in which], backing=True,
                  colors=[RU_COLOR if hot[i] else None for i in which])
    ax.set_xlabel(r"Sectors with a funded unit / 1")
    ax.set_ylabel(r"Share of total budget / \%")
    ax.set_xlim(0, inst["n_sectors"].max() + 1), ax.set_ylim(0, 1.08 * y.max())
    _save(fig, ax, fig_dir, "institution_breadth")


def fig_neighbours(d: Data, inst: pd.DataFrame, fig_dir: Path, highlight: str, window: int = 5):
    """The highlighted institution and the ones ranked just above and below it by funding."""
    pos = int(np.flatnonzero((inst["city"] == highlight).to_numpy())[0])
    sel = inst.iloc[max(pos - window, 0):pos + window + 1][::-1]
    fig, ax = _axes(small=True)
    y = np.arange(len(sel))
    colors_ = [RU_COLOR if c == highlight else PI_COLOR for c in sel["city"]]
    ax.barh(y, sel["share_of_budget_pct"], color=colors_)
    ax.set_yticks(y, [tex(f"{r} {n}") for r, n in zip(sel["rank"], sel["short_name"])])
    ax.yaxis.set_minor_locator(plt.NullLocator())
    ax.set_xlabel(r"Share of total budget / \%")
    _save(fig, ax, fig_dir, "highlight_neighbours")


def fig_ego_map(d: Data, inst: pd.DataFrame, fig_dir: Path, highlight: str):
    """Map of the cities sharing projects with the highlighted one (width ~ number of projects)."""
    city = _city_table(d, inst)
    pos = {c: (r["lon"], r["lat"]) for c, r in city.iterrows()}
    pos[NATIONAL] = (11.2, 38.9)
    place = d.units.assign(node=np.where(d.units["region"] == NATIONAL, NATIONAL, d.units["city"]))
    mine = set(place.loc[place["city"] == highlight, "project_code"])
    shared: Counter = Counter()
    for _, g in place[place["project_code"].isin(mine)].groupby("project_code"):
        for n in set(g["node"]) - {highlight}:
            shared[n] += 1
    fig, ax = _axes(small=True)
    _draw_regions(ax, None, None, None, label_values=False)
    for n, w in shared.items():
        ax.plot([pos[highlight][0], pos[n][0]], [pos[highlight][1], pos[n][1]], color=RU_COLOR,
                lw=0.8 + 0.9 * w, alpha=0.7, solid_capstyle="round", zorder=2)
    names = [highlight] + list(shared)
    xy = np.array([pos[n] for n in names])
    for k, n in enumerate(names):
        ax.scatter(*xy[k], s=500 if k == 0 else 300, marker="D" if n == NATIONAL else "o", zorder=3,
                   color=RU_COLOR if k == 0 else (GREY if n == NATIONAL else PI_COLOR), alpha=0.9,
                   edgecolor="white", lw=1.0)
    _place_labels(fig, ax, xy, np.full(len(names), np.sqrt(300 / np.pi)), list(range(len(names))),
                  [tex("National bodies" if n == NATIONAL else n) for n in names], fontsize=16,
                  colors=[RU_COLOR if k == 0 else None for k in range(len(names))], backing=True)
    ax.set_title(tex(f"{highlight}: cities sharing projects, {_stamp(d)}"), fontsize=22)
    _save(fig, ax, fig_dir, "highlight_map")


def _ccw(a, b, c) -> bool:
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(s1, s2) -> int:
    a, b, c, d = s1[:2], s1[2:], s2[:2], s2[2:]
    return int(_ccw(a, c, d) != _ccw(b, c, d) and _ccw(a, b, c) != _ccw(a, b, d))


def _segment_hits_box(seg, box) -> int:
    """Whether the segment passes through the box, not counting its two ends."""
    t = np.linspace(0.12, 0.88, 40)
    x, y = seg[0] + t * (seg[2] - seg[0]), seg[1] + t * (seg[3] - seg[1])
    return int(np.any((x > box[0]) & (x < box[2]) & (y > box[1]) & (y < box[3])))


LABEL_DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1), (.7, .7), (-.7, .7), (.7, -.7), (-.7, -.7),
                    (1, .4), (1, -.4), (-1, .4), (-1, -.4), (.4, 1), (-.4, 1), (.4, -1), (-.4, -1))


def _label_with_leaders(fig, ax, xs, ys, labels, diagonal, fontsize=20, r_pts=9, forced=None):
    """Write each label at the nearest of sixteen directions and four distances where it
    overlaps no earlier label, no point and not the diagonal, and its leader line crosses no
    point, label or earlier leader. The densest points are labelled first; `forced` maps a
    label to (dx, dy, distance in points) where the search settles for a bad position."""
    fig.canvas.draw()
    rend, sc = fig.canvas.get_renderer(), fig.dpi / 72.0
    xy = ax.transData.transform(np.c_[xs, ys])
    pts = [(c[0] - r_pts * sc, c[1] - r_pts * sc, c[0] + r_pts * sc, c[1] + r_pts * sc) for c in xy]
    frame = ax.get_window_extent(rend)
    line = ax.transData.transform(np.c_[diagonal, diagonal])
    pad, placed, segs = 3 * sc, [], []
    dens = [sum(np.hypot(*(xy[i] - xy[j])) < 150 * sc for j in range(len(xy))) for i in range(len(xy))]
    for i in sorted(range(len(xy)), key=lambda i: -dens[i]):
        probe = ax.text(0, 0, labels[i], fontsize=fontsize)
        ext = probe.get_window_extent(rend)
        probe.remove()
        w, h = ext.width, ext.height
        dists = (r_pts + 6, 2.5 * r_pts + 8, 4 * r_pts + 12, 6 * r_pts + 16)
        dirs = LABEL_DIRECTIONS
        if forced and labels[i] in forced:
            dirs, dists = (forced[labels[i]][:2],), (forced[labels[i]][2],)
        best = None
        for dist in dists:
            for dx, dy in dirs:
                x0 = xy[i][0] + dx * dist * sc - (0 if dx > 0.3 else w if dx < -0.3 else w / 2)
                y0 = xy[i][1] + dy * dist * sc - (0 if dy > 0.3 else h if dy < -0.3 else h / 2)
                box = (x0 - pad, y0 - pad, x0 + w + pad, y0 + h + pad)
                seg = (xy[i][0], xy[i][1], min(max(xy[i][0], box[0] + pad), box[2] - pad),
                       min(max(xy[i][1], box[1] + pad), box[3] - pad))
                pen = sum(_overlap(box, q) for q in placed) + sum(_overlap(box, q) for q in pts)
                pen += 80 * (sum(_segments_cross(seg, q) for q in segs)
                             + sum(_segment_hits_box(seg, pts[j]) for j in range(len(pts)) if j != i)
                             + sum(_segment_hits_box(seg, q) for q in placed))
                pen += 50 * np.sum((line[:, 0] > box[0]) & (line[:, 0] < box[2])
                                   & (line[:, 1] > box[1]) & (line[:, 1] < box[3]))
                pen += 10 * (w * h - _overlap(box, (frame.x0, frame.y0, frame.x1, frame.y1)))
                if best is None or pen < best[0]:
                    best = (pen, dx, dy, dist, box, seg)
                if pen == 0:
                    break
            if best[0] == 0:
                break
        _, dx, dy, dist, box, seg = best
        placed.append(box), segs.append(seg)
        ha = "left" if dx > 0.3 else "right" if dx < -0.3 else "center"
        va = "bottom" if dy > 0.3 else "top" if dy < -0.3 else "center"
        ax.annotate(labels[i], (xs.iloc[i], ys.iloc[i]), xytext=(dx * dist, dy * dist),
                    textcoords="offset points", ha=ha, va=va, fontsize=fontsize, zorder=6,
                    arrowprops=dict(arrowstyle="-", color="grey", lw=0.8, shrinkA=2, shrinkB=r_pts))


REGION_ABBREVIATIONS = {"Valle d'Aosta/Vallée d'Aoste": "VdA", "Trentino-Alto Adige/Südtirol": "TAA",
                        "Friuli-Venezia Giulia": "FVG", "Emilia-Romagna": "ER"}
CONTEXT_FIGURES = (("population", "Share of resident population / \\%", "population_vs_budget", {}),
                   ("staff", "Share of professors and researchers / \\%", "staff_vs_budget",
                    {"ER": (0.4, -1, 50)}))


def fig_region_context(d: Data, ctx: pd.DataFrame, regions: pd.DataFrame, fig_dir: Path):
    """Share of the budget of each region against its share of the population and of the
    professors and researchers, on logarithmic axes with the line of equal shares. Regions
    that received nothing cannot be drawn and are named in the title."""
    lo, hi, ticks = 0.15, 25, [0.2, 0.5, 1, 2, 5, 10, 20]
    drawn = ctx[ctx["budget_share_pct"] > 0]
    absent = ctx.index[ctx["budget_share_pct"] <= 0]
    nat = float(regions.loc[NATIONAL, "share_of_budget_pct"])
    for column, xlabel, name, forced in CONTEXT_FIGURES:
        xs, ys = drawn[f"{column}_share_pct"], drawn["budget_share_pct"]
        fig, ax = _axes(tick=30)
        for label in (ax.xaxis.label, ax.yaxis.label):
            label.set_fontsize(34)
        diagonal = np.geomspace(lo, hi, 400)
        ax.plot([lo, hi], [lo, hi], color="grey", lw=1.5, ls="--", zorder=1)
        ax.scatter(xs, ys, s=200, color="#1f4e9c", zorder=3)
        ax.set_xscale("log"), ax.set_yscale("log")
        ax.set_xlim(lo, hi), ax.set_ylim(lo, hi)
        for axis in (ax.xaxis, ax.yaxis):
            axis.set_ticks(ticks), axis.set_ticklabels([str(t) for t in ticks])
            axis.set_minor_locator(plt.NullLocator())
        ax.set_xlabel(xlabel), ax.set_ylabel(r"Share of budget / \%")
        gone = ", ".join(r.split("/")[0] for r in absent)
        ax.set_title(tex(f"{_stamp(d)}; national bodies not shown ({nat:.1f}% of budget); {gone} (0%) not shown"), fontsize=18)
        _label_with_leaders(fig, ax, xs, ys, [tex(REGION_ABBREVIATIONS.get(r, r)) for r in xs.index],
                            diagonal, forced=forced)
        _save(fig, ax, fig_dir, name)


def gsd_tables(d: Data, cache: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """The GSD 2024 of the unit leaders found in the MUR directory (see gsd.py), as
    aggregates: the outcome of the lookup, the leaders and the staff by CUN area (the first
    two digits of the GSD code are the area), the leaders by GSD, and the leaders of each
    ERC macro-area by CUN area. Only leaders found at the university of their unit count."""
    u = d.units[["sector", "role", "name", "institution", "mur_contribution"]].merge(
        cache[["name", "institution", "status", "gsd"]], on=["name", "institution"], how="left")
    u["status"] = u["status"].fillna("not_looked_up")
    u["group"] = u["role"].map({"PI": "PI", "RU": "Partner-unit leaders"})
    u["macro"] = u["sector"].str[:2]
    status = u.pivot_table(index="group", columns="status", values="name", aggfunc="count", fill_value=0)
    status["leaders"] = status.sum(axis=1)
    found = u[u["status"] == "found"].copy()
    found["area"] = found["gsd"].str[:2]
    staff = pd.read_csv(DATA / "staff_by_area.csv", index_col=0, dtype={"code": str})
    staff.index = staff.index.map(lambda c: f"{int(c):02d}")
    staff["staff"] = staff["professors"] + staff["researchers"]
    areas = staff[["area", "staff"]].copy()
    for g in ("PI", "Partner-unit leaders"):
        areas[g] = found[found["group"] == g].groupby("area").size().reindex(areas.index).fillna(0).astype(int)
    areas["leaders"] = areas["PI"] + areas["Partner-unit leaders"]
    areas["mur_total"] = found.groupby("area")["mur_contribution"].sum().reindex(areas.index).fillna(0.0)
    areas["budget_share_pct"] = 100 * areas["mur_total"] / d.budget
    areas["leaders_share_pct"] = 100 * areas["leaders"] / areas["leaders"].sum()
    areas["staff_share_pct"] = 100 * areas["staff"] / areas["staff"].sum()
    areas["leaders_per_1000_staff"] = 1000 * areas["leaders"] / areas["staff"]
    codes = (found.groupby(["gsd", "group"]).size().unstack(fill_value=0)
             .reindex(columns=["PI", "Partner-unit leaders"], fill_value=0))
    codes["leaders"] = codes.sum(axis=1)
    codes = codes.sort_values(["leaders", "PI"], ascending=False)
    macro = found.pivot_table(index="area", columns="macro", values="name", aggfunc="count", fill_value=0)
    macro = macro.reindex(columns=["PE", "LS", "SH"], fill_value=0).reindex(areas.index, fill_value=0)
    return dict(status=status, areas=areas, codes=codes, macro=macro)


CAREER_LEVELS = {"Ordinario": "Full professor (PO)", "Associato": "Associate professor (PA)",
                 "Ricercatori a tempo determinato L.79/2022": "Fixed-term (RTD, L. 79/2022)",
                 "Ricercatori a tempo determinato L.240/10 tipo B": "Fixed-term (RTD-B)",
                 "Ricercatori a tempo determinato L.240/10 tipo A": "Fixed-term (RTD-A)",
                 "Ricercatore": "Permanent researcher"}


def career_tables(d: Data, cache: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """The career level of the unit leaders found in the MUR directory (see gsd.py): per
    level, the PIs and the partner-unit leaders, their ERC macro-areas, and the MUR money of
    their units. Only leaders found at the university of their unit count."""
    u = d.units[["sector", "role", "name", "institution", "mur_contribution"]].merge(
        cache[["name", "institution", "status", "role"]].rename(columns={"role": "career"}),
        on=["name", "institution"], how="left")
    found = u[u["status"] == "found"].copy()
    found["level"] = found["career"].map(CAREER_LEVELS)
    found["macro"] = found["sector"].str[:2]
    levels = list(CAREER_LEVELS.values())
    t = pd.DataFrame(index=levels)
    for role, col in (("PI", "PI"), ("RU", "Partner-unit leaders")):
        t[col] = found[found["role"] == role].groupby("level").size().reindex(levels).fillna(0).astype(int)
    t["leaders"] = t["PI"] + t["Partner-unit leaders"]
    for m in ("PE", "LS", "SH"):
        t[m] = found[found["macro"] == m].groupby("level").size().reindex(levels).fillna(0).astype(int)
    t["leaders_share_pct"] = 100 * t["leaders"] / t["leaders"].sum()
    t["mur_total"] = found.groupby("level")["mur_contribution"].sum().reindex(levels).fillna(0.0)
    t["budget_share_pct"] = 100 * t["mur_total"] / d.budget
    t["mean_per_unit"] = t["mur_total"] / t["leaders"].where(t["leaders"] > 0)
    t.index.name = "level"
    # the same leaders by CUN area and level, against the staff of the area (2025)
    staff = pd.read_csv(DATA / "staff_by_area_level.csv", index_col=0, dtype={"code": str})
    staff.index = staff.index.map(lambda c: f"{int(c):02d}")
    found["area"] = cache.set_index(["name", "institution"])["gsd"].reindex(
        pd.MultiIndex.from_frame(found[["name", "institution"]])).str[:2].to_numpy()
    found["short"] = found["career"].map({"Ordinario": "po", "Associato": "pa", "Ricercatore": "ru"}).fillna("rtd")
    lead = found.pivot_table(index="area", columns="short", values="name", aggfunc="count", fill_value=0)
    lead = lead.reindex(index=staff.index, columns=["po", "pa", "rtd", "ru"], fill_value=0)
    money = found.pivot_table(index="area", columns="short", values="mur_contribution", aggfunc="sum", fill_value=0.0)
    money = money.reindex(index=staff.index, columns=["po", "pa", "rtd", "ru"], fill_value=0.0)
    a = pd.concat([staff[["area"]], staff[["po", "pa", "rtd", "ru"]].add_prefix("staff_"),
                   lead.add_prefix("leaders_"), money.add_prefix("money_")], axis=1)
    a.loc["All"] = [""] + [a[c].sum() for c in a.columns[1:]]
    for g in ("staff", "leaders", "money"):
        tot = a[[f"{g}_{k}" for k in ("po", "pa", "rtd", "ru")]].sum(axis=1)
        for k in ("po", "pa", "rtd", "ru"):
            a[f"{g}_{k}_pct"] = 100 * a[f"{g}_{k}"] / tot
    for k in ("po", "pa", "rtd"):
        a[f"leaders_per_1000_{k}"] = 1000 * a[f"leaders_{k}"] / a[f"staff_{k}"]
    a.index.name = "code"
    return dict(levels=t, areas=a)


def fig_career(d: Data, t: pd.DataFrame, fig_dir: Path):
    """Per career level, the share of the funded PIs and of the partner-unit leaders found
    in the MUR directory."""
    t = t[t["leaders"] > 0].iloc[::-1]
    fig, ax = _axes(small=True)
    fig.set_size_inches(14, 9)
    y = np.arange(len(t))
    for off, col, color in ((0.2, "PI", PI_COLOR), (-0.2, "Partner-unit leaders", RU_COLOR)):
        ax.barh(y + off, 100 * t[col] / t[col].sum(), height=0.4, color=color,
                label=f"{col} ({int(t[col].sum())})")
    ax.set_yticks(y, [tex(l) for l in t.index])
    ax.yaxis.set_minor_locator(plt.NullLocator())
    ax.set_xlabel(r"Share of the leaders / \%")
    ax.legend(title=tex(f"{_stamp(d)}; leaders at a university"), loc="lower center",
              bbox_to_anchor=(0.5, 1.01), ncol=2, fontsize=20, title_fontsize=20)
    _save(fig, ax, fig_dir, "career_levels")


def project_tables(d: Data, cache: pd.DataFrame, n_shuffle: int = 2000, seed: int = 0) -> Dict[str, pd.DataFrame]:
    """The funded projects by number of units, and by number of distinct GSDs among the
    leaders of their units. The GSD counts use only the projects whose leaders were all found
    in the MUR directory (see gsd.py). `random` repeats the count after assigning the leaders of
    those projects to projects at random within the sector, keeping the number of units of
    each project (mean over `n_shuffle` assignments)."""
    u = d.units[["sector", "project_code", "role", "name", "institution", "mur_contribution"]].merge(
        cache[["name", "institution", "status", "gsd"]], on=["name", "institution"], how="left")
    u["found"] = u["status"] == "found"
    u["macro"] = u["sector"].str[:2]
    proj = u.groupby("project_code").agg(units=("name", "size"), macro=("macro", "first"), sector=("sector", "first"),
                                         money=("mur_contribution", "sum"), complete=("found", "all"))
    size = pd.DataFrame(index=sorted(proj["units"].unique()))
    size["projects"] = proj.groupby("units").size()
    size["projects_pct"] = 100 * size["projects"] / len(proj)
    for m in ("PE", "LS", "SH"):
        size[m] = proj[proj["macro"] == m].groupby("units").size().reindex(size.index).fillna(0).astype(int)
    size["mur_total"] = proj.groupby("units")["money"].sum()
    size["mur_per_project"] = size["mur_total"] / size["projects"]
    size["mur_per_unit"] = size["mur_total"] / (size["projects"] * size.index)
    size["units_pct"] = 100 * size["projects"] * size.index / len(u)
    size.index.name = "units"

    comp = u[u["project_code"].isin(proj.index[proj["complete"]])].copy()
    comp["area"] = comp["gsd"].str[:2]
    codes = comp.groupby("project_code")["gsd"].apply(list)
    areas = comp.groupby("project_code")["area"].apply(list)
    n_units = proj.loc[codes.index, "units"]
    sectors = proj.loc[codes.index, "sector"]
    rng = np.random.default_rng(seed)
    kmax = int(n_units.max())
    rows = {}
    for label, lists in (("gsd", codes), ("area", areas)):
        obs = lists.map(lambda v: len(set(v)))
        rnd = np.zeros(kmax)
        mean_rnd = 0.0
        for _, idx in sectors.groupby(sectors):
            pool = np.array([x for p in idx.index for x in lists[p]])
            sizes = [len(lists[p]) for p in idx.index]
            cuts = np.cumsum(sizes)[:-1]
            counts = np.array([[len(set(g)) for g in np.split(rng.permutation(pool), cuts)] for _ in range(n_shuffle)])
            rnd += np.array([(counts == k).sum() for k in range(1, kmax + 1)]) / n_shuffle
            mean_rnd += counts.mean(axis=0).sum()
        dist = pd.DataFrame(index=range(1, kmax + 1))
        for n in sorted(n_units.unique()):
            dist[f"{n} units"] = obs[n_units == n].value_counts().reindex(dist.index).fillna(0).astype(int)
        dist["projects"] = obs.value_counts().reindex(dist.index).fillna(0).astype(int)
        dist["projects_pct"] = 100 * dist["projects"] / len(obs)
        dist["random_pct"] = 100 * rnd / len(obs)
        dist.index.name = f"distinct_{label}"
        rows[f"distinct_{label}"] = dist
        rows[f"mean_{label}"] = pd.DataFrame(dict(projects=[len(obs)], observed=[obs.mean()], random=[mean_rnd / len(obs)],
                                                  per_unit=[(obs / n_units).mean()]), index=[label])
    return dict(size=size, distinct_gsd=rows["distinct_gsd"], distinct_area=rows["distinct_area"],
                means=pd.concat([rows["mean_gsd"], rows["mean_area"]]))


def fig_distinct_gsd(d: Data, dist: pd.DataFrame, n_proj: int, fig_dir: Path):
    """Share of the projects with k distinct GSDs among the leaders, against the same share
    when the leaders are assigned to projects at random within the sector."""
    fig, ax = _axes(small=True)
    x = np.arange(len(dist))
    ax.bar(x - 0.2, dist["projects_pct"], width=0.4, color=PI_COLOR, label=f"funded projects ({n_proj})")
    ax.bar(x + 0.2, dist["random_pct"], width=0.4, color=GREY, label="same leaders, shuffled between the projects of their sector")
    ax.set_xticks(x, [str(k) for k in dist.index])
    ax.xaxis.set_minor_locator(plt.NullLocator())
    ax.set_xlabel("Distinct GSDs among the leaders of the project"), ax.set_ylabel(r"Share of the projects / \%")
    ax.legend(title=tex(f"{_stamp(d)}; projects whose leaders were all found"), loc="lower center",
              bbox_to_anchor=(0.5, 1.01), ncol=1, fontsize=20, title_fontsize=20)
    _save(fig, ax, fig_dir, "distinct_gsd")


CUN_AREAS = {"01": "Mathematics, computer science", "02": "Physics", "03": "Chemistry", "04": "Earth sciences",
             "05": "Biology", "06": "Medicine", "07": "Agriculture, veterinary", "08": "Civil eng., architecture",
             "09": "Industrial, information eng.", "10": "Antiquity, philology, arts", "11": "History, philosophy, psychology",
             "12": "Law", "13": "Economics, statistics", "14": "Political, social sciences"}


def fig_gsd_areas(d: Data, areas: pd.DataFrame, n_found: int, fig_dir: Path):
    """Per CUN area, the share of the funded unit leaders whose GSD was found and the share
    of the professors and researchers of the Italian universities."""
    t = areas.sort_values("leaders_share_pct")
    fig, ax = _axes(small=True)
    fig.set_size_inches(14, 12)
    y = np.arange(len(t))
    ax.barh(y + 0.2, t["leaders_share_pct"], height=0.4, color=PI_COLOR, label=f"funded unit leaders ({n_found})")
    ax.barh(y - 0.2, t["staff_share_pct"], height=0.4, color=GREY, label="professors and researchers (2025)")
    ax.set_yticks(y, [f"{c} {tex(CUN_AREAS.get(c, a))}" for c, a in zip(t.index, t["area"])])
    ax.yaxis.set_minor_locator(plt.NullLocator())
    ax.set_xlim(0, 1.1 * float(max(t["leaders_share_pct"].max(), t["staff_share_pct"].max())))
    ax.set_xlabel(r"Share of the total / \%")
    ax.legend(title=tex(f"{_stamp(d)}; leaders at a university, GSD 2024 area (CUN)"), loc="lower center",
              bbox_to_anchor=(0.5, 1.01), ncol=1, fontsize=20, title_fontsize=20)
    _save(fig, ax, fig_dir, "gsd_areas")


def fig_gsd_staff_budget(d: Data, areas: pd.DataFrame, fig_dir: Path):
    """Per CUN area, the share of the total budget received by the units whose leader's GSD
    is in the area, against the share of the professors and researchers of the area, on
    logarithmic axes with the line of equal shares. The points are labelled with the CUN area
    number (the names are in the table of the report)."""
    lo, hi, ticks = 0.15, 25, [0.2, 0.5, 1, 2, 5, 10, 20]
    xs, ys = areas["staff_share_pct"], areas["budget_share_pct"]
    fig, ax = _axes(tick=30)
    for label in (ax.xaxis.label, ax.yaxis.label):
        label.set_fontsize(34)
    ax.plot([lo, hi], [lo, hi], color="grey", lw=1.5, ls="--", zorder=1)
    ax.scatter(xs, ys, s=200, color="#1f4e9c", zorder=3)
    ax.set_xscale("log"), ax.set_yscale("log")
    ax.set_xlim(lo, hi), ax.set_ylim(lo, hi)
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_ticks(ticks), axis.set_ticklabels([str(t) for t in ticks])
        axis.set_minor_locator(plt.NullLocator())
    ax.set_xlabel(r"Share of professors and researchers / \%"), ax.set_ylabel(r"Share of budget / \%")
    ax.set_title(tex(f"{_stamp(d)}; units whose leader's GSD was found, by CUN area"), fontsize=18)
    _label_with_leaders(fig, ax, xs, ys, [str(c) for c in areas.index],
                        np.geomspace(lo, hi, 400))
    _save(fig, ax, fig_dir, "gsd_staff_vs_budget")


def fig_gender(d: Data, gt: pd.DataFrame, fig_dir: Path):
    styles = {"PI, funded": (PI_COLOR, "o"), "Partner-unit leaders, funded": (RU_COLOR, "^")}
    macros = ["PE", "LS", "SH", "All"]
    fig, ax = _axes(small=True)
    for k, (label, (color, marker)) in enumerate(styles.items()):
        sub = gt[gt["group"] == label].set_index("macro").loc[macros]
        x = np.arange(len(macros)) + (k - 1) * 0.2
        ax.errorbar(x, 100 * sub["female_share"],
                    yerr=100 * np.vstack([sub["female_share"] - sub["low"],
                                          sub["high"] - sub["female_share"]]),
                    fmt=marker, color=color, ms=12, capsize=6, lw=2.5, label=tex(label))
    ax.set_xticks(range(len(macros)), macros)
    ax.xaxis.set_minor_locator(plt.NullLocator())
    ax.set_ylabel(r"Female share / \%")
    ax.set_ylim(0, 100)
    ax.axhline(50, color=GREY, lw=1.2, ls="--")
    ax.legend(loc="lower left", fontsize=20)
    _save(fig, ax, fig_dir, "gender")


def update_history(out_dir: Path, d: Data, inst: pd.DataFrame, regions: pd.DataFrame) -> bool:
    """Append the shares of institutions and regions to prin_out/history.csv when the set of
    parsed sectors differs from the last entry; return whether rows were added. The file lets
    the numbers be followed as sectors are published."""
    path = out_dir / "history.csv"
    sectors = " ".join(d.sectors)
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(
        columns=["date", "n_sectors", "sectors", "kind", "key", "share_of_budget_pct"])
    if len(old) and old["sectors"].iloc[-1] == sectors:
        return False
    stamp = datetime.date.today().isoformat()
    new = pd.concat([
        pd.DataFrame({"kind": "institution", "key": inst["short_name"].to_numpy(),
                      "share_of_budget_pct": inst["share_of_budget_pct"].to_numpy()}),
        pd.DataFrame({"kind": "region", "key": regions.index.to_numpy(),
                      "share_of_budget_pct": regions["share_of_budget_pct"].to_numpy()})])
    new.insert(0, "sectors", sectors)
    new.insert(0, "n_sectors", len(d.sectors))
    new.insert(0, "date", stamp)
    pd.concat([old, new]).to_csv(path, index=False, encoding="utf-8-sig")
    return True


# ------------------------------------------------------------------ main

def run(out_dir: Path, use_latex: bool = True, highlight: Optional[str] = None) -> Dict[str, float]:
    d = load(out_dir)
    tab_dir, fig_dir = out_dir / "analysis", out_dir / "figures"
    tab_dir.mkdir(exist_ok=True), fig_dir.mkdir(exist_ok=True)
    inst, regions, sec = institution_table(d), region_table(d), sector_table(d)
    kinds, gt = _money(d.units, "kind", d.budget), gender_table(d)
    u40, areas, per_sector = under40_table(d), macro_area_table(d), institution_sector_table(d)
    ctx = region_context_table(regions)
    inst.to_csv(tab_dir / "institutions.csv", encoding="utf-8-sig")
    regions.to_csv(tab_dir / "regions.csv", encoding="utf-8-sig")
    ctx.to_csv(tab_dir / "regions_context.csv", encoding="utf-8-sig")
    sec.to_csv(tab_dir / "sectors.csv", encoding="utf-8-sig")
    kinds.to_csv(tab_dir / "institution_types.csv", encoding="utf-8-sig")
    gt.to_csv(tab_dir / "gender.csv", index=False, encoding="utf-8-sig")
    u40.to_csv(tab_dir / "under40.csv", encoding="utf-8-sig")
    areas.to_csv(tab_dir / "macro_areas.csv", encoding="utf-8-sig")
    per_sector.to_csv(tab_dir / "institution_sectors.csv", index=False, encoding="utf-8-sig")
    global USE_LATEX
    USE_LATEX = use_latex
    fig_institutions(d, inst, fig_dir)
    fig_budget_drop(d, inst, fig_dir)
    fig_map_regions(d, regions, fig_dir)
    fig_map_cities(d, inst, fig_dir, highlight)
    fig_sectors(d, sec, u40, fig_dir)
    fig_ranking(d, sec, fig_dir)
    fig_money(d, fig_dir)
    fig_kinds(d, fig_dir)
    fig_collaboration(d, inst, fig_dir, highlight=highlight)
    fig_gender(d, gt, fig_dir)
    fig_region_context(d, ctx, regions, fig_dir)
    if gsd.CACHE.exists():
        gt_gsd = gsd_tables(d, gsd.load_cache())
        for name, t in gt_gsd.items():
            t.to_csv(tab_dir / f"gsd_{name}.csv", encoding="utf-8-sig")
        fig_gsd_areas(d, gt_gsd["areas"], int(gt_gsd["areas"]["leaders"].sum()), fig_dir)
        fig_gsd_staff_budget(d, gt_gsd["areas"], fig_dir)
        gt_career = career_tables(d, gsd.load_cache())
        for name, t in gt_career.items():
            t.to_csv(tab_dir / f"career_{name}.csv", encoding="utf-8-sig")
        fig_career(d, gt_career["levels"], fig_dir)
        gt_proj = project_tables(d, gsd.load_cache())
        for name, t in gt_proj.items():
            t.to_csv(tab_dir / f"project_{name}.csv", encoding="utf-8-sig")
        fig_distinct_gsd(d, gt_proj["distinct_gsd"], int(gt_proj["means"].loc["gsd", "projects"]), fig_dir)
    fig_region_roles(d, regions, areas, fig_dir)
    fig_breadth(d, inst, fig_dir, highlight)
    if highlight:
        fig_neighbours(d, inst, fig_dir, highlight)
        fig_ego_map(d, inst, fig_dir, highlight)
    summary = dict(n_sectors=len(d.sectors), sectors=d.sectors, budget=d.budget,
                   funded=float(d.units["mur_contribution"].sum()),
                   n_projects=int(d.units["project_code"].nunique()),
                   n_units=int(len(d.units)), n_ranked=int(len(d.ranking)),
                   **concentration(inst))
    if highlight:
        summary["highlight"] = {
            r["short_name"]: dict(share_of_budget_pct=float(r["share_of_budget_pct"]), rank=int(r["rank"]),
                                  rank_in_type=int(r["rank_in_type"]), type=r["kind"],
                                  n_institutions_of_type=int((inst["kind"] == r["kind"]).sum()),
                                  projects=int(r["projects"]), pi_units=int(r["pi_units"]),
                                  ru_units=int(r["ru_units"]), n_sectors=int(r["n_sectors"]),
                                  mur_total=float(r["mur_total"]))
            for _, r in inst[inst["city"] == highlight].iterrows()}
    (tab_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    update_history(out_dir, d, inst, regions)
    return summary


def main(argv=None) -> int:
    ap = arg.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="prin_out", help="directory written by prin_extract.py")
    ap.add_argument("--highlight", default="Siena", help="city to colour on the maps (default Siena)")
    ap.add_argument("--no-latex", action="store_true", help="render text with mathtext, not LaTeX")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    s = run(Path(a.out), use_latex=not a.no_latex, highlight=a.highlight)
    print(f"{s['n_projects']} projects, {s['funded'] / 1e6:.1f} of {s['budget'] / 1e6:.1f} M EUR "
          f"in {s['n_sectors']} sectors; Gini {s['gini']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
