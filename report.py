"""report.py - LaTeX report of the PRIN 2026 funded projects.

Writes report/report.tex from the tables of analysis.py and compiles it with pdflatex.
Every number in the text is computed here from prin_out/; each analysis has a
"Purpose" (why it was made) and a "Result" (what the data show), and nothing else.
Figures are the PDFs in prin_out/figures/.
"""
import argparse as arg
import datetime
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy import stats

import analysis as an
import decrees
from analysis import NATIONAL, tex

log = logging.getLogger(__name__)

PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[margin=2.2cm]{geometry}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{float}
\usepackage{siunitx}
\usepackage[colorlinks=true,linkcolor=black,urlcolor=blue]{hyperref}
\usepackage[inline]{enumitem}
\sisetup{range-phrase=--}
\setlength{\parindent}{0pt}
\setlength{\parskip}{4pt}
\emergencystretch=3em
"""


def eur(x: float, digits: int = 1) -> str:
    return f"{x / 1e6:.{digits}f}~M~EUR"


def pct(x: float, digits: int = 1) -> str:
    return rf"{x:.{digits}f}\%"


def join(items: List[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def table(header: List[str], rows: List[List[str]], colspec: str, size: str = "",
          total: Optional[List[str]] = None, note: str = "") -> str:
    """A booktabs table; `total`, if given, is a last row set off by a midrule; `note` is
    set in a small row under the bottom rule, inside the table."""
    lines = [r"\begin{table}[H]", r"\centering", size, rf"\begin{{tabular}}{{{colspec}}}", r"\toprule",
             " & ".join(header) + r" \\", r"\midrule"]
    lines += [" & ".join(r) + r" \\" for r in rows]
    if total is not None:
        lines += [r"\midrule", " & ".join(total) + r" \\"]
    lines += [r"\bottomrule"]
    if note:
        lines += [rf"\multicolumn{{{len(header)}}}{{l}}{{\footnotesize {note}}} \\"]
    lines += [r"\end{tabular}", r"\end{table}"]
    return "\n".join(x for x in lines if x)


def figure(name: str, caption: str, width: float = 0.8) -> str:
    return "\n".join([r"\begin{figure}[H]", r"\centering",
                      rf"\includegraphics[width={width}\textwidth]{{../prin_out/figures/{name}.pdf}}",
                      rf"\caption{{{caption}}}", r"\end{figure}"])


def section(title: str, purpose: str, result: str, body: str, level: str = "subsubsection") -> str:
    return "\n".join([rf"\{level}{{{title}}}", rf"\textbf{{Purpose.}} {purpose}", "",
                      rf"\textbf{{Result.}} {result}", "", body, ""])


def build(out_dir: Path, highlight: Optional[str]) -> str:
    d = an.load(out_dir)
    manifest = decrees.load_manifest(out_dir / "decrees.json")
    inst, regions, areas = an.institution_table(d), an.region_table(d), an.macro_area_table(d)
    sec, u40, gt = an.sector_table(d), an.under40_table(d), an.gender_table(d)
    per_sector = an.institution_sector_table(d)
    units, B = d.units, d.budget
    funded = float(units["mur_contribution"].sum())
    n_proj = int(units["project_code"].nunique())
    missing = [s for s in decrees.ALL_SECTORS if s not in d.sectors]
    parts: List[str] = []

    # ---------------------------------------------------------------- scope
    names = pd.read_csv(an.DATA / "given_names.csv")
    basis = names["basis"].value_counts()
    parts.append(rf"""\section{{Scope}}
The report covers {len(d.sectors)} of the {len(decrees.ALL_SECTORS)} ERC sectors of the PRIN 2026 call,
those for which the MUR had published the decree, the ranking (Tabella A) and the funded projects
(Tabella B) when the data were extracted: {join(d.sectors)}. Not yet published: {join(missing)}.
Every figure and number refers to these {len(d.sectors)} sectors only.

\subsection{{Definitions}}
\begin{{itemize}}
\item \textbf{{Budget}}: the sum, over the {len(d.sectors)} sectors, of the funds that the decrees make
available to each sector (under-40 pool plus ordinary pool): {eur(B, 2)}.
\item \textbf{{Share}}: MUR contribution received by an institution, region or other group, divided by the budget, in percent.
\item \textbf{{PI}} and \textbf{{RU}}: the coordinating unit of a project and its partner units; the money of a project is the sum of the MUR contributions of its units.
\item \textbf{{Under-40 PI}}: a principal investigator printed in green in the MUR tables.
\end{{itemize}}

\subsection{{Data}}
{n_proj} funded projects and {len(units)} funded units ({int((units['role'] == 'PI').sum())} PI, {int((units['role'] == 'RU').sum())} RU) from Tabella B, receiving {eur(funded, 2)} ({pct(100 * funded / B, 2)} of the budget).
Tabella A lists {len(d.ranking)} ranked projects, {int(d.ranking['funded'].sum())} of them funded; it contains the projects the evaluation committees judged fundable, not all the projects submitted.
Gender is inferred from the first given name with a table of {len(names)} names ({int(basis.get('curated', 0))} assigned by hand, {int(basis.get('ending', 0))} by the Italian ending rule); it is a binary inference used only in aggregate.
City, region and type of each institution come from a hand-checked table of {inst.shape[0]} institutions.

\subsubsection*{{Sources}}
\begin{{itemize}}
\item Decrees, Tabella A (ranking) and Tabella B (funded projects): the MUR \href{{https://prin.mur.gov.it/Pages/Index/301}}{{PRIN 2026 page}} and the pages and files linked in the table of decrees below.
\item Regional boundaries: ISTAT administrative boundaries, simplified, from the repository \href{{https://github.com/openpolis/geojson-italy}}{{geojson-italy}} of openpolis.
\item Resident population by region, 1 January 2026 (ISTAT figures): the \href{{https://en.wikipedia.org/wiki/List_of_Italian_regions_by_population}}{{table of Italian regions by population}}, which cites \href{{https://www.tuttitalia.it}}{{tuttitalia.it}}.
\item Professors, researchers and research fellows of the universities by region, 2024: \href{{https://dati-ustat.mur.gov.it/dataset/263a4704-a5cb-46c3-9062-4f977c9fd3e7/resource/46015a92-abe3-411c-af07-2532164cab59/download/personale_xgenere.csv}}{{personale\_xgenere.csv}}, dataset \href{{https://dati-ustat.mur.gov.it/dataset/personale-universitario}}{{2020--2024 Personale universitario}} of the open data of the MUR statistical office (USTAT). The staff is all the university staff in post, not those who applied to the programme, for which no data are available.
\item Professors and researchers by CUN scientific-disciplinary area, 2024: \href{{https://dati-ustat.mur.gov.it/dataset/263a4704-a5cb-46c3-9062-4f977c9fd3e7/resource/a966dec6-b9a4-481c-92d2-485e799a9c1a/download/personale_docentedi-ruoloricercatorexareasd.csv}}{{personale\_docentedi-ruoloricercatorexareasd.csv}}, same dataset; the same file by qualification (PO, PA, RTD, RU) gives data/staff_by_area_level.csv.
\item Disciplinary group (GSD 2024) and career level of the unit leaders: looked up by name in the staff search of the MUR portal \href{{https://cercauniversita.mur.gov.it}}{{Cerca Universit\`a}} (see \texttt{{gsd.py}}); only aggregates are kept in the repository.
\end{{itemize}}
""")

    parts.append(r"\section{Analyses}")
    parts.append(r"\subsection{Budget and its distribution}")

    # ------------------------------------------------------------- 2.1 sectors
    lo, hi = sec["used_pct"].idxmin(), sec["used_pct"].idxmax()
    below = u40[u40["funded_below_ordinary_cut"] > 0]
    over_pool = int((u40["money_under40_projects"] > u40["pool"]).sum())
    parts.append(section(
        "Budget and funded money per sector",
        "To compare, sector by sector, the money funded with the budget the decrees make available, and to separate the money that went to projects whose PI is under 40.",
        rf"The budget is {eur(B, 2)} and {eur(funded, 2)} ({pct(100 * funded / B)}) was funded. Per sector, the funded money is between {pct(sec.loc[lo, 'used_pct'])} of the budget of {lo} and {pct(sec.loc[hi, 'used_pct'])} of the budget of {hi}. "
        rf"{int(u40['funded_under40'].sum())} of the {n_proj} funded projects have an under-40 PI; they received {eur(u40['money_under40_projects'].sum(), 2)} ({pct(100 * u40['money_under40_projects'].sum() / funded)} of the funded money). The under-40 pools of the {len(d.sectors)} sectors add up to {eur(u40['pool'].sum(), 2)}; in {over_pool} sectors the money of the under-40 PIs' projects is larger than the sector's pool. "
        rf"{int(u40['funded_below_ordinary_cut'].sum())} funded under-40 projects rank below the best unfunded project of an over-40 PI ({join(list(below.index))}).",
        figure("sector_budgets", rf"Per sector, in percent of the total budget: budget available (outline) and funded money, split into projects of under-40 PIs (green) and the others (blue). {len(d.sectors)} of 28 sectors.", 0.85)))

    # -------------------------------------------------------------- 2.3 types
    kinds = an._money(units, "kind", B).reindex(list(an.KIND_LABELS)).dropna(subset=["mur_total"])
    n_by_kind = inst["kind"].value_counts()
    rows = [[tex(an.KIND_LABELS[k]), str(int(n_by_kind[k])), str(int(r["projects"])),
             f"{r['share_of_budget_pct']:.2f}", f"{100 * r['mur_pi'] / B:.2f}", f"{100 * r['mur_ru'] / B:.2f}"]
            for k, r in kinds.iterrows()]
    parts.append(section(
        "Institution types",
        "To show how the budget is divided among types of institution (public and private universities, telematic universities, advanced schools, research bodies).",
        rf"Public universities received {pct(kinds.loc['public_university', 'share_of_budget_pct'])} of the budget, national research bodies {pct(kinds.loc['national_research_body', 'share_of_budget_pct'])}, private universities {pct(kinds.loc['private_university', 'share_of_budget_pct'])}, advanced schools {pct(kinds.loc['school', 'share_of_budget_pct'])}, telematic universities {pct(kinds.loc['telematic', 'share_of_budget_pct'])}. The table gives the number of institutions and the shares by role.",
        table(["Type", "Institutions", "Projects", "Share (\\%)", "as PI (\\%)", "as RU (\\%)"], rows, "lrrrrr",
              total=["Total", str(int(n_by_kind[kinds.index].sum())), str(n_proj),
                     f"{kinds['share_of_budget_pct'].sum():.2f}", f"{100 * kinds['mur_pi'].sum() / B:.2f}",
                     f"{100 * kinds['mur_ru'].sum() / B:.2f}"])
        + "\n" + figure("institution_types", "Share of the total budget by institution type, as coordinator (PI) and as partner (RU).", 0.7)))

    # ------------------------------------------------------------- 2.4 money
    def quart(v):
        q = np.percentile(v / 1e3, [25, 50, 75])
        return q, v.min() / 1e3, v.max() / 1e3
    pi_v = units.loc[units["role"] == "PI", "mur_contribution"].to_numpy()
    ru_v = units.loc[units["role"] == "RU", "mur_contribution"].to_numpy()
    (qp, mnp, mxp), (qr, mnr, mxr) = quart(pi_v), quart(ru_v)
    parts.append(section(
        "MUR contribution per unit",
        "To show the distribution of the money assigned to a single unit, for coordinating and for partner units.",
        rf"The {len(pi_v)} coordinating units received a median of {qp[1]:.0f}~k~EUR (quartiles {qp[0]:.0f} and {qp[2]:.0f}; range {mnp:.0f} to {mxp:.0f}~k~EUR). The {len(ru_v)} partner units received a median of {qr[1]:.0f}~k~EUR (quartiles {qr[0]:.0f} and {qr[2]:.0f}; range {mnr:.0f} to {mxr:.0f}~k~EUR).",
        figure("money_per_unit_coordinating", "Histogram of the MUR contribution of the coordinating units; the dashed line is the median.", 0.6)
        + "\n" + figure("money_per_unit_partner", "Histogram of the MUR contribution of the partner units; the dashed line is the median.", 0.6)))
    parts.append(r"\subsection{Institutions}")

    # -------------------------------------------------------- 2.2 institutions
    ranked = inst.sort_values("mur_total", ascending=False)
    cum = 100 * ranked["mur_total"].cumsum() / B
    parts.append(section(
        "Funding by institution",
        "To show which institutions received the largest shares of the budget and how the budget is divided among institutions.",
        rf"{len(ranked)} institutions have at least one funded unit. The largest share is that of {tex(ranked['short_name'].iloc[0])} ({pct(ranked['share_of_budget_pct'].iloc[0])}), followed by {tex(ranked['short_name'].iloc[1])} ({pct(ranked['share_of_budget_pct'].iloc[1])}) and {tex(ranked['short_name'].iloc[2])} ({pct(ranked['share_of_budget_pct'].iloc[2])}). "
        rf"The 10 best-funded institutions received {pct(cum.iloc[9])} of the budget and the 20 best-funded {pct(cum.iloc[19])}; after accounting for them, {pct(100 - cum.iloc[9])} and {pct(100 - cum.iloc[19])} of the budget are left.",
        figure("institutions_share", "Share of the total budget of the 20 best-funded institutions, as coordinator (PI) and as partner (RU).", 0.7)
        + "\n" + figure("budget_by_institution", "Budget left, in percent of the total, as the institutions are accounted for from the best funded to the least funded; the ten largest steps are named.", 0.8)))

    # ---------------------------------------------------------------- 2.7 breadth
    rho = stats.spearmanr(inst["n_sectors"], inst["mur_total"])
    widest = inst[inst["n_sectors"] == inst["n_sectors"].max()]
    parts.append(section(
        "Breadth across sectors",
        "To show in how many sectors each institution has funded units, against the share of the budget it received.",
        rf"The number of sectors with at least one funded unit has median {inst['n_sectors'].median():.0f} across the {len(inst)} institutions; {int((inst['n_sectors'] == 1).sum())} institutions have funded units in one sector only. The maximum, {int(widest['n_sectors'].iloc[0])} sectors, is reached by {join([tex(n) for n in widest['short_name']])}. The Spearman correlation between the number of sectors and the money received is {rho.statistic:.2f} (p = {rho.pvalue:.1g}).",
        figure("institution_breadth", "Share of the total budget of each institution against the number of sectors with a funded unit (horizontal jitter added).", 0.75)))
    parts.append(r"\subsection{Geography}")

    # ------------------------------------------------------------ 2.5 geography
    reg = regions.drop(NATIONAL).sort_values("share_of_budget_pct", ascending=False)
    zero = [n.split("/")[0] for n in reg.index[reg["mur_total"] == 0]]
    city = an._city_table(d, inst)
    city_share = 100 * city["mur"] / B
    macro = "; ".join(f"{tex(a)} {pct(r['pi_share_of_region_pct'], 0)}" for a, r in areas.iterrows())
    no_pi = [n.split("/")[0] for n, r in regions.drop(NATIONAL).iterrows() if r["mur_total"] > 0 and r["pi_units"] == 0]
    parts.append(section(
        "Money by region and city",
        "To show where the money went: by region, by city, and, per region and macro-area, which part of the funding came from units coordinating projects and which from partner units.",
        rf"The regions with the largest shares are {join([f'{tex(n.split(chr(47))[0])} ({pct(r.share_of_budget_pct)})' for n, r in reg.head(3).iterrows()])}. "
        rf"National research bodies (CNR, INAF, INFN, INGV), which have no region, received {pct(regions.loc[NATIONAL, 'share_of_budget_pct'])}. "
        + (rf"No funded unit is in {join(zero)}. " if zero else "")
        + rf"The {len(city)} cities with a funded unit include {join([f'{tex(n)} ({pct(v)})' for n, v in city_share.head(5).items()])} as the five largest. "
        rf"The share of the money received by units coordinating projects is, by macro-area: {macro}. "
        + (rf"{join(no_pi)} have no coordinating unit among their funded units. " if no_pi else "")
        + "The table of regions is in Appendix C.",
        figure("map_regions_share", "Share of the total budget by region; national research bodies are not shown.", 0.7)
        + "\n" + figure("map_cities_funding", "MUR funding by city (circle area proportional to the money).", 0.7)
        + "\n" + figure("regions_roles", "Share of each macro-area's and region's funding received as coordinating (PI) and as partner (RU) units; in brackets, the number of funded units.", 0.75)))

    # ----------------------------------------------------------- 2.6 collaboration
    shared = an.shared_projects(d)
    top_pairs = shared.most_common(5)
    pair_txt = join([f"{tex(a if a != NATIONAL else 'national bodies')}--{tex(b if b != NATIONAL else 'national bodies')} ({n})" for (a, b), n in top_pairs])
    parts.append(section(
        "Collaboration between cities",
        "To show which cities share funded projects, counting the national research bodies as one node.",
        rf"{len(shared)} pairs of nodes share at least one funded project and {sum(1 for v in shared.values() if v >= 8)} share eight or more. The pairs sharing the most projects are {pair_txt}.",
        figure("collaboration_map", rf"Pairs of cities sharing at least 8 funded projects (line width proportional to the number); circle area proportional to the money; the diamond is the national research bodies. {len(d.sectors)} of 28 sectors.", 0.75)))

    # ------------------------------------------------- 2.8b budget, population, staff
    ctx = an.region_context_table(regions)
    drawn = ctx[ctx["budget_share_pct"] > 0]
    cors = {}
    for col in ("population", "staff"):
        x, y = drawn[f"{col}_share_pct"], drawn["budget_share_pct"]
        cors[col] = (stats.pearsonr(x, y).statistic, stats.spearmanr(x, y).statistic)
    rows = [[tex(r.split("/")[0]), f"{v['population_share_pct']:.1f}", f"{v['staff_share_pct']:.1f}",
             f"{v['budget_share_pct']:.1f}", f"{v['budget_over_population']:.2f}", f"{v['budget_over_staff']:.2f}"]
            for r, v in ctx.sort_values("budget_over_staff", ascending=False).iterrows()]
    nat_pct = float(regions.loc[an.NATIONAL, "share_of_budget_pct"])
    unassigned_pct = 100.0 - float(regions["share_of_budget_pct"].sum())
    bodies = join(sorted(inst.loc[inst["kind"] == "national_research_body", "short_name"]))
    rows.append([r"\textbf{National research bodies}$^\dagger$", "--", "--", rf"\textbf{{{nat_pct:.1f}}}", "--", "--"])
    parts.append(section(
        "Budget, population and university staff by region",
        "To compare the share of the total budget gathered by each region, as in the regional map, with its share of the resident population and of the professors and researchers of its universities.",
        rf"Across the {len(drawn)} regions with funded units, the share of the budget has Pearson correlation {cors['population'][0]:.2f} and Spearman correlation {cors['population'][1]:.2f} with the share of the resident population, and {cors['staff'][0]:.2f} and {cors['staff'][1]:.2f} with the share of professors and researchers (the national research bodies are not regions and are left out of the correlations; {join([tex(r.split('/')[0]) for r in ctx.index[ctx['budget_share_pct'] <= 0]])} has no funded unit and is left out). The national research bodies ({bodies}) belong to no region and received {nat_pct:.1f}\% of the budget; a further {unassigned_pct:.1f}\% of the budget was not assigned. The table gives the shares and, in the last two columns, the share of the budget divided by the share of the population and of the staff. The staff shares refer to all the professors and researchers of the Italian universities, not to those who applied to the programme, for which no data are available.",
        table(["Region", "Population (\\%)", "Staff (\\%)", "Budget (\\%)", "Budget/population", "Budget/staff"], rows, "lrrrrr", "\\small\\setlength{\\tabcolsep}{3.5pt}",
              total=["Total", f"{ctx['population_share_pct'].sum():.1f}", f"{ctx['staff_share_pct'].sum():.1f}",
                     f"{ctx['budget_share_pct'].sum() + nat_pct:.1f}", "--", "--"],
              note=rf"$^\dagger$ {bodies}: no region, so no population or staff is attributed to them.")
        + "\n" + figure("population_vs_budget", f"Share of the budget of each region against its share of the resident population (1 January 2026); logarithmic axes, the dashed line marks equal shares; the national research bodies ({nat_pct:.1f}\\% of the budget) are not shown. ER: Emilia-Romagna; FVG: Friuli-Venezia Giulia; TAA: Trentino-Alto Adige.", 0.75)
        + "\n" + figure("staff_vs_budget", "As above, against the share of professors and researchers of the universities of the region (2024), over all the Italian university staff and not only the applicants.", 0.75)))
    parts.append(r"\subsection{People}")

    # ------------------------------------------------------------------ 2.8 gender
    rows = []
    for g, sub in gt.groupby("group", sort=False):
        for _, r in sub.iterrows():
            rows.append([tex(g), r["macro"], str(int(r["n"])), f"{100 * r['female_share']:.0f}",
                         f"{100 * r['low']:.0f}--{100 * r['high']:.0f}"])
    both = gt[gt["macro"] == "All"]
    n_both, k_both = int(both["n_known"].sum()), int(round((both["female_share"] * both["n_known"]).sum()))
    f_both, lo_both, hi_both = an.wilson(k_both, n_both)
    gender_total = ["Total", "All", str(n_both), f"{100 * f_both:.0f}", f"{100 * lo_both:.0f}--{100 * hi_both:.0f}"]
    allpi = gt[(gt["group"] == "PI, funded") & (gt["macro"] == "All")].iloc[0]
    allru = gt[(gt["group"] == "Partner-unit leaders, funded") & (gt["macro"] == "All")].iloc[0]
    parts.append(section(
        "Gender of the unit leaders",
        "To show the share of women among the leaders of the funded units, with the uncertainty due to the small numbers, by macro-area (PE, LS, SH).",
        rf"Among the {int(allpi['n'])} funded PIs, {pct(100 * allpi['female_share'], 0)} are women (95\% interval {100 * allpi['low']:.0f}--{100 * allpi['high']:.0f}); among the {int(allru['n'])} leaders of funded partner units, {pct(100 * allru['female_share'], 0)} ({100 * allru['low']:.0f}--{100 * allru['high']:.0f}). The first given name was found in the name table for all {int(allpi['n_known'] + allru['n_known'])} leaders considered. The table gives the shares by macro-area.",
        table(["Group", "Area", "Leaders", "Women (\\%)", "95\\% interval"], rows, "llrrr", total=gender_total)
        + "\n" + figure("gender", "Share of women among the leaders of the funded units, with Wilson 95\\% intervals; the dashed line marks 50\\%.", 0.7)))

    # ------------------------------------------------------------------- 2.10 GSD
    gsd_dir = out_dir / "analysis"
    if (gsd_dir / "gsd_areas.csv").exists():
        st = pd.read_csv(gsd_dir / "gsd_status.csv", index_col=0)
        ga = pd.read_csv(gsd_dir / "gsd_areas.csv", index_col=0, dtype={"code": str})
        gc = pd.read_csv(gsd_dir / "gsd_codes.csv", index_col=0)
        gm = pd.read_csv(gsd_dir / "gsd_macro.csv", index_col=0, dtype={"code": str})
        n_all, n_found = int(st["leaders"].sum()), int(st["found"].sum())
        other = {c: int(st[c].sum()) if c in st else 0 for c in ("other_university", "not_found", "ambiguous", "not_looked_up")}
        pi_f, ru_f = int(st.loc["PI", "found"]), int(st.loc["Partner-unit leaders", "found"])
        top = ga.sort_values("leaders", ascending=False).head(3)
        top_txt = join([tex(f"{c} {a}") + f" ({int(n)})" for c, a, n in zip(top.index, top["area"], top["leaders"])])
        rows = [[f"{c} {tex(a.split(',')[0][:30])}", f"{int(v['staff'])}", f"{int(v['PI'])}", f"{int(v['Partner-unit leaders'])}",
                 f"{int(gm.loc[c, 'PE'])}", f"{int(gm.loc[c, 'LS'])}", f"{int(gm.loc[c, 'SH'])}",
                 f"{v['leaders_share_pct']:.1f}", f"{v['staff_share_pct']:.1f}", f"{v['budget_share_pct']:.1f}",
                 f"{v['leaders_per_1000_staff']:.1f}"]
                for (c, v), a in zip(ga.iterrows(), ga["area"])]
        cor = (stats.pearsonr(ga["staff_share_pct"], ga["budget_share_pct"]).statistic,
               stats.spearmanr(ga["staff_share_pct"], ga["budget_share_pct"]).statistic)
        rows_codes = [[tex(g), str(int(v["PI"])), str(int(v["Partner-unit leaders"])), str(int(v["leaders"]))]
                      for g, v in gc.head(15).iterrows()]
        parts.append(section(
            "Disciplinary group of the unit leaders",
            "To show the disciplinary group (GSD 2024) of the leaders of the funded units, by area of the National University Council (CUN), against the professors and researchers of the Italian universities.",
            rf"The GSD was found at the university of the unit for {n_found} of the {n_all} leaders ({pi_f} PI, {ru_f} partner-unit leaders). The other leaders are: found only at another university {other['other_university']}, in no record {other['not_found']} (research bodies and other institutions that are not universities, and people not listed), several records at the university {other['ambiguous']}, not looked up {other['not_looked_up']}. The three areas with most leaders are {top_txt}. The units whose leader's GSD was found received {ga['budget_share_pct'].sum():.1f}\% of the budget; by CUN area, the share of the budget has Pearson correlation {cor[0]:.2f} and Spearman correlation {cor[1]:.2f} with the share of the professors and researchers. The first table gives the leaders by CUN area (the first two digits of the GSD) and by ERC macro-area, the share of leaders, of staff and of the budget, and the leaders per 1000 professors and researchers; the second the most frequent GSDs. The staff shares refer to all the professors and researchers of the Italian universities, not to those who applied to the programme, for which no data are available.",
            table(["CUN area", "Staff", "PI", "Partners", "PE", "LS", "SH", "Lead. (\\%)", "Staff (\\%)", "Budget (\\%)", "Per 1000"], rows, "lrrrrrrrrrr", "\\scriptsize\\setlength{\\tabcolsep}{2.5pt}",
                  total=["Total", str(int(ga["staff"].sum())), str(int(ga["PI"].sum())),
                         str(int(ga["Partner-unit leaders"].sum())), str(int(gm["PE"].sum())), str(int(gm["LS"].sum())),
                         str(int(gm["SH"].sum())), "100.0", "100.0", f"{ga['budget_share_pct'].sum():.1f}",
                         f"{1000 * ga['leaders'].sum() / ga['staff'].sum():.1f}"],
                  note="Staff: all professors and researchers of the Italian universities, not only applicants.")
            + "\n" + table(["GSD", "PI", "Partners", "Leaders"], rows_codes, "lrrr", "\\small",
                  total=["Total, all GSDs", str(int(gc["PI"].sum())), str(int(gc["Partner-unit leaders"].sum())),
                         str(int(gc["leaders"].sum()))])
            + "\n" + figure("gsd_staff_vs_budget", "Share of the budget received by the units whose leader's GSD was found, against the share of the professors and researchers (2024), by CUN area, numbered as in the table above; logarithmic axes, the dashed line marks equal shares. The staff is all the professors and researchers of the Italian universities, not only the applicants.", 0.75)
            + "\n" + figure("gsd_areas", "Share of the funded unit leaders found in the MUR directory, and share of all the professors and researchers of the Italian universities (2024, not only the applicants), by CUN area.", 0.75)))

    # ------------------------------------------------------------ career level
    if (gsd_dir / "career_levels.csv").exists():
        cl = pd.read_csv(gsd_dir / "career_levels.csv", index_col=0)
        cl = cl[cl["leaders"] > 0]
        n_lead = int(cl["leaders"].sum())
        po, pa = cl.iloc[0], cl.iloc[1]
        rt = cl[cl.index.str.startswith("Fixed-term")]
        rows = [[tex(lv), str(int(v["PI"])), str(int(v["Partner-unit leaders"])), str(int(v["leaders"])),
                 str(int(v["PE"])), str(int(v["LS"])), str(int(v["SH"])),
                 f"{v['leaders_share_pct']:.1f}", f"{v['mur_total'] / 1e6:.2f}", f"{v['budget_share_pct']:.1f}",
                 f"{v['mean_per_unit'] / 1e3:.0f}"] for lv, v in cl.iterrows()]
        ca = pd.read_csv(gsd_dir / "career_areas.csv", index_col=0, dtype={"code": str})
        ca["n"] = ca[[f"leaders_{k}" for k in ("po", "pa", "rtd", "ru")]].sum(axis=1)
        def comp(c, v):
            return [str(int(v["n"]))] + [f"{v[f'staff_{k}_pct']:.1f}" for k in ("po", "pa", "rtd", "ru")] \
                + [f"{v[f'leaders_{k}_pct']:.1f}" for k in ("po", "pa", "rtd", "ru")]
        rows_comp = [[f"{c} {tex(v['area'].split(',')[0][:30])}"] + comp(c, v) for c, v in ca.iloc[:-1].iterrows()]
        comp_total = ["All areas"] + comp("All", ca.loc["All"])
        rate = lambda v: [f"{v[f'leaders_per_1000_{k}']:.1f}" for k in ("po", "pa", "rtd")]
        rows_rate = [[f"{c} {tex(v['area'].split(',')[0][:30])}"] + rate(v) for c, v in ca.iloc[:-1].iterrows()]
        rate_total = ["All areas"] + rate(ca.loc["All"])
        parts.append(section(
            "Career level of the unit leaders",
            "To show the career level (full professor PO, associate professor PA, fixed-term researcher RTD) of the leaders of the funded units, the MUR money of their units, and, by CUN area, the share of each level among the leaders against its share among all the professors and researchers of the Italian universities (2024). The levels are from the same MUR directory lookup as the disciplinary group; PRIN sectors have no staff data, so the staff comparison is by CUN area.",
            rf"The level was found for {n_lead} leaders. Full professors are {int(po['PI'])} of the {int(cl['PI'].sum())} PIs and {int(po['Partner-unit leaders'])} of the {int(cl['Partner-unit leaders'].sum())} partner-unit leaders; associate professors are {int(pa['PI'])} and {int(pa['Partner-unit leaders'])}; fixed-term researchers are {int(rt['PI'].sum())} and {int(rt['Partner-unit leaders'].sum())}. The units led by full professors received {cl.iloc[0]['budget_share_pct']:.1f}\% of the total budget, those led by associate professors {cl.iloc[1]['budget_share_pct']:.1f}\%, those led by fixed-term researchers {rt['budget_share_pct'].sum():.1f}\%. The mean MUR contribution per unit is in the last column. Over all areas, PO are {ca.loc['All','staff_po_pct']:.1f}\% of the staff and {ca.loc['All','leaders_po_pct']:.1f}\% of the leaders, PA {ca.loc['All','staff_pa_pct']:.1f}\% and {ca.loc['All','leaders_pa_pct']:.1f}\%, RTD {ca.loc['All','staff_rtd_pct']:.1f}\% and {ca.loc['All','leaders_rtd_pct']:.1f}\%; the leaders per 1000 staff are {ca.loc['All','leaders_per_1000_po']:.1f} for PO, {ca.loc['All','leaders_per_1000_pa']:.1f} for PA and {ca.loc['All','leaders_per_1000_rtd']:.1f} for RTD. The tables give the same by CUN area.",
            table(["Level", "PI", "Partners", "Leaders", "PE", "LS", "SH", "Lead. (\\%)", "MUR (M EUR)", "Budget (\\%)", "Mean (k EUR)"],
                  rows, "lrrrrrrrrrr", "\\scriptsize\\setlength{\\tabcolsep}{2pt}",
                  total=["Total", str(int(cl["PI"].sum())), str(int(cl["Partner-unit leaders"].sum())), str(n_lead),
                         str(int(cl["PE"].sum())), str(int(cl["LS"].sum())), str(int(cl["SH"].sum())), "100.0",
                         f"{cl['mur_total'].sum() / 1e6:.2f}", f"{cl['budget_share_pct'].sum():.1f}",
                         f"{cl['mur_total'].sum() / n_lead / 1e3:.0f}"],
                  note="Leaders found at the university of their unit; mean: MUR contribution per unit.")
            + "\n" + table(["CUN area", "Lead.", "PO", "PA", "RTD", "RU", "PO", "PA", "RTD", "RU"], rows_comp, "lrrrrrrrrr",
                  "\\scriptsize\\setlength{\\tabcolsep}{3pt}", total=comp_total,
                  note="Columns 3--6: \\% of the area staff; 7--10: \\% of the leaders. RU: permanent researchers.")
            + "\n" + table(["CUN area", "PO", "PA", "RTD"], rows_rate, "lrrr", "\\small", total=rate_total,
                  note="Leaders per 1000 staff of the same level and area (all staff, not only applicants).")
            + "\n" + figure("career_levels", "Share of the funded PIs and of the partner-unit leaders found in the MUR directory, by career level.", 0.75)))

    # ------------------------------------------------------------ 2.9 fact sheet
    summ = json.loads((out_dir / "analysis" / "summary.json").read_text())
    if highlight and summ.get("highlight"):
        name, f = next(iter(summ["highlight"].items()))
        cf = inst.index[inst["short_name"] == name][0]
        peers = inst[inst["kind"] == f["type"]]
        mine = units[units["cf"] == cf].sort_values("sector")
        rows = []
        for _, r in mine.iterrows():
            g = units[units["project_code"] == r["project_code"]]
            lead = g[g["role"] == "PI"].iloc[0]
            others = sorted(set(g["short_name"]) - {name} - ({lead["short_name"]} if r["role"] == "RU" else set()))
            title = r["title"] if len(r["title"]) <= 64 else r["title"][:61].rsplit(" ", 1)[0] + "..."
            rows.append([r["sector"], r["role"], f"{r['mur_contribution'] / 1e3:.0f}", tex(title),
                         tex(lead["short_name"] if r["role"] == "RU" else "this institution"),
                         tex(", ".join(others))])
        facts = [["Funding", eur(f["mur_total"], 2) + f", {pct(f['share_of_budget_pct'], 2)} of the budget",
                  pct(peers["share_of_budget_pct"].median(), 2)],
                 ["Rank", f"{f['rank']} of {len(inst)}; {f['rank_in_type']} of {f['n_institutions_of_type']} in its type", ""],
                 ["Funded projects", str(f["projects"]), f"{peers['projects'].median():.0f}"],
                 ["Sectors with a funded unit", f"{f['n_sectors']} of {len(d.sectors)}", f"{peers['n_sectors'].median():.0f}"],
                 ["Money received as PI", pct(100 * peers.loc[cf, "mur_pi"] / f["mur_total"], 0),
                  pct(100 * (peers["mur_pi"] / peers["mur_total"]).median(), 0)]]
        body = (table([tex(name), "Value", f"Median, {tex(an.KIND_LABELS[f['type']].lower())}"],
                      [[tex(a), b, c] for a, b, c in facts], "llr")
                + "\n" + table(["Sector", "Role", "k EUR", "Project", "Coordinator", "Other institutions"], rows, "llrp{4.6cm}p{2cm}p{3.6cm}", r"\footnotesize",
                              total=["Total", "", f"{mine['mur_contribution'].sum() / 1e3:.0f}", "", "", ""])
                + "\n" + figure("highlight_neighbours", rf"Share of the total budget of {tex(name)} and of the institutions ranked just above and below it.", 0.65)
                + "\n" + figure("highlight_map", rf"Cities sharing funded projects with {tex(name)} (line width proportional to the number of projects).", 0.75))
        parts.append(section(
            f"Institution fact sheet: {tex(name)}",
            "To collect the figures of one institution and compare them with the other institutions of the same type.",
            rf"{tex(name)} received {eur(f['mur_total'], 2)} ({pct(f['share_of_budget_pct'], 2)} of the budget) in {f['projects']} projects, {f['pi_units']} as coordinator and {f['ru_units']} as partner, in {f['n_sectors']} sectors; it ranks {f['rank']} of {len(inst)} institutions and {f['rank_in_type']} of {f['n_institutions_of_type']} within its type.",
            body, level="subsection"))

    # ------------------------------------------------------------- appendices
    parts.append(r"\appendix")
    rows = [[s, str(r["decree_number"]), r["date"], rf"\href{{{r['page']}}}{{page}}"]
            for s, r in sorted(manifest["decrees"].items(), key=lambda kv: (kv[0][:2], int(kv[0][2:])))]
    parts.append(r"\section{Decrees}" + "\n" + table(["Sector", "Decree n.", "Date", "MUR page"], rows, "llll"))
    rows = [[s, eur(r["budget"], 2), eur(r["funded"], 2), f"{r['used_pct']:.1f}", str(int(r["n_funded"])),
             str(int(r["n_ranked"])), eur(u40.loc[s, "pool"], 2), eur(u40.loc[s, "money_under40_projects"], 2)]
            for s, r in sec.iterrows()]
    parts.append(r"\section{Sectors}" + "\n" + table(
        ["Sector", "Available", "Funded", "Funded (\\%)", "Projects", "Ranked", "Under-40 pool", "Under-40 PIs' projects"], rows,
        "lrrrrrrr", r"\footnotesize\setlength{\tabcolsep}{3pt}",
        total=["Total", eur(sec["budget"].sum(), 2), eur(sec["funded"].sum(), 2),
               f"{100 * sec['funded'].sum() / sec['budget'].sum():.1f}", str(int(sec["n_funded"].sum())),
               str(int(sec["n_ranked"].sum())), eur(u40.loc[sec.index, "pool"].sum(), 2),
               eur(u40.loc[sec.index, "money_under40_projects"].sum(), 2)]))
    rows = [[tex(n.split("/")[0]), f"{r['share_of_budget_pct']:.2f}", str(int(r["projects"])), str(int(r["pi_units"])),
             str(int(r["ru_units"])), "" if np.isnan(r["pi_share_of_region_pct"]) else f"{r['pi_share_of_region_pct']:.0f}"]
            for n, r in regions.iterrows()]
    parts.append(r"\section{Regions}" + "\n" + table(
        ["Region", "Share (\\%)", "Projects", "PI units", "RU units", "As PI (\\%)"], rows, "lrrrrr", r"\footnotesize",
        total=["Total", f"{regions['share_of_budget_pct'].sum():.2f}", str(n_proj), str(int(regions["pi_units"].sum())),
               str(int(regions["ru_units"].sum())), f"{100 * regions['mur_pi'].sum() / regions['mur_total'].sum():.0f}"]))
    lines = [r"\section{All institutions}",
             "Institutions with at least one funded unit, by funding (the region of each is in the institution table of the analysis output); share of the total budget, MUR contribution, projects, units as coordinator (PI) and partner (RU), sectors with a funded unit.", "",
             r"{\footnotesize\setlength{\tabcolsep}{2.5pt}", r"\begin{longtable}{rlllrrrrrr}", r"\toprule",
             r"Rank & Institution & Type & City & Share (\%) & k EUR & Proj. & PI & RU & Sect. \\", r"\midrule", r"\endhead"]
    for _, r in inst.iterrows():
        lines.append(" & ".join([str(int(r["rank"])), tex(r["short_name"]), tex(an.KIND_LABELS[r["kind"]]), tex(r["city"]),
                                 f"{r['share_of_budget_pct']:.2f}", f"{r['mur_total'] / 1e3:.0f}",
                                 str(int(r["projects"])), str(int(r["pi_units"])), str(int(r["ru_units"])),
                                 str(int(r["n_sectors"]))]) + r" \\")
    lines += [r"\midrule",
              " & ".join(["", "Total", "", "", f"{inst['share_of_budget_pct'].sum():.2f}", f"{inst['mur_total'].sum() / 1e3:.0f}",
                          str(n_proj), str(int(inst["pi_units"].sum())), str(int(inst["ru_units"].sum())),
                          str(len(d.sectors))]) + r" \\",
              r"\bottomrule", r"\end{longtable}", "}"]
    parts.append("\n".join(lines))

    head = rf"""{PREAMBLE}\title{{PRIN 2026: funded projects}}
\author{{}}
\date{{Data of {datetime.date.today().strftime("%d/%m/%Y")}; {len(d.sectors)} of {len(decrees.ALL_SECTORS)} sectors}}
\begin{{document}}
\maketitle
"""
    return head + "\n".join(parts) + "\n\\end{document}\n"


RESULTS_BEGIN, RESULTS_END = "<!-- results:begin -->", "<!-- results:end -->"
README_FIGURES = [("map_regions_share", "Share of the total budget by region (national research bodies not shown)."),
                  ("regions_roles", "Per macro-area and region, share of the funding received as coordinating (PI) and partner (RU) units."),
                  ("sector_budgets", "Per sector, in percent of the total budget: budget available and money funded, with the projects of under-40 PIs in green."),
                  ("institution_types", "Share of the total budget by institution type."),
                  ("gender", "Share of women among unit leaders, with 95% intervals.")]


def readme_results(out_dir: Path) -> str:
    """Markdown of the global results of the README, all numbers from the tables."""
    d = an.load(out_dir)
    units, B = d.units, d.budget
    funded = float(units["mur_contribution"].sum())
    kinds = an._money(units, "kind", B)
    areas, regions = an.macro_area_table(d), an.region_table(d)
    u40, gt = an.under40_table(d), an.gender_table(d)
    pi = gt[(gt["group"] == "PI, funded") & (gt["macro"] == "All")].iloc[0]
    ru = gt[(gt["group"] == "Partner-unit leaders, funded") & (gt["macro"] == "All")].iloc[0]
    med = {r: float(np.median(units.loc[units["role"] == r, "mur_contribution"])) / 1e3 for r in ("PI", "RU")}
    kind_txt = ", ".join(f"{an.KIND_LABELS[k]} {kinds.loc[k, 'share_of_budget_pct']:.1f}%"
                         for k in an.KIND_LABELS if k in kinds.index)
    area_txt = ", ".join(f"{a} {r['share_of_budget_pct']:.1f}% (of which {r['pi_share_of_region_pct']:.0f}% as PI)"
                         for a, r in areas.iterrows())
    lines = [f"Provisional: {len(d.sectors)} of {len(decrees.ALL_SECTORS)} sectors. "
             f"Regenerate with `python3 analysis.py` and `python3 report.py`; the full report is "
             f"[report/report.pdf](report/report.pdf).", "",
             "| Quantity | Value |", "|---|---|",
             f"| Budget of the parsed sectors | {B / 1e6:.2f} M EUR |",
             f"| Funded | {funded / 1e6:.2f} M EUR ({100 * funded / B:.1f}% of the budget) |",
             f"| Projects, units | {units['project_code'].nunique()}, {len(units)} ({int((units['role'] == 'PI').sum())} PI, {int((units['role'] == 'RU').sum())} RU) |",
             f"| Institutions with a funded unit | {units['cf'].nunique()} |",
             f"| Share by institution type | {kind_txt} |",
             f"| Share by macro-area | {area_txt}; national research bodies {regions.loc[NATIONAL, 'share_of_budget_pct']:.1f}% |",
             f"| Median MUR contribution per unit | {med['PI']:.0f} k EUR (PI), {med['RU']:.0f} k EUR (RU) |",
             f"| Projects of under-40 PIs | {int(u40['funded_under40'].sum())} projects, {u40['money_under40_projects'].sum() / 1e6:.2f} M EUR ({100 * u40['money_under40_projects'].sum() / funded:.1f}% of the funded money); under-40 pools {u40['pool'].sum() / 1e6:.2f} M EUR |",
             f"| Women among unit leaders | {100 * pi['female_share']:.0f}% of PIs, {100 * ru['female_share']:.0f}% of partner-unit leaders |",
             ""]
    for name, caption in README_FIGURES:
        lines += [f"![{caption}](prin_out/figures/{name}.png)", f"*{caption}*", ""]
    return "\n".join(lines).rstrip()


def update_readme_results(readme: Path, out_dir: Path):
    """Rewrite the text between the results markers of the README; no markers, no change."""
    text = readme.read_text()
    if RESULTS_BEGIN not in text or RESULTS_END not in text:
        log.warning("%s has no results markers: not updated", readme)
        return
    head, rest = text.split(RESULTS_BEGIN, 1)
    tail = rest.split(RESULTS_END, 1)[1]
    readme.write_text(f"{head}{RESULTS_BEGIN}\n{readme_results(out_dir)}\n{RESULTS_END}{tail}")


def main(argv=None) -> int:
    ap = arg.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="prin_out", help="directory written by prin_extract.py and analysis.py")
    ap.add_argument("--highlight", default="Siena", help="city of the institution fact sheet; '' for none")
    ap.add_argument("--no-compile", action="store_true", help="write report.tex only")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(__file__).resolve().parent
    out = Path(a.out)
    rdir = root / "report"
    rdir.mkdir(exist_ok=True)
    (rdir / "report.tex").write_text(build(out, a.highlight or None), encoding="utf-8")
    update_readme_results(root / "README.md", out)
    if not a.no_compile:
        for _ in range(2):
            subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "report.tex"],
                           cwd=rdir, check=True, stdout=subprocess.DEVNULL)
    print(f"Wrote {rdir / 'report.tex'}" + ("" if a.no_compile else " and report.pdf"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
