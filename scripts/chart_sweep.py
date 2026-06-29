"""No-LLM error sweep: render every question x every applicable chart type across
all input SAVs via build_pptx (no LibreOffice). Reports any failure."""
import os, sys, tempfile, traceback
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.model.report import (
    Report, ChartSpec, NumberFormat, SortSpec, ElementToggles,
)
from reportbuilder.export.pptx_build import build_pptx

SAVS = [
    "input/spss_FINAL_HolidayClub.sav",
    "input/spss AttendoSuomi-Brandiseuranta_112025.sav",
    "input/spss Synsam_segmenteillä_vainvalittu_segmmalli.sav",
]
ALL_TYPES = ["vertical_bar", "horizontal_bar", "stacked_vertical_bar",
             "stacked_horizontal_bar", "line", "pie", "doughnut", "radar",
             "funnel", "combo", "wordcloud"]


def spec(ref, ctype, statistic="pct", classifying=None, scatter=None, options=None):
    return ChartSpec(
        question_ref=ref, chart_type=ctype, statistic=statistic,
        classifying_var=classifying, number_format=NumberFormat(),
        sort=SortSpec(basis="pct"), template_slot="s1", elements=ElementToggles(),
        scatter_xy=scatter, options=options or {},
    )


def main():
    failures = []
    total = 0
    for sav in SAVS:
        df, model = read_sav(sav)
        model = enrich_model(model)
        # a low-cardinality categorical classifier for stacked charts
        classifier = None
        for v in model.variables.values():
            if v.measurement == "categorical" and 2 <= len(v.value_labels) <= 12:
                classifier = v.name
                break
        # an aggregatable secondary for combo
        import re
        secondary = None
        for v in model.variables.values():
            vls = v.value_labels
            if vls and sum(1 for x in vls if re.match(r"^\s*\d", x.label or "")) >= len(vls) * 0.6:
                secondary = v.name
                break
        for q in model.questions:
            is_text = all(model.variables[n].measurement == "text" for n in q.variables)
            types = ["wordcloud"] if is_text else [t for t in ALL_TYPES if t != "wordcloud"]
            for ct in types:
                kw = {}
                if ct in ("stacked_vertical_bar", "stacked_horizontal_bar"):
                    if not classifier:
                        continue
                    kw["classifying"] = classifier
                if ct == "combo" and secondary:
                    kw["options"] = {"combo_secondary": secondary}
                total += 1
                out = os.path.join(tempfile.gettempdir(), "sweep.pptx")
                try:
                    build_pptx(Report(name="t", render_mode="image", template_ref="",
                                      charts=(spec(q.qid, ct, **kw),)), model, df, out)
                except Exception as e:
                    failures.append((os.path.basename(sav), q.qid, ct, repr(e)))
    print(f"Rendered {total} (question x chart_type) combos.")
    print(f"FAILURES: {len(failures)}")
    for sav, qid, ct, err in failures[:60]:
        print(f"  {sav} | {qid} | {ct} | {err[:120]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
