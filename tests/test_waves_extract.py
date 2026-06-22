import pytest

from nsight import config
from nsight.waves import WaveHistory


@pytest.mark.integration
def test_waves_extract_aided_awareness():
    if not config.ATTENDO_TEMPLATE.exists():
        pytest.skip("Attendo template not present")

    # Ensure waves.json is produced from the deck.
    if WaveHistory(config.WAVES_JSON).get("Marraskuu 2025", "aided_awareness", "Attendo") is None:
        import sys

        sys.path.insert(0, str(config.ROOT))
        import scripts.extract_waves as extract_waves

        extract_waves.main()

    history = WaveHistory(config.WAVES_JSON)

    # Current wave spot-check (matches DECK_AIDED_AWARENESS["Attendo"]).
    assert history.get("Marraskuu 2025", "aided_awareness", "Attendo") == 86

    # A prior wave has an Attendo value present as an int.
    prior = history.get("Toukokuu 2025", "aided_awareness", "Attendo")
    assert isinstance(prior, int)
