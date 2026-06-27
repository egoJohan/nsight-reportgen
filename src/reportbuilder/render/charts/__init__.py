"""Self-contained chart plugins — one module per graph style.

Importing this package registers every chart plugin (each module calls
``register(...)`` at import time).  ``render/plugins.py`` imports this package
for that side-effect.  Adding a new graph style = drop a new module here and add
it to the import list below; no generic code changes.
"""
from __future__ import annotations

# Import order = registry/registration order (used for deterministic tie-breaks
# in suggest_chart_type). Keep the canonical chart order.
from reportbuilder.render.charts import vertical_bar          # noqa: F401
from reportbuilder.render.charts import horizontal_bar        # noqa: F401
from reportbuilder.render.charts import stacked_vertical_bar  # noqa: F401
from reportbuilder.render.charts import stacked_horizontal_bar  # noqa: F401
from reportbuilder.render.charts import line                  # noqa: F401
from reportbuilder.render.charts import pie                   # noqa: F401
from reportbuilder.render.charts import doughnut              # noqa: F401
from reportbuilder.render.charts import radar                 # noqa: F401
from reportbuilder.render.charts import scatter               # noqa: F401
from reportbuilder.render.charts import funnel                # noqa: F401
from reportbuilder.render.charts import combo                 # noqa: F401
from reportbuilder.render.charts import wordcloud             # noqa: F401
