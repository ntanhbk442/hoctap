"""Compatibility shim for a pre-release CPython 3.14 build.

pydantic 2.13.5's `_typing_extra._eval_type` calls `typing._eval_type(..., prefer_fwd_module=True)`
on Python >= 3.14 (see pydantic/_internal/_typing_extra.py). Some CPython 3.14 pre-release builds
(observed: 3.14.0rc2) already dropped that parameter from `typing._eval_type`, which makes
`TypeError: _eval_type() got an unexpected keyword argument 'prefer_fwd_module'` on the very
first `import fastapi` -- the whole app and every pydantic model become unimportable.

This drops the unsupported keyword before delegating to the real `typing._eval_type`, only when
the running interpreter actually lacks it. Safe to delete once the pinned Python and pydantic
versions agree on this signature again (an already-current `typing._eval_type` is left untouched).
"""

from __future__ import annotations

import inspect
import typing


def apply() -> None:
    original = typing._eval_type
    try:
        supports_kwarg = "prefer_fwd_module" in inspect.signature(original).parameters
    except (TypeError, ValueError):
        return
    if supports_kwarg:
        return

    def _eval_type(*args: object, **kwargs: object) -> object:
        kwargs.pop("prefer_fwd_module", None)
        return original(*args, **kwargs)

    typing._eval_type = _eval_type


apply()
