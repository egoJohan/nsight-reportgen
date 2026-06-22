from nsight.waves import WaveHistory


def test_store_and_delta(tmp_path):
    wh = WaveHistory(tmp_path / "waves.json")
    wh.set("2025-05", "aided_awareness", "Attendo", 93)
    wh.set("2025-11", "aided_awareness", "Attendo", 92)
    assert wh.get("2025-05", "aided_awareness", "Attendo") == 93
    assert wh.delta(current=92, prior_wave="2025-05", metric="aided_awareness", key="Attendo") == -1
