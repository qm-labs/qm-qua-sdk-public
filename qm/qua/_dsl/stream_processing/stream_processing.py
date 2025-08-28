import abc
import warnings
import dataclasses
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Sequence
from typing import Iterable as IterableClass
from typing import List, Tuple, Union, Literal

import numpy as np
from betterproto.lib.std.google.protobuf import Value, ListValue

from qm._loc import _get_loc
from qm.type_hinting import Number
from qm.exceptions import QmQuaException
from qm.qua._dsl._type_hints import OneOrMore
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.grpc.qua import QuaProgramAnyStatement, QuaProgramSaveStatement
from qm.qua._expressions import ScalarOfAnyType, create_qua_scalar_expression
from qm.qua._dsl.stream_processing.stream_processing_utils import _ARRAY_SYMBOL, create_array
from qm.qua._dsl.stream_processing.map_functions.map_function_classes import (
    FFT,
    DotProduct,
    Convolution,
    BooleanToInt,
    FunctionBase,
    TupleMultiply,
    ConvolutionMode,
    TupleDotProduct,
    MultiplyByScalar,
    MultiplyByVector,
    TupleConvolution,
)


class ResultStream(metaclass=abc.ABCMeta):
    def average(self) -> "UnaryMathOperation":
        """
        Perform a running average on a stream item. The Output of this operation is the running average
        of the values in the stream starting from the beginning of the QUA program.
        """
        return UnaryMathOperation(self, "average")

    def real(self) -> "UnaryMathOperation":
        return UnaryMathOperation(self, "real")

    def image(self) -> "UnaryMathOperation":
        return UnaryMathOperation(self, "image")

    def buffer(self, *args: int) -> "BufferOfStream":
        """Gather items into vectors - creates an array of input stream items and outputs the array as one item.
        only outputs full buffers.

        Note:
            The order of resulting dimensions is different when using a buffer with multiple inputs compared to using
            multiple buffers. The following two lines are equivalent:
            ```python
            stream.buffer(n, l, k)
            stream.buffer(k).buffer(l).buffer(n)
            ```

        Args:
            *args: number of items to gather, can either be a single
                number, which gives the results as a 1d array or
                multiple numbers for a multidimensional array.
        """
        return BufferOfStream(self, *args)

    def buffer_and_skip(self, length: Number, skip: Number) -> "SkippedBufferOfStream":
        """Gather items into vectors - creates an array of input stream items and outputs
        the array as one item.
        Skips the number of given elements. Note that length and skip start from the
        same index, so the `buffer(n)` command is equivalent to `buffer_and_skip(n, n)`.

        Only outputs full buffers.

        Example:
            ```python
            # The stream input is [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]
            with stream_processing():
                stream.buffer(3).save_all("example1")
                stream.buffer_and_skip(3, 3).save_all("example2")
                stream.buffer_and_skip(3, 2).save_all("example3")
                stream.buffer_and_skip(3, 5).save_all("example4")
            # example1 -> [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
            # example2 -> [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
            # example3 -> [[1, 2, 3], [3, 4, 5], [5, 6, 7], [7, 8, 9]]
            # example4 -> [[1, 2, 3], [6, 7, 8]]
            ```
        Args:
            length: number of items to gather
            skip: number of items to skip for each buffer, starting from
                the same index as length
        """
        return SkippedBufferOfStream(self, int(length), int(skip))

    def map(self, function: FunctionBase) -> "MapOfStream":
        """Transform the item by applying a
        [function][qm.qua._dsl.stream_processing.map_functions.map_functions.MapFunctions] to it

        Args:
            function: a function to transform each item to a different
                item. For example, to compute an average between
                elements in a buffer you should write
                ".buffer(len).map(FUNCTIONS.average())"
        """
        return MapOfStream(self, function)

    def flatten(self) -> "UnaryMathOperation":
        """
        Deconstruct an array item - and send its elements one by one as items
        """
        return UnaryMathOperation(self, "flatten")

    def skip(self, length: Number) -> "DiscardedStream":
        """Suppress the first n items of the stream

        Args:
            length: number of items to skip
        """
        return DiscardedStream(self, int(length), "skip")

    def skip_last(self, length: Number) -> "DiscardedStream":
        """Suppress the last n items of the stream

        Args:
            length: number of items to skip
        """
        return DiscardedStream(self, int(length), "skipLast")

    def take(self, length: Number) -> "DiscardedStream":
        """Outputs only the first n items of the stream

        Args:
            length: number of items to take
        """
        return DiscardedStream(self, int(length), "take")

    def histogram(self, bins: List[List[Number]]) -> "HistogramStream":
        """Compute the histogram of all items in stream

        Args:
            bins: vector or pairs. each pair indicates the edge of each
                bin. example: [[1,10],[11,20]] - two bins, one between 1
                and 10, second between 11 and 20
        """
        standardized_bins = [(_bin[0], _bin[1]) for _bin in bins]
        return HistogramStream(self, standardized_bins)

    def zip(self, other: "ResultStream") -> "BinaryOperation":
        """Combine the emissions of two streams to one item that is a tuple of items of input streams

        Args:
            other: second stream to combine with self
        """
        return BinaryOperation(other, self, "zip")

    def save_all(self, tag: str) -> None:
        """Save all items received in stream.

        Args:
            tag: result name
        """
        scopes_manager.append_output_stream(_SaveAllOutputStream(self, tag))

    def save(self, tag: str) -> None:
        """Save only the last item received in stream

        Args:
            tag: result name
        """
        scopes_manager.append_output_stream(_SaveOutputStream(self, tag))

    def _auto_save_all(self, tag: str) -> None:
        """Save all items received in stream.

        Args:
            tag: result name
        """
        scopes_manager.append_output_stream(_AutoSaveAllOutputStream(self, tag))

    def dot_product(self, vector: Sequence[Number]) -> "MapOfStream":
        """Computes dot product of the given vector and each item of the input stream

        Args:
            vector: constant vector of numbers
        """
        return self.map(DotProduct(vector))

    def tuple_dot_product(self) -> "MapOfStream":
        """
        Computes dot product of the given item of the input stream - that should include two vectors
        """
        return self.map(TupleDotProduct())

    def multiply_by(self, scalar_or_vector: OneOrMore[Number]) -> "MapOfStream":
        """Multiply the input stream item by a constant scalar or vector.
        The input item can be either scalar or vector.

        Args:
            scalar_or_vector: either a scalar number, or a vector of
                scalars.
        """
        if isinstance(scalar_or_vector, IterableClass):
            return self.map(MultiplyByVector(scalar_or_vector))
        else:
            return self.map(MultiplyByScalar(scalar_or_vector))

    def tuple_multiply(self) -> "MapOfStream":
        """
        Computes multiplication of the given item of the input stream - that can be any
        combination of scalar and vectors.
        """
        return self.map(TupleMultiply())

    def convolution(self, constant_vector: Sequence[Number], mode: Optional[ConvolutionMode] = "") -> "MapOfStream":
        """Computes discrete, linear convolution of one-dimensional constant vector and one-dimensional vector
        item of the input stream.

        Args:
            constant_vector: vector of numbers
            mode: "full", "same" or "valid"
        """
        if mode is None:
            warnings.warn(
                "mode=None is deprecated, use empty-string or (recommended) don't write the mode at-all.",
                DeprecationWarning,
            )
            mode = ""
        return self.map(Convolution(constant_vector, mode))

    def tuple_convolution(self, mode: Optional[ConvolutionMode] = "") -> "MapOfStream":
        """Computes discrete, linear convolution of two one-dimensional vectors that received as the one item from the input stream

        Args:
            mode: "full", "same" or "valid"
        """
        if mode is None:
            warnings.warn(
                "mode=None is deprecated, use empty-string or (recommended) don't write the mode at-all.",
                DeprecationWarning,
            )
            mode = ""
        return self.map(TupleConvolution(mode))

    def fft(self, output: Optional[str] = None) -> "MapOfStream":
        """Computes one-dimensional discrete fourier transform for every item in the
        stream.
        Item can be a vector of numbers, in this case fft will assume all imaginary
        numbers are 0.
        Item can also be a vector of number pairs - in this case for each pair - the
        first will be real and second imaginary.

        Args:
            output: supported from QOP 1.30 and QOP 2.0, options are
                "normal", "abs" and "angle":

                *   "normal" - Same as default (none), returns a 2d array of
                    size Nx2, where N is the length of the original vector.
                    The first item in each pair is the real part, and the 2nd
                    is the imaginary part.
                *   "abs" - Returns a 1d array of size N with the abs of the fft.
                *   "angle" - Returns the angle between the imaginary and real
                    parts in radians.

        Returns:
            stream object
        """
        return self.map(FFT(output))

    def boolean_to_int(self) -> "MapOfStream":
        """
        converts boolean to an integer number - 1 for true and 0 for false
        """
        return self.map(BooleanToInt())

    def to_proto(self) -> Value:
        return Value(list_value=ListValue(values=list(self._to_list_of_values())))

    @abc.abstractmethod
    def _to_list_of_values(self) -> Sequence[Value]:
        pass

    def add(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        """Allows addition between streams. The addition is done element-wise.
        Can also be performed on buffers and other operators, but they must have the
        same dimensions.

        Example:
            ```python
            i = declare(int)
            j = declare(int)
            k = declare(int, value=5)
            stream = declare_stream()
            stream2 = declare_stream()
            stream3 = declare_stream()
            with for_(j, 0, j < 30, j + 1):
                with for_(i, 0, i < 10, i + 1):
                    save(i, stream)
                    save(j, stream2)
                    save(k, stream3)

            with stream_processing():
                (stream1 + stream2 + stream3).save_all("example1")
                (stream1.buffer(10) + stream2.buffer(10) + stream3.buffer(10)).save_all("example2")
                (stream1 + stream2 + stream3).buffer(10).average().save("example3")
            ```
        """
        return self.__add__(other)

    def subtract(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        """Allows subtraction between streams. The subtraction is done element-wise.
        Can also be performed on buffers and other operators, but they must have the
        same dimensions.

        Example:
            ```python
            i = declare(int)
            j = declare(int)
            k = declare(int, value=5)
            stream = declare_stream()
            stream2 = declare_stream()
            stream3 = declare_stream()
            with for_(j, 0, j < 30, j + 1):
                with for_(i, 0, i < 10, i + 1):
                    save(i, stream)
                    save(j, stream2)
                    save(k, stream3)

            with stream_processing():
                (stream1 - stream2 - stream3).save_all("example1")
                (stream1.buffer(10) - stream2.buffer(10) - stream3.buffer(10)).save_all("example2")
                (stream1 - stream2 - stream3).buffer(10).average().save("example3")
            ```
        """
        return self.__sub__(other)

    def multiply(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        """Allows multiplication between streams. The multiplication is done element-wise.
        Can also be performed on buffers and other operators, but they must have the
        same dimensions.

        Example:
            ```python
            i = declare(int)
            j = declare(int)
            k = declare(int, value=5)
            stream = declare_stream()
            stream2 = declare_stream()
            stream3 = declare_stream()
            with for_(j, 0, j < 30, j + 1):
                with for_(i, 0, i < 10, i + 1):
                    save(i, stream)
                    save(j, stream2)
                    save(k, stream3)

            with stream_processing():
                (stream1 * stream2 * stream3).save_all("example1")
                (stream1.buffer(10) * stream2.buffer(10) * stream3.buffer(10)).save_all("example2")
                (stream1 * stream2 * stream3).buffer(10).average().save("example3")
            ```
        """
        return self.__mul__(other)

    def divide(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        """Allows division between streams. The division is done element-wise.
        Can also be performed on buffers and other operators, but they must have the
        same dimensions.

        Example:
            ```python
            i = declare(int)
            j = declare(int)
            k = declare(int, value=5)
            stream = declare_stream()
            stream2 = declare_stream()
            stream3 = declare_stream()
            with for_(j, 0, j < 30, j + 1):
                with for_(i, 0, i < 10, i + 1):
                    save(i, stream)
                    save(j, stream2)
                    save(k, stream3)

            with stream_processing():
                (stream1 / stream2 / stream3).save_all("example1")
                (stream1.buffer(10) / stream2.buffer(10) / stream3.buffer(10)).save_all("example2")
                (stream1 / stream2 / stream3).buffer(10).average().save("example3")
            ```
        """
        return self.__truediv__(other)

    def __add__(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(self, other, "+")

    def __radd__(self, other: OneOrMore[Number]) -> "BinaryOperation":
        return BinaryOperation(other, self, "+")

    def __sub__(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(self, other, "-")

    def __rsub__(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(other, self, "-")

    def __gt__(self, other: object) -> bool:
        raise QmQuaException("Can't use > operator on results")

    def __ge__(self, other: object) -> bool:
        raise QmQuaException("Can't use >= operator on results")

    def __lt__(self, other: object) -> bool:
        raise QmQuaException("Can't use < operator on results")

    def __le__(self, other: object) -> bool:
        raise QmQuaException("Can't use <= operator on results")

    def __eq__(self, other: object) -> bool:
        raise QmQuaException("Can't use == operator on results")

    def __mul__(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(self, other, "*")

    def __rmul__(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(other, self, "*")

    def __div__(self, other: Union["ResultStream", OneOrMore[Number]]) -> None:
        raise QmQuaException("Can't use / operator on results")

    def __truediv__(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(self, other, "/")

    def __rtruediv__(self, other: Union["ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(other, self, "/")

    def __lshift__(self, other: ScalarOfAnyType) -> None:
        raise TypeError("Can't use << operator on results of type 'ResultStream', only 'ResultSource'")

    def __rshift__(self, other: Union["ResultStream", OneOrMore[Number]]) -> None:
        raise QmQuaException("Can't use >> operator on results")

    def __and__(self, other: Union["ResultStream", OneOrMore[Number]]) -> None:
        raise QmQuaException("Can't use & operator on results")

    def __or__(self, other: Union["ResultStream", OneOrMore[Number]]) -> None:
        raise QmQuaException("Can't use | operator on results")

    def __xor__(self, other: Union["ResultStream", OneOrMore[Number]]) -> None:
        raise QmQuaException("Can't use ^ operator on results")


class _TimestampMode(Enum):
    Values = 0
    Timestamps = 1
    ValuesAndTimestamps = 2


@dataclass
class _Configuration:
    var_name: str
    timestamp_mode: _TimestampMode
    is_adc_trace: bool
    input: int
    auto_reshape: bool


_RESULT_SYMBOL = "@re"


class ResultStreamSource(ResultStream):
    """A python object representing a source of values that can be processed in a [`stream_processing()`][qm.qua.stream_processing] pipeline

    This interface is chainable, which means that calling most methods on this object will create a new streaming source

    See the base class [ResultStream][qm.qua._dsl.stream_processing.stream_processing.ResultStream] for operations
    """

    def __init__(self, configuration: _Configuration):
        self._configuration = configuration

    @property
    def is_adc_trace(self) -> bool:
        return self._configuration.is_adc_trace

    def _to_list_of_values(self) -> Sequence[Value]:
        result = [
            Value(string_value=_RESULT_SYMBOL),
            Value(string_value=str(self._configuration.timestamp_mode.value)),
            Value(string_value=self._configuration.var_name),
        ]
        tmp = [
            Value(string_value="@macro_input"),
            Value(string_value=str(self._configuration.input)),
            Value(list_value=ListValue(values=result)),
        ]
        inputs = result if self._configuration.input == -1 else tmp
        macro_auto_reshape = [Value(string_value="@macro_auto_reshape"), Value(list_value=ListValue(values=inputs))]
        auto_reshape = macro_auto_reshape if self._configuration.auto_reshape else inputs
        macro_adc_trace = [Value(string_value="@macro_adc_trace"), Value(list_value=ListValue(values=auto_reshape))]
        return macro_adc_trace if self._configuration.is_adc_trace else auto_reshape

    def get_var_name(self) -> str:
        return self._configuration.var_name

    def with_timestamps(self) -> "ResultStreamSource":
        """Get a stream with the relevant timestamp for each stream-item"""
        return ResultStreamSource(
            dataclasses.replace(
                self._configuration,
                timestamp_mode=_TimestampMode.ValuesAndTimestamps,
            )
        )

    def timestamps(self) -> "ResultStreamSource":
        """Get a stream with only the timestamps of the stream-items"""
        return ResultStreamSource(
            dataclasses.replace(
                self._configuration,
                timestamp_mode=_TimestampMode.Timestamps,
            )
        )

    def input1(self) -> "ResultStreamSource":
        """A stream of raw ADC data from input 1. Only relevant when saving data from measure statement."""
        return ResultStreamSource(dataclasses.replace(self._configuration, input=1))

    def input2(self) -> "ResultStreamSource":
        """A stream of raw ADC data from input 2. Only relevant when saving data from measure statement."""
        return ResultStreamSource(dataclasses.replace(self._configuration, input=2))

    def auto_reshape(self) -> "ResultStreamSource":
        """Creates a buffer with dimensions according to the program structure in QUA.

        For example, when running the following program the result "reshaped" will have
        shape of (30,10):

        Example:
            ```python
            i = declare(int)
            j = declare(int)
            stream = declare_stream()
            with for_(i, 0, i < 30, i + 1):
                with for_(j, 0, j < 10, j + 1):
                    save(i, stream)

            with stream_processing():
                stream.auto_reshape().save_all("reshaped")
            ```
        """
        return ResultStreamSource(dataclasses.replace(self._configuration, auto_reshape=True))

    def __lshift__(self, other: ScalarOfAnyType) -> None:
        if self.is_adc_trace:
            raise QmQuaException("adc_trace can't be used in save")
        statement = QuaProgramSaveStatement(
            loc=_get_loc(), source=create_qua_scalar_expression(other).save_statement, tag=self.get_var_name()
        )
        scopes_manager.append_statement(QuaProgramAnyStatement(save=statement))


class _UnaryOperation(ResultStream, metaclass=abc.ABCMeta):
    def __init__(self, input_stream: "ResultStream"):
        self._input_stream = input_stream

    def _to_list_of_values(self) -> Sequence[Value]:
        return [Value(string_value=self._operator_name)] + list(self._args) + [self._input_stream.to_proto()]

    @property
    @abc.abstractmethod
    def _operator_name(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def _args(self) -> Sequence[Value]:
        pass


class UnaryMathOperation(_UnaryOperation):
    def __init__(
        self, input_stream: "ResultStream", operator_name: Literal["average", "real", "image", "flatten", "tmult"]
    ) -> None:
        super().__init__(input_stream)
        self._operator = operator_name

    @property
    def _operator_name(self) -> str:
        return self._operator

    @property
    def _args(self) -> Sequence[Value]:
        return []


class BufferOfStream(_UnaryOperation):
    def __init__(self, input_stream: "ResultStream", *args: int):
        super().__init__(input_stream)
        self._args_input = args

    @property
    def _args(self) -> List[Value]:
        return [Value(string_value=str(int(arg))) for arg in self._args_input]

    @property
    def _operator_name(self) -> str:
        return "buffer"


class SkippedBufferOfStream(_UnaryOperation):
    def __init__(self, input_stream: "ResultStream", length: int, skip: int):
        super().__init__(input_stream)
        self._length = length
        self._skip = skip

    @property
    def _args(self) -> List[Value]:
        return [Value(string_value=str(self._length)), Value(string_value=str(self._skip))]

    @property
    def _operator_name(self) -> str:
        return "bufferAndSkip"


class MapOfStream(_UnaryOperation):
    def __init__(self, input_stream: "ResultStream", function: FunctionBase):
        super().__init__(input_stream)
        self._function = function

    @property
    def _operator_name(self) -> str:
        return "map"

    @property
    def _args(self) -> List[Value]:
        return [self._function.to_proto()]


class DiscardedStream(_UnaryOperation):
    def __init__(self, input_stream: "ResultStream", length: int, operator_name: Literal["skip", "skipLast", "take"]):
        super().__init__(input_stream)
        self._length = length
        self._operator_input = operator_name

    @property
    def _operator_name(self) -> str:
        return self._operator_input

    @property
    def _args(self) -> List[Value]:
        return [Value(string_value=str(self._length))]


class HistogramStream(_UnaryOperation):
    def __init__(self, input_stream: "ResultStream", bins_: Sequence[Tuple[Number, Number]]):
        super().__init__(input_stream)
        self._bins = bins_

    @property
    def _operator_name(self) -> str:
        return "histogram"

    @property
    def _args(self) -> List[Value]:
        tmp = [Value(string_value=_ARRAY_SYMBOL)]
        converted_bins = [create_array(sub_list) for sub_list in self._bins]
        _bins = Value(list_value=ListValue(values=tmp + converted_bins))
        return [_bins]


class BinaryOperation(ResultStream):
    def __init__(
        self,
        lhs: Union["ResultStream", OneOrMore[Number]],
        rhs: Union["ResultStream", OneOrMore[Number]],
        operator_name: Literal["+", "-", "*", "/", "zip"],
    ):
        self._lhs = lhs
        self._rhs = rhs
        self._operator_name = operator_name

    def _standardize_output(self, other: Union["ResultStream", OneOrMore[Number]]) -> Value:
        if isinstance(other, ResultStream):
            return other.to_proto()
        elif isinstance(other, (int, float, np.integer, np.floating)) and not isinstance(other, (bool, np.bool_)):
            return Value(string_value=str(other))
        elif isinstance(other, IterableClass):
            return create_array(other)
        if self._operator_name == "zip":
            raise TypeError(f"Unsupported zip for '{type(self._lhs)} and {type(self._rhs)}.")
        else:
            raise TypeError(f"Unsupported operation - '{type(self._lhs)} {self._operator_name} {type(self._rhs)}.")

    def _to_list_of_values(self) -> Sequence[Value]:
        return [
            Value(string_value=self._operator_name),
            self._standardize_output(self._lhs),
            self._standardize_output(self._rhs),
        ]


class _OutputStream(metaclass=abc.ABCMeta):
    """Even though it looks like a stream, it does not support operations (like __add__) and hence, a different object"""

    def __init__(self, input_stream: "ResultStream", tag: str):
        self._input_stream = input_stream
        self.tag = tag

    def to_proto(self) -> "ListValue":
        values = [Value(string_value=s) for s in self._operator_array]
        values.append(self._input_stream.to_proto())
        return ListValue(values=values)

    @property
    @abc.abstractmethod
    def _operator_array(self) -> Tuple[str, ...]:
        pass


class _SaveOutputStream(_OutputStream):
    @property
    def _operator_array(self) -> Tuple[str, ...]:
        return "save", self.tag


class _SaveAllOutputStream(_OutputStream):
    @property
    def _operator_array(self) -> Tuple[str, ...]:
        return "saveAll", self.tag


class _AutoSaveAllOutputStream(_OutputStream):
    @property
    def _operator_array(self) -> Tuple[str, ...]:
        return "saveAll", self.tag, "auto"


def declare_stream(adc_trace: bool = False) -> "ResultStreamSource":
    """Declare a QUA output stream to be used in subsequent statements
    To retrieve the result - it must be saved in the stream processing block.

    Declaration is performed by declaring a python variable with the return value of this function.

    Note:
        if the stream is an ADC trace, declaring it with the syntax ``declare_stream(adc_trace=True)``
        will add a buffer of length corresponding to the pulse length.

    Returns:
        A :class:`ResultStreamSource` object to be used in
        [`stream_processing`][qm.qua.stream_processing]

    Example:
        ```python
        a = declare_stream()
        measure('pulse', 'element', a)

        with stream_processing():
            a.save("tag")
            a.save_all("another tag")
        ```
    """

    scope = scopes_manager.program_scope
    scope.result_index += 1
    var = f"r{scope.result_index}"
    if adc_trace:
        var = "atr_" + var

    return ResultStreamSource(
        _Configuration(
            var_name=var,
            timestamp_mode=_TimestampMode.Values,
            is_adc_trace=adc_trace,
            input=-1,
            auto_reshape=False,
        )
    )


StreamType = Union[str, ResultStreamSource]
"""A type for a stream object in QUA."""
