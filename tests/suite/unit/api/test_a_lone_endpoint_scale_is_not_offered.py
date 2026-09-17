"""A variable is only offered as a battery member if something corroborates it.

`scale_levels(var, df)` learned to read a rating off the data when only the ends
are labelled — the shape a brand-image battery exports as. It cannot tell that
shape from a partially-labelled CATEGORICAL, because on the data they are
identical: "Asuinalue" coded 1..5 with labels on `1 = Etelä-Suomi` and
`5 = Lappi` produces the same five points, and the same `scale_compat_key`
(`1.0|2.0|3.0|4.0|5.0`), as a genuine 1..5 satisfaction rating. The grouping
dialog therefore offered "Group as battery" for region + satisfaction, and
answered with a mean Asuinalue of 3.0 — the average region.

No rule over ONE variable can separate them; the data really is the same. What
separates them is that a battery has PARALLEL MEMBERS. Five brand attributes
share an identical endpoint-label signature with each other; a lone region
variable shares its with nothing.

So a scale inferred from endpoint labels alone must be corroborated by at least
one other variable carrying the same signature before it is OFFERED for
grouping. Charting is untouched: once an author has formed a battery, every path
reads its scale from the data as before (see
test_endpoint_scale_reaches_every_path). Offering is where the mistake was
invited, and offering is what this narrows. (Johan, 2026-09-17)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reportbuilder.model.question import ValueLabel, Variable
from reportbuilder.api.routes_questions import _groupable_scale_rows

pytestmark = pytest.mark.unit

RATING_ENDS = (ValueLabel(1.0, "Erittäin huonosti"), ValueLabel(5.0, "Erittäin hyvin"))
REGION_ENDS = (ValueLabel(1.0, "Etelä-Suomi"), ValueLabel(5.0, "Lappi"))
FULL = tuple(ValueLabel(float(i), f"Taso {i}") for i in range(1, 6))


def _var(name, labels):
    return Variable(name, name, "categorical", tuple(labels), frozenset())


def _df(names):
    rng = np.random.default_rng(3)
    return pd.DataFrame({n: rng.choice([1.0, 2.0, 3.0, 4.0, 5.0], size=200)
                         for n in names})


def _scales(vars_):
    """{name: is offered as a groupable scale}."""
    df = _df([v.name for v in vars_])
    return {name: bool(row["scale"])
            for name, row in _groupable_scale_rows(vars_, df).items()}


def test_a_lone_partially_labelled_categorical_is_not_a_scale():
    """The defect: region joined the battery pool."""
    vars_ = [_var("Asuinalue", REGION_ENDS),
             _var("Tyytyvaisyys", RATING_ENDS)]
    assert _scales(vars_)["Asuinalue"] is False


def test_a_lone_rating_is_not_offered_either():
    """Symmetrical, deliberately. The rule cannot read the WORDS — it would have
    to know that "Lappi" is a place and "Erittäin hyvin" is not — so a single
    endpoint-labelled variable of either kind waits for a sibling. A battery of
    one was never something to offer."""
    vars_ = [_var("Asuinalue", REGION_ENDS),
             _var("Tyytyvaisyys", RATING_ENDS)]
    assert _scales(vars_)["Tyytyvaisyys"] is False


def test_the_reported_battery_is_still_offered():
    """Five brand attributes, each labelled only at its ends — the case the
    endpoint rule was added for. Each corroborates the others."""
    attrs = ["Luotettava", "Viihdyttävä", "Edelläkävijä", "Ammattitaitoinen",
             "Palveleva"]
    vars_ = [_var(a, RATING_ENDS) for a in attrs] + [_var("Asuinalue", REGION_ENDS)]
    offered = _scales(vars_)
    assert all(offered[a] for a in attrs), offered
    assert offered["Asuinalue"] is False


def test_two_siblings_are_enough():
    vars_ = [_var("Brand_A", RATING_ENDS), _var("Brand_B", RATING_ENDS)]
    assert all(_scales(vars_).values())


def test_a_fully_labelled_scale_never_needs_corroboration():
    """A scale that states itself does not depend on having siblings — that was
    true before any of this and must stay true, or a single rating question
    stops being groupable at all."""
    vars_ = [_var("Tyytyvaisyys", FULL), _var("Asuinalue", REGION_ENDS)]
    offered = _scales(vars_)
    assert offered["Tyytyvaisyys"] is True and offered["Asuinalue"] is False


def test_a_demoted_variable_carries_no_keys():
    """Leaving the keys behind would put it back in the pool: the dialog groups
    on `scale_compat_key ?? scale_key`, not on the `scale` flag."""
    vars_ = [_var("Asuinalue", REGION_ENDS), _var("Tyytyvaisyys", RATING_ENDS)]
    row = _groupable_scale_rows(vars_, _df(["Asuinalue", "Tyytyvaisyys"]))["Asuinalue"]
    assert row["scale_key"] is None and row["scale_compat_key"] is None
