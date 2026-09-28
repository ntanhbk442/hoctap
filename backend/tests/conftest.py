"""Applies the Python 3.14 pre-release compat shim before any test module runs.

Some test modules import `fastapi` directly, before importing anything from `hoctap` --
importing `hoctap` here first (pytest always loads `conftest.py` before collecting test
modules in its directory) makes sure the shim in `hoctap/_py314_compat.py` is active first.
"""

import hoctap  # noqa: F401 -- import for its side effect
