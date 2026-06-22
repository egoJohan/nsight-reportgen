import json
from nsight.codebook import Codebook


def _cb(tmp_path):
    p = tmp_path / "cb.json"
    p.write_text(json.dumps({
        "columns": ["aware_attendo", "q5"],
        "labels": {"aware_attendo": "Tunnetko Attendo", "q5": "Yleinen käsitys"},
        "value_labels": {"aware_attendo": {"1.0": "Kyllä", "0.0": "Ei"}},
        "measure": {"aware_attendo": "nominal"},
        "missing_ranges": {},
        "var_types": {"aware_attendo": "double", "q5": "string"},
    }, ensure_ascii=False))
    return Codebook.load(p)


def test_label_and_value_labels(tmp_path):
    cb = _cb(tmp_path)
    assert cb.label_of("aware_attendo") == "Tunnetko Attendo"
    assert cb.value_labels("aware_attendo")[1.0] == "Kyllä"


def test_find_by_label_substring(tmp_path):
    cb = _cb(tmp_path)
    assert cb.find_by_label("yleinen käsitys") == ["q5"]


def test_var_types_and_type_of(tmp_path):
    cb = _cb(tmp_path)
    assert cb.type_of("aware_attendo") == "double"
    assert cb.type_of("q5") == "string"
    assert cb.type_of("nonexistent") == ""
