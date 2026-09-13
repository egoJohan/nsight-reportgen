"""Make `acceptance/` importable from its own tests.

Running `pytest acceptance/tests` from the repo root picks up the root config,
which puts `src` on the path but knows nothing about this directory — so
`import oracles` would fail. `acceptance/run` does the same insert for itself.
"""
from __future__ import annotations

import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
