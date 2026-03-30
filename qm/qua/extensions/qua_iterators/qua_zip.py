from typing import Any, List, Union, Optional, Sequence, cast

from qm._loc import _get_loc
from qm.exceptions import QmQuaException
from qm.qua._dsl.scope_functions import for_each_
from qm.qua._scope_management._core_scopes import _PythonNativeScope
from qm.qua.extensions.qua_iterators.qua_iterators import QuaIterableBase
from qm.qua.extensions.qua_iterators.qua_iterators_base import IterableBase
from qm.qua.extensions.qua_iterators.qua_native_iterators import NativeIterableBase
from qm.qua.extensions.qua_iterators.qua_iterators_types import (
    QuaNamedTuple,
    MultiIteratorType,
    AnyQuaIterableArrayType,
    MultiIteratorsValuesType,
)


class QuaZip(IterableBase[Any]):
    """
    Combine iterables position-by-position, similarly to Python's built-in
    ``zip``.

    ``QuaZip`` advances multiple iterables together and yields one named tuple
    per position.

    It can zip either QUA iterables or native iterables, but not both in the
    same call. When zipping QUA iterables, the zip is compiled as a single
    [`for_each_`][qm.qua.for_each_] loop. When zipping native iterables,
    iteration happens in Python and stops at the shortest iterable.

    Note:
        Provide iterables with matching lengths so that the zipped values
        represent the same sweep positions.

    Example:
        ```python
        with program() as prog:
            for pair in QuaZip(
                [
                    QuaIterable("amp", [0.2, 0.5, 0.8]),
                    QuaIterable("tau", [16, 32, 64]),
                ]
            ):
                play("x90" * amp(pair.amp), "q1")
                wait(pair.tau)
        ```
    """

    def __init__(self, iterables: Sequence[IterableBase[Any]], name: Optional[str] = None):
        is_qua = [isinstance(itr, QuaIterableBase) for itr in iterables]
        is_native = [isinstance(itr, NativeIterableBase) for itr in iterables]

        self.zip_iterable: Union[QuaZipIterable, NativeZipIterable]
        if all(is_qua):
            self.zip_iterable = QuaZipIterable(cast(Sequence[QuaIterableBase[Any]], iterables), name)
        elif all(is_native):
            self.zip_iterable = NativeZipIterable(cast(Sequence[NativeIterableBase[Any]], iterables), name)
        else:
            raise QmQuaException(
                "QuaZip does not support mixing Qua and Native iterables. " "All iterables must be of the same kind."
            )
        super().__init__(name if name else self.zip_iterable.name)

    @property
    def values(self) -> MultiIteratorsValuesType:
        """Return the underlying values of the zipped iterables."""
        return self.zip_iterable.values

    def __iter__(self) -> MultiIteratorType:
        yield from self.zip_iterable

    @property
    def is_qua_iterable(self) -> bool:
        return self.zip_iterable.is_qua_iterable


class ZipIterableBase(IterableBase[Any]):
    def __init__(self, iterables: Sequence[IterableBase[Any]], name: Optional[str] = None):
        self._iterables = iterables
        self._iterable_names = [itr.name for itr in self._iterables]
        super().__init__(name if name else "_".join(self._iterable_names))

    @property
    def values(self) -> MultiIteratorsValuesType:
        return list(zip(*[itr.values for itr in self._iterables]))


class QuaZipIterable(ZipIterableBase):
    _iterables: Sequence[QuaIterableBase[Any]]

    def __init__(self, iterables: Sequence[QuaIterableBase[Any]], name: Optional[str]):
        super().__init__(iterables, name)

    def __iter__(self) -> MultiIteratorType:
        qua_vars = [itr.declare_var() for itr in self._iterables]
        qua_values = [itr.values for itr in self._iterables]
        with (for_each_(qua_vars, cast(List[AnyQuaIterableArrayType], qua_values))):
            self._add_to_current_scope()
            yield QuaNamedTuple(self._iterable_names, qua_vars)
            self._set_averaged_streams()

    @property
    def is_qua_iterable(self) -> bool:
        return True


class NativeZipIterable(ZipIterableBase):
    def __init__(self, iterables: Sequence[NativeIterableBase[Any]], name: Optional[str]):
        super().__init__(iterables, name)

    def __iter__(self) -> MultiIteratorType:
        native_scope = _PythonNativeScope(_get_loc())
        with (native_scope):
            self._add_to_current_scope()
            for i, args in enumerate(zip(*[itr.values for itr in self._iterables])):
                native_scope.set_current_iteration_number(i)
                yield QuaNamedTuple(self._iterable_names, args)
