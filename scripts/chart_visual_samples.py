"""Render worst-case (longest labels / most categories) charts per type as full
slide PNGs (via LibreOffice) for visual label-overlap inspection. Also a few
synthetic erroneous-data edge cases (very long single word, etc.)."""
import os, sys, tempfile
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.model.report import (
    Report, ChartSpec, NumberFormat, SortSpec, ElementToggles,
)
from reportbuilder.model.question import (
    Question, QuestionModel, Variable, ValueLabel,
)
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.preview import rasterize_pages

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/visual"
os.makedirs(OUT, exist_ok=True)


def spec(ref, ctype, classifying=None):
    return ChartSpec(question_ref=ref, chart_type=ctype, statistic="pct",
                     classifying_var=classifying, number_format=NumberFormat(),
                     sort=SortSpec(basis="pct"), template_slot="s1",
                     elements=ElementToggles(), options={})


def render(model, df, sp, name):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.pptx")
    try:
        build_pptx(Report(name="t", render_mode="image", template_ref="", charts=(sp,)),
                   model, df, p)
        pdf = pptx_to_pdf(p, d)
        pngs = rasterize_pages(pdf, os.path.join(d, "pg"), dpi=110)
        dest = os.path.join(OUT, name + ".png")
        os.replace(pngs[0], dest)
        print("  ok:", dest)
    except Exception as e:
        print("  FAIL:", name, repr(e)[:100])


def main():
    df, model = read_sav("input/spss_FINAL_HolidayClub.sav")
    model = enrich_model(model)
    # classifier for stacked
    classifier = next((v.name for v in model.variables.values()
                       if v.measurement == "categorical" and 2 <= len(v.value_labels) <= 8), None)

    def cats_of(q):
        var = model.variables[q.variables[0]]
        return [vl.label for vl in var.value_labels]

    singles = [q for q in model.questions if q.kind == "single" and len(model.variables[q.variables[0]].value_labels) >= 2]
    multis = [q for q in model.questions if q.kind == "multi"]
    batteries = [q for q in model.questions if q.kind == "battery"]

    def longest_label(qs):
        return max(qs, key=lambda q: max((len(c) for c in cats_of(q)), default=0), default=None)

    def most_cats(qs):
        return max(qs, key=lambda q: len(cats_of(q)), default=None)

    # Per chart type: worst-case from the real data.
    ll = longest_label(singles)
    mc = most_cats(singles)
    if ll:
        render(model, df, spec(ll.qid, "horizontal_bar"), "hbar_longlabels")
        render(model, df, spec(ll.qid, "pie"), "pie_longlabels")
        render(model, df, spec(ll.qid, "doughnut"), "doughnut_longlabels")
    if mc:
        render(model, df, spec(mc.qid, "vertical_bar"), "vbar_manycats")
        render(model, df, spec(mc.qid, "radar"), "radar_manycats")
        render(model, df, spec(mc.qid, "line"), "line_manycats")
        render(model, df, spec(mc.qid, "funnel"), "funnel_manycats")
    if multis:
        m = longest_label(multis) or multis[0]
        render(model, df, spec(m.qid, "horizontal_bar"), "hbar_multi_long")
    if batteries:
        b = longest_label(batteries) or batteries[0]
        render(model, df, spec(b.qid, "horizontal_bar"), "battery_long")
    if ll and classifier:
        render(model, df, spec(ll.qid, "stacked_horizontal_bar", classifier), "stacked_long")

    # Synthetic edge cases: very long single word + very long label.
    longword = "Pitkäsanaverbaalinenkokonaisuusjokaeisanojenvälissärivity" * 2
    syn = QuestionModel(
        variables={"e": Variable(name="e", label="Edge case question?",
                                 measurement="categorical",
                                 value_labels=(ValueLabel(1.0, longword),
                                               ValueLabel(2.0, "Tavallinen lyhyt"),
                                               ValueLabel(3.0, "Toinen erittäin pitkä monisanainen kategoria joka kiertää useammalle riville varmasti")),
                                 missing_values=frozenset())},
        questions=[Question(qid="e", kind="single", variables=("e",), text="Edge?")],
    )
    import pandas as pd
    sdf = pd.DataFrame({"e": [1.0]*40 + [2.0]*35 + [3.0]*25})
    for ct in ("horizontal_bar", "vertical_bar", "pie", "doughnut", "radar", "line", "funnel"):
        render(syn, sdf, spec("e", ct), f"edge_{ct}")


if __name__ == "__main__":
    main()
