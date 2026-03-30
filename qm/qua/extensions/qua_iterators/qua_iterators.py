from abc import ABC
from typing import Type, Optional, cast, overload

import numpy as np

from qm.exceptions import QmQuaException
from qm.type_hinting.general import Number
from qm.qua._expressions import QuaVariable
from qm.qua._dsl.variable_handling import declare
from qm.qua._dsl.scope_functions import for_, for_each_
from qm.qua.extensions.qua_iterators.qua_iterators_base import IterableBase
from qm.qua.extensions.qua_iterators.qua_iterators_types import (
    T,
    MetaDataType,
    QuaIteratorType,
    QuaIterableArrayType,
    QuaIterableArrayInput,
    QuaIterableArrayInputInt,
    QuaIterableArrayInputFloat,
)

FIXED_TYPE_TOLERANCE = 1e-10


class QuaIterableBase(IterableBase[T], ABC):
    def __init__(
        self,
        name: str,
        dtype: Type[T],
        metadata: Optional[MetaDataType],
    ):
        super().__init__(name, metadata)
        self._dtype: Type[T] = dtype

    @property
    def dtype(self) -> Type[T]:
        """
        Type of the QUA variable declared for this iterable.
        """
        return self._dtype

    def declare_var(self) -> QuaVariable[T]:
        """
        Declare the QUA variable used by this iterable.
        """
        return declare(self._dtype)

    @property
    def is_qua_iterable(self) -> bool:
        return True


class QuaIterableRange(QuaIterableBase[T]):
    """
    QUA-side range iterator.

    Use this helper when a sweep axis should execute on the QOP as a
    [`for_`][qm.qua.for_] loop rather than in Python.

    ``QuaIterableRange(name, stop)`` behaves like ``range(stop)``.
    ``QuaIterableRange(name, start, stop, step)`` behaves like
    ``range(start, stop, step)`` for integers and like
    ``numpy.arange(start, stop, step)`` for floats. ``stop`` is exclusive.

    The yielded value is a QUA variable, not a Python scalar.

    For floating-point ranges, the internal stop value may be adjusted slightly
    to avoid fixed-point boundary issues in the generated loop.

    Example:
        ```python
        with program() as prog:
            for amp_scale in QuaIterableRange("amp_scale", 0.1, 1.0, 0.05):
                play("pulse" * amp(amp_scale), "element")
        ```

        This is equivalent to:

        ```python
        with program() as prog:
            amp_scale = declare(fixed)
            with for_(amp_scale, 0.1, amp_scale < 1.0, amp_scale + 0.05):
                play("pulse" * amp(amp_scale), "element")
        ```
    """

    @overload
    def __init__(self: "QuaIterableRange[int]", name: str, stop: int, *, metadata: Optional[MetaDataType] = None):
        """
        support range(5)
        """
        ...

    @overload
    def __init__(
        self: "QuaIterableRange[int]",
        name: str,
        start: int,
        stop: int,
        step: int = 1,
        *,
        metadata: Optional[MetaDataType] = None,
    ):
        ...

    @overload
    def __init__(
        self: "QuaIterableRange[float]",
        name: str,
        start: Number,
        stop: Number,
        step: Number = 1,
        *,
        metadata: Optional[MetaDataType] = None,
    ):
        ...

    def __init__(self, name: str, /, *args: Number, metadata: Optional[MetaDataType] = None):  # type: ignore[misc]
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

        if isinstance(self._start, float) or isinstance(self._stop, float) or isinstance(self._step, float):
            self._start = float(self._start)
            self._stop = float(self._stop)
            self._step = float(self._step)
            # because of fixed point accuracy issues change stop in case its start + step * n == stop
            if self._start + (len(self.values)) * self._step >= self._stop - FIXED_TYPE_TOLERANCE:
                self._stop = self._stop - self._step / 2

            # Mypy doesn't propagate the self-type from overloads into the implementation
            # body, so it can't verify float/int matches T.
            # The overloads guarantee T matches the arg types at the call site.
            super().__init__(name, float, metadata)  # type: ignore[arg-type]
        else:
            self._start = int(self._start)
            self._stop = int(self._stop)
            self._step = int(self._step)
            super().__init__(name, int, metadata)  # type: ignore[arg-type]

    @property
    def values(self) -> QuaIterableArrayType[T]:
        """
        Return the Python values represented by this iterable.
        """
        return np.arange(self._start, self._stop, self._step).tolist()  # type: ignore[return-value]

    def __iter__(self) -> QuaIteratorType[T]:
        var = self.declare_var()

        with for_(var, self._start, var < self._stop, var + self._step):  # type: ignore[operator]
            self._add_to_current_scope()
            yield var
            self._set_averaged_streams()


class QuaIterable(QuaIterableBase[T]):
    """
    QUA-side iterable over an explicit sequence of numeric values.

    Use this helper when a sweep axis should execute on the QOP rather than in
    Python.

    If the values are uniformly spaced, the iterator may be optimized to a
    [`for_`][qm.qua.for_] loop. Otherwise it is compiled as a
    [`for_each_`][qm.qua.for_each_] loop.

    Integer sequences produce integer QUA variables. Any non-integer values are
    converted to float.

    The yielded value is a QUA variable, not a Python scalar.

    Example:
        ```python
        with program() as prog:
            for amp_scale in QuaIterable("amp_scale", np.linspace(0.1, 0.6, 10)):
                play("pulse" * amp(amp_scale), "element")
        ```

        This is equivalent to:

        ```python
        with program() as prog:
            amp_scale = declare(fixed)
            with for_each_(amp_scale, np.linspace(0.1, 0.6, 10)):
                play("pulse" * amp(amp_scale), "element")
        ```
    """

    @overload
    def __init__(
        self: "QuaIterable[int]",
        name: str,
        array: QuaIterableArrayInputInt,
        *,
        metadata: Optional[MetaDataType] = None,
    ):
        ...

    @overload
    def __init__(
        self: "QuaIterable[float]",
        name: str,
        array: QuaIterableArrayInputFloat,
        *,
        metadata: Optional[MetaDataType] = None,
    ):
        ...

    def __init__(
        self,
        name: str,
        array: QuaIterableArrayInput,
        *,
        metadata: Optional[MetaDataType] = None,
    ):
        raw_array = array.tolist() if isinstance(array, np.ndarray) else list(array)
        dtype: type = int if all([type(v) == int for v in raw_array]) else float
        if dtype is float:
            self._array: QuaIterableArrayType[T] = cast(QuaIterableArrayType[T], [float(v) for v in raw_array])
            # Mypy doesn't propagate the self-type from overloads into the implementation
            # body, so it can't verify float/int matches T.
            # The overloads guarantee T matches the arg types at the call site.
            super().__init__(name, float, metadata)  # type: ignore[arg-type]
        else:
            self._array = cast(QuaIterableArrayType[T], [int(v) for v in raw_array])
            super().__init__(name, int, metadata)  # type: ignore[arg-type]

        self._qua_range_itr: Optional[QuaIterableRange[T]] = None
        # according to dtype set the minimum step that can be done
        minimum_step = FIXED_TYPE_TOLERANCE if dtype is float else 1
        first_step = array[1] - array[0]
        # in case all steps in the array are up < minimum steps than we can use for.
        # the reason to use this approach is that if array is created by linspace and his likes the steps won't be ==
        optimize_to_for = all(
            [abs((array[i + 1] - array[i]) - first_step) < minimum_step for i in range(len(array) - 1)]
        )

        if optimize_to_for:
            range_itr: QuaIterableRange[T] = QuaIterableRange(  # type: ignore[assignment]
                name, array[0], array[-1] + first_step, first_step, metadata=metadata
            )
            # checking that optimization succeeded
            if range_itr.buffer_size == self.buffer_size:
                self._qua_range_itr = range_itr

    @property
    def values(self) -> QuaIterableArrayType[T]:
        """
        Return the Python values represented by this iterable.
        """
        return self._array

    def __iter__(self) -> QuaIteratorType[T]:
        # in case exist equivalent qua range itr iterate over it for optimization purposes
        if self._qua_range_itr is not None:
            yield from self._qua_range_itr
        else:
            var = self.declare_var()

            with for_each_(var, self._array):
                self._add_to_current_scope()
                yield var
                self._set_averaged_streams()

    def is_stream_averaged(self, stream_name: str) -> bool:
        """
        Check if stream is averaged on this iterable
        """
        if self._qua_range_itr is not None:
            return self._qua_range_itr.is_stream_averaged(stream_name)
        else:
            return super().is_stream_averaged(stream_name)
