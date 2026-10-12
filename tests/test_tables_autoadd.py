import pandas as pd

import gender
import institutions


def test_record_missing_given_names(tmp_path):
    p = tmp_path / "g.csv"
    pd.DataFrame({"given": ["Anna"], "gender": ["F"], "basis": ["curated"]}).to_csv(p, index=False)
    assert gender.record_missing(["Anna", "Luisa", "Jean"], p) == ["Jean"]
    t = pd.read_csv(p, keep_default_na=False).set_index("given")
    assert t.loc["Luisa", "gender"] == "F" and t.loc["Jean", "basis"] == "review"
    assert "Jean" not in gender.load_table(p) and gender.infer("Jean", gender.load_table(p)) is None


def test_institution_kind_from_name():
    assert institutions.guess_kind('Università Telematica "E-CAMPUS"') == "telematic"
    assert institutions.guess_kind("Università degli Studi di PAVIA") == "public_university"
    assert institutions.guess_kind("Scuola IMT Alti Studi - LUCCA") == "school"
    assert institutions.guess_short_name("Università degli Studi di PAVIA") == "Pavia"
