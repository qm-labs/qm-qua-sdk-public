from typing import Any, Optional, overload

import numpy as np

from qm._loc import _get_loc
from qm.exceptions import QmQuaException
from qm.type_hinting.general import Number
from qm.qua._scope_management._core_scopes import _PythonNativeScope
from qm.qua.extensions.qua_iterators.qua_iterators_base import IterableBase
from qm.qua.extensions.qua_iterators.qua_iterators_types import V, MetaDataType, NativeArrayType, NativeIteratorType


class NativeIterableBase(IterableBase[V]):
    def __init__(self, name: str, metadata: Optional[MetaDataType]):
        super().__init__(name, metadata)
        self._create_native_scope = True

    def __iter__(self) -> NativeIteratorType[V]:
        native_scope = _PythonNativeScope(_get_loc())
        with native_scope:
            self._add_to_current_scope()
            for i, v in enumerate(self.values):
                native_scope.set_current_iteration_number(i)
                yield v


class NativeIterableRange(NativeIterableBase[Any]):
    """
    Python-side range iterator.

    Use this helper for sweep dimensions that should stay in Python, for
    example when choosing configuration variants or element names around QUA
    code. No QUA variable is declared; the yielded value is a Python value.

    Use ``NativeIterableRange`` instead of a plain Python iterator when the
    Python-side axis should still participate in Sweep Program composition. The
    iterable name is preserved, so the axis can be combined inside
    [QuaProduct][qm.qua.extensions.qua_iterators.QuaProduct] or
    [QuaZip][qm.qua.extensions.qua_iterators.QuaZip], and its current value can
    be reflected in generated stream names by
    [declare_with_stream][qm.qua.declare_with_stream].

    ``NativeIterableRange(name, stop)`` behaves like ``range(stop)``.
    ``NativeIterableRange(name, start, stop, step)`` behaves like
    ``range(start, stop, step)`` for integers and like
    ``numpy.arange(start, stop, step)`` for floats. ``stop`` is exclusive.

    Example:
        ```python
        with program() as prog:
            for amp_scale in NativeIterableRange("amp_scale", 0.1, 1.0, 0.05):
                play("pulse" * amp(amp_scale), "element")
        ```

        This is equivalent to:

        ```python
        with program() as prog:
            for amp_scale in np.arange(0.1, 1.0, 0.05):
                play("pulse" * amp(amp_scale), "element")
        ```
    """

    @overload
    def __init__(self, name: str, stop: int, *, metadata: Optional[MetaDataType] = None):
        """
        support range(5)
        """
        ...

    @overload
    def __init__(
        self, name: str, start: Number, stop: Number, step: Number = 1, *, metadata: Optional[MetaDataType] = None
    ):
        ...

    def __init__(self, name: str, *args: Number, metadata: Optional[MetaDataType] = None):  # type: ignore[misc]
        super().__init__(name, metadata)
        self._start: Number
        self._stop: Number
        self._step: Number = 1

        if len(args) == 1:
            self._stop = args[0]
            self._start = 0
        elif len(args) == 2:
            self._start, self._stop = args
        elif len(args) == 3:
            self._start, self._stop, self._step = args
        else:
            raise QmQuaException(f"not supported args len = {len(args)}")

    @property
    def values(self) -> NativeArrayType:
        """
        Return the Python values represented by this iterable.
        """
        return np.arange(self._start, self._stop, self._step).tolist()


class NativeIterable(NativeIterableBase[Any]):
    """
    Python-side iterable over explicit values.

    Use this helper for loops that choose Python values such as element names,
    labels, or configuration variants. No QUA variable is declared; the yielded
    value is a Python value.

    Use ``NativeIterable`` instead of a plain Python iterator when the
    Python-side axis should still participate in Sweep Program composition. The
    iterable name is preserved, so the axis can be combined inside
    [QuaProduct][qm.qua.extensions.qua_iterators.QuaProduct] or
    [QuaZip][qm.qua.extensions.qua_iterators.QuaZip], and its current value can
    be reflected in generated stream names by
    [declare_with_stream][qm.qua.declare_with_stream].

    Example:
        ```python
        with program() as prog:
            for element in NativeIterable("element", ["q1", "q2"]):
                play("x180", element)
        ```

        This is equivalent to:

        ```python
        with program() as prog:
            for element in ["q1", "q2"]:
                play("x180", element)
        ```
    """

    def __init__(self, name: str, array: NativeArrayType, *, metadata: Optional[MetaDataType] = None):
        super().__init__(name, metadata)
        self._array: NativeArrayType = array

    @property
    def values(self) -> NativeArrayType:
        """
        Return the Python values represented by this iterable.
        """
        return self._array
