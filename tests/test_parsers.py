"""Tests on the real MUR PDFs and tables in the repository (no network, no QM)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import analysis  # noqa: E402
import decrees  # noqa: E402
import gender  # noqa: E402
import tabella_a  # noqa: E402

OUT = ROOT / "prin_out"


def test_split_name_surname_is_first_capital_run():
    assert tabella_a.split_name("Maria Beatrice POZZETTI") == ("Maria Beatrice", "POZZETTI")
    assert tabella_a.split_name("Carmela DELL'AVERSANA Anna Christina") == (
        "Carmela Anna Christina", "DELL'AVERSANA")
    assert tabella_a.split_name("Anna KAJASTE- RUDNITSKI") == ("Anna", "KAJASTE-RUDNITSKI")


def test_tabella_a_matches_tabella_b():
    """Every funded project is ranked, PI names agree, and the ranks are 1..n."""
    units = pd.read_csv(OUT / "all_rows.csv", dtype={"cf": str})
    pis = units[units["role"] == "PI"].set_index("project_code")["name"]
    for pdf in sorted((ROOT / "prin_pdfs" / "tabella_a").glob("*.pdf")):
        sector = pdf.name.split("_")[0]
        rows = tabella_a.parse_pdf(pdf, sector)
        assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
        funded = set(units.loc[units["sector"] == sector, "project_code"])
        assert funded <= {r["project_code"] for r in rows}, sector
        for r in rows:
            if r["project_code"] in pis.index:
                assert f"{r['pi_surname']} {r['pi_given']}".lower() == pis[r["project_code"]].lower()


def test_tabella_a_tie_break_cells_of_a_full_row():
    rows = tabella_a.parse_pdf(ROOT / "prin_pdfs" / "tabella_a" / "LS7_n39.pdf", "LS7")
    first = rows[0]
    assert (first["score"], first["excellence"], first["impact"], first["equity"]) == (
        100.0, 40.0, 20.0, 0.95)
    assert (first["men"], first["women"]) == (9, 10)


def test_budgets_cover_28_sectors_and_add_up():
    manifest = decrees.load_manifest(OUT / "decrees.json")
    b = manifest["budgets"]
    assert set(b) == set(decrees.ALL_SECTORS)
    for macro in ("PE", "LS"):
        total = sum(v["total"] for k, v in b.items() if k.startswith(macro))
        assert total == pytest.approx(90_961_274.0, abs=0.05)
    for v in b.values():
        assert v["under40"] + v["ordinary"] == pytest.approx(v["total"], abs=0.015)


def test_funded_never_exceeds_the_sector_budget():
    d = analysis.load(OUT)
    sec = analysis.sector_table(d)
    assert (sec["funded"] <= sec["budget"]).all()


def test_regional_shares_conserve_the_funded_money():
    d = analysis.load(OUT)
    regions = analysis.region_table(d)
    assert regions["mur_total"].sum() == pytest.approx(d.units["mur_contribution"].sum())
    inst = analysis.institution_table(d)
    assert inst["mur_total"].sum() == pytest.approx(d.units["mur_contribution"].sum())


def test_gender_table_covers_every_given_name_seen():
    """Every given name is in data/given_names.csv. A name whose gender the ending rule does not
    decide stays empty (basis 'review') and is left out of the shares; the pull request lists it."""
    d = analysis.load(OUT)
    table = pd.read_csv(ROOT / "data" / "given_names.csv", keep_default_na=False)
    givens = ([g.split()[0] for g in d.ranking["pi_given"].dropna()]
              + [gender.first_given_from_surname_first(n) for n in d.units["name"]])
    assert not gender.unresolved(givens, dict.fromkeys(table["given"], "")), "run analysis.py to add them"
    for df in (d.ranking, d.units):
        assert df["gender"].notna().mean() > 0.99


@pytest.mark.parametrize("name,expected", [("Veronica", "F"), ("Luca", "M"), ("Andrea", "M"),
                                           ("Simone", "M"), ("Zzzzze", None)])
def test_gender_infer(name, expected):
    assert gender.infer(name) == expected


def test_concentration_of_equal_shares_is_zero():
    inst = pd.DataFrame({"mur_total": np.ones(20)})
    assert analysis.concentration(inst)["gini"] == pytest.approx(0.0, abs=1e-12)


def test_institution_table_keys_every_funded_cf():
    inst = pd.read_csv(ROOT / "data" / "institutions.csv", dtype={"cf": str})
    units = pd.read_csv(OUT / "all_rows.csv", dtype={"cf": str})
    assert set(units["cf"]) <= set(inst["cf"])
    regions = {f["properties"]["region"] for f in
               json.loads((ROOT / "data" / "italy_regions.geojson").read_text())["features"]}
    assert set(inst["region"].dropna()) <= regions


def test_under40_flag_agrees_with_the_printed_birth_years():
    r = pd.read_csv(OUT / "ranking.csv")
    known = r[r["birth_year"].notna()]
    assert len(known) > 0
    assert not known.loc[known["birth_year"] <= 1985, "under40"].any()
    assert known.loc[known["birth_year"] >= 1987, "under40"].all()


def test_under40_table_is_consistent():
    d = analysis.load(OUT)
    u = analysis.under40_table(d)
    assert (u["funded_under40"] <= u["ranked_under40"]).all()
    assert (u["funded_over40"] <= u["ranked_over40"]).all()
    assert (u["ranked_under40"] + u["ranked_over40"]).sum() == len(d.ranking)
    assert (u["funded_under40"] + u["funded_over40"]).sum() == d.units["project_code"].nunique()


def test_institution_ranks_and_breadth():
    d = analysis.load(OUT)
    inst = analysis.institution_table(d)
    assert (inst["mur_total"].diff().dropna() <= 0).all()
    assert list(inst["rank"]) == list(range(1, len(inst) + 1))
    assert (inst["n_sectors"] >= 1).all() and (inst["n_sectors"] <= len(d.sectors)).all()
    per_sector = analysis.institution_sector_table(d)
    assert per_sector["mur"].sum() == pytest.approx(d.units["mur_contribution"].sum())


def test_macro_areas_cover_every_region_except_national_bodies():
    d = analysis.load(OUT)
    areas = analysis.macro_area_table(d)
    regions = analysis.region_table(d)
    assert areas["mur_total"].sum() == pytest.approx(
        regions.drop(analysis.NATIONAL)["mur_total"].sum())
    listed = {r for rs in analysis.MACRO_AREA.values() for r in rs}
    assert listed == set(regions.index) - {analysis.NATIONAL}


def test_report_text_has_every_section_and_no_missing_numbers():
    import report
    tex = report.build(OUT, "Siena")
    for title in ("Scope", "Budget and funded money per sector", "Geography", "Gender of the unit leaders",
                  "Institution fact sheet: Siena", "All institutions"):
        assert title in tex
    assert "nan" not in tex.replace("Finance", "").lower().split("\\begin{document}")[1].replace("financ", "")
    assert tex.count(r"\begin{figure}") == tex.count(r"\end{figure}")


def test_readme_results_block_numbers_come_from_the_tables():
    import report
    block = report.readme_results(OUT)
    d = analysis.load(OUT)
    assert f"{d.budget / 1e6:.2f} M EUR" in block
    assert f"{d.units['project_code'].nunique()}, {len(d.units)}" in block


def test_region_context_tables_cover_the_regions_of_the_map():
    """Population and staff tables list the same regions as the map; the shares add to 100."""
    regions = [f["properties"]["region"] for f in
               json.loads((ROOT / "data" / "italy_regions.geojson").read_text())["features"]]
    pop = pd.read_csv(ROOT / "data" / "population_regions.csv", index_col=0)
    staff = pd.read_csv(ROOT / "data" / "university_staff.csv", index_col=0)
    assert set(pop.index) == set(regions) == set(staff.index)
    regions_table = pd.read_csv(OUT / "analysis" / "regions.csv", index_col=0)
    ctx = analysis.region_context_table(regions_table)
    for col in ("population_share_pct", "staff_share_pct"):
        assert ctx[col].sum() == pytest.approx(100.0)
    assert ctx["budget_share_pct"].equals(regions_table.drop(analysis.NATIONAL)["share_of_budget_pct"])
    assert pop["population"].sum() == 58942828


def test_gsd_name_and_university_matching():
    import gsd
    assert gsd.search_names("ARCA SEDDA Manuel") == ("ARCA SEDDA", "Manuel")
    assert gsd.search_names("CIURLI Stefano Luciano") == ("CIURLI", "Stefano")
    same = gsd.same_university
    assert same('Università "Campus Bio-Medico" di ROMA', 'Univ. "Campus Bio-Medico" di ROMA')
    assert same('Università degli Studi di ROMA "La Sapienza"', 'ROMA "La Sapienza"')
    assert not same('Università degli Studi di ROMA "La Sapienza"', "ROMA TRE")
    assert not same("Politecnico di BARI", "BARI")
    assert same("Università degli Studi INSUBRIA Varese-Como", "INSUBRIA")
    assert same('Università degli Studi della Campania "Luigi Vanvitelli"', 'CAMPANIA - "L. VANVITELLI"')
    assert same("Università degli Studi dell'AQUILA", "L'AQUILA")
    assert not same("Università degli Studi di MILANO", "MILANO-BICOCCA")


def test_under40_name_only_green_is_detected():
    """LS6 and SH5 print only the PI's name in green, not the project code."""
    cells = [("2026PXXXXX", False), ("A title", False), ("Maria ROSSI", True), ("85,00", False)]
    assert tabella_a.parse_cells(cells, "LS6")[0]["under40"]


def test_tabella_a_glued_cells_are_split():
    """LS5 prints rank and code, name and scores, or only the scores, in one text cell."""
    cells = [
        ("1 2026P3FMLS Disentangling non-nEuronal ceLls", False), ("DELETE-PAIN", False),
        ("Romina NASSINI 85,50 36,00", False),
        ("2 2026PHMNCT", False), ("A title", False), ("Michela FAGIOLINI 85,00 34,50 16,00 0,80 3 2", False),
        ("3", False), ("2026PPHL87", True), ("Another title", False), ("Cristina SPALLETTI", True),
        ("84,25 34,50", False),
    ]
    rows = tabella_a.parse_cells(cells, "LS5")
    assert [r["project_code"] for r in rows] == ["2026P3FMLS", "2026PHMNCT", "2026PPHL87"]
    assert [r["pi_surname"] for r in rows] == ["NASSINI", "FAGIOLINI", "SPALLETTI"]
    assert [r["score"] for r in rows] == [85.5, 85.0, 84.25]
    assert rows[0]["title"] == "Disentangling non-nEuronal ceLls DELETE-PAIN"
    assert (rows[1]["equity"], rows[1]["men"], rows[1]["women"]) == (0.8, 3, 2)
    assert [r["under40"] for r in rows] == [False, False, True]
    with pytest.raises(ValueError, match="expected 1"):
        tabella_a.parse_cells([("2 2026P3FMLS", False)], "LS5")


def test_focus_tables_split_units_by_gsd():
    import analysis as an
    import focus
    units = pd.DataFrame(dict(
        sector=["PE5", "PE5", "PE5"], project_code=["A", "A", "B"], role=["PI", "RU", "PI"],
        name=["P One", "R Two", "P Three"], institution=["X", "Y", "X"], cf=["1", "2", "1"],
        mur_contribution=[100.0, 50.0, 200.0], gender=["F", "M", "M"], short_name=["X", "Y", "X"]))
    ranking = pd.DataFrame(dict(project_code=["A", "B"], under40=[True, False]))
    d = an.Data(units=units, ranking=ranking, budgets=None, budget=1000.0, sectors=["PE5"])
    cache = pd.DataFrame(dict(name=["P One", "R Two", "P Three"], institution=["X", "Y", "X"], status="found",
                              gsd=["03/CHEM-05", "03/CHEM-03", "03/CHEM-05"], ssd=["CHEM-05/A", "CHEM-03/A", "CHEM-05/A"],
                              role=["Associato", "Ordinario", "Ricercatore"]))
    t = focus.tables(d, cache, "03/CHEM")
    p = t["profile"]
    assert p.loc["03/CHEM-05", "units"] == 2 and p.loc["03/CHEM-05", "pi_under40"] == 1
    assert p.loc["03/CHEM-03", "ru_money"] == 50.0 and p.loc["All", "mur_total"] == 350.0
    assert t["partners"].loc["03/CHEM-05", "03"] == 1
