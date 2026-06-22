import pytest
import pandas as pd
import pyreadstat
from nsight import config
from nsight.store.survey_store import SurveyStore


def test_ingest_then_frame_roundtrips_rows(tiny_sav, tmp_path):
    store = SurveyStore(db_path=tmp_path / "s.duckdb", codebook_path=tmp_path / "cb.json")
    info = store.ingest(tiny_sav)
    assert info.num_cases == 6
    assert info.num_variables == 3

    frame = store.frame()
    assert len(frame) == 6
    assert set(frame.columns) >= {"aware_attendo", "experience", "image_word"}
    assert sorted(frame["aware_attendo"].astype(float).unique().tolist()) == [0.0, 1.0]


def test_codebook_persisted(tiny_sav, tmp_path):
    store = SurveyStore(db_path=tmp_path / "s.duckdb", codebook_path=tmp_path / "cb.json")
    store.ingest(tiny_sav)
    cb = store.codebook()
    assert cb.label_of("aware_attendo") == "Tunnetko Attendo"
    assert cb.value_labels("aware_attendo")[1.0] == "Kyllä"


@pytest.fixture
def digit_string_sav(tmp_path):
    """SAV with a numeric column AND a string column whose values are digit-only with leading zeros."""
    df = pd.DataFrame({
        "score": [1.0, 2.0, 3.0],
        "postal_code": ["00100", "00200", "00100"],
    })
    # postal_code must stay object/string dtype so pyreadstat writes it as a string variable
    df["postal_code"] = df["postal_code"].astype(str)
    out = tmp_path / "digit_string.sav"
    pyreadstat.write_sav(
        df,
        str(out),
        column_labels=["Score", "Postal Code"],
        # No value labels for postal_code — keeps it a plain string variable
    )
    return out


def test_leading_zero_string_preserved(digit_string_sav, tmp_path):
    """M4: digit-only string SPSS vars must not be coerced to numeric (leading zeros corrupted)."""
    store = SurveyStore(db_path=tmp_path / "s.duckdb", codebook_path=tmp_path / "cb.json")
    store.ingest(digit_string_sav)
    frame = store.frame()

    # Numeric column must be numeric dtype
    assert pd.api.types.is_numeric_dtype(frame["score"]), "score should be numeric"

    # String column with leading zeros must NOT be coerced — values stay as strings
    postal_values = frame["postal_code"].tolist()
    assert "00100" in postal_values, (
        f"Leading zero lost: expected '00100' in {postal_values}"
    )
    assert 100.0 not in postal_values and 100 not in postal_values, (
        f"postal_code was incorrectly coerced to numeric: {postal_values}"
    )


@pytest.mark.integration
def test_real_attendo_ingest():
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")
    store = SurveyStore(db_path=config.SURVEY_DB, codebook_path=config.CODEBOOK_JSON)
    info = store.ingest(config.ATTENDO_SAV)
    assert info.num_cases == 1001
    assert info.num_variables == 229
    frame = store.frame()
    assert len(frame) == 1001
