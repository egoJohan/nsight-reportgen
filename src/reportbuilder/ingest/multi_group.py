from __future__ import annotations
import re
from collections import OrderedDict
from reportbuilder.model.question import QuestionModel, Variable

_SUFFIX = re.compile(r"O?\d+$")

def _prefix(name: str) -> str:
    return _SUFFIX.sub("", name)

def _is_binary(var: Variable) -> bool:
    codes = {vl.value for vl in var.value_labels}
    return bool(codes) and codes <= {0.0, 1.0}

def suggest_multi_groups(model: QuestionModel) -> list[tuple[str, ...]]:
    """Group variables sharing a name prefix that look like a 0/1 tickbox grid.
    A group needs >=2 members all carrying a value-label set subset of {0,1}.
    Returns groups in file (insertion) order. (REQ-M-02, R2)"""
    buckets: "OrderedDict[str, list[str]]" = OrderedDict()
    for name, var in model.variables.items():
        if not _is_binary(var):
            continue
        buckets.setdefault(_prefix(name), []).append(name)
    return [tuple(members) for members in buckets.values() if len(members) >= 2]
