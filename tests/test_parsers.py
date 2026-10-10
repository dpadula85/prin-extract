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
    d = analysis.load(OUT)
    assert d.ranking["gender"].notna().all()
    assert d.units["gender"].notna().all()


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
