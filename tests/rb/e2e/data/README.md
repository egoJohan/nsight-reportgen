# e2e SAV test data (local only — gitignored)

The demo-group e2e (`@pytest.mark.demo`) renders total-only stacked bars over the
three current client SAVs. These are **client IPR** and must never be committed;
this directory is gitignored.

Populate it locally from the tracked `input/` copies:

    mkdir -p tests/rb/e2e/data/sav
    cp "input/spss_FINAL_HolidayClub.sav" tests/rb/e2e/data/sav/
    cp "input/spss AttendoSuomi-Brandiseuranta_112025.sav" tests/rb/e2e/data/sav/
    cp "input/spss Synsam_segmenteillä_vainvalittu_segmmalli.sav" tests/rb/e2e/data/sav/

If absent, the demo-group tests skip cleanly. Run the group with:

    NSIGHT_DEMO=1 python -m pytest tests/rb/e2e -m demo -v
