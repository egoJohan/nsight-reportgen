from nsight.fidelity.extract import extract_deck


def test_extract_reads_chart_values(chart_pptx):
    deck = extract_deck(chart_pptx)
    s0 = deck.slides[0]
    assert s0.charts[0].categories == ["Attendo", "Esperi"]
    assert s0.charts[0].series["Series 1"] == [0.1, 0.2]
