"""Deprecated module path.

This module was renamed to
:mod:`qm.qua.extensions.qua_iterators.qua_python_iterators`. It is kept as a
backward-compatible shim and will be removed in a future release. Import from
the new module instead.
"""
from qm.utils.deprecation_utils import throw_warning, deprecation_message
from qm.qua.extensions.qua_iterators.qua_python_iterators import (  # noqa: F401
    NativeIterable,
    PythonIterableBase,
    NativeIterableRange,
)

# Backward-compatible alias for the renamed base class. Kept (without a runtime
# warning) mainly for existing ``isinstance`` checks against the old name.
NativeIterableBase = PythonIterableBase

throw_warning(
    deprecation_message(
        "The qm.qua.extensions.qua_iterators.qua_native_iterators module",
        "1.3.0",
        "2.0.0",
        "Import from qm.qua.extensions.qua_iterators.qua_python_iterators instead.",
    ),
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "NativeIterableBase",
    "NativeIterable",
    "NativeIterableRange",
]
