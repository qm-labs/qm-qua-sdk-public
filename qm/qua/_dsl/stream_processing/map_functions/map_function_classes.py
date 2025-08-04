import abc
from collections.abc import Collection
from typing import Literal, Optional, Sequence

from betterproto.lib.google.protobuf import Value, ListValue

from qm.type_hinting import Number
from qm.qua._dsl._type_hints import OneOrMore
from qm.qua._dsl.stream_processing.stream_processing_utils import create_array


class FunctionBase(metaclass=abc.ABCMeta):
    def to_proto(self) -> Value:
        return Value(list_value=ListValue(values=[Value(string_value=self._operator_name)] + list(self._args)))

    @property
    @abc.abstractmethod
    def _operator_name(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def _args(self) -> Sequence[Value]:
        pass


class Average(FunctionBase):
    def __init__(self, axis: Optional[OneOrMore[Number]] = None):
        self._axis = axis

    @property
    def _operator_name(self) -> str:
        return "average"

    @property
    def _args(self) -> Sequence[Value]:
        if self._axis is None:
            return []
        else:
            if isinstance(self._axis, Collection):
                return [create_array(self._axis)]
            else:
                return [Value(string_value=str(self._axis))]


class DotProduct(FunctionBase):
    def __init__(self, vector: Sequence[Number]):
        self._vector = vector

    @property
    def _operator_name(self) -> str:
        return "dot"

    @property
    def _args(self) -> Sequence[Value]:
        return [create_array(self._vector)]


class TupleDotProduct(FunctionBase):
    @property
    def _operator_name(self) -> str:
        return "dot"

    @property
    def _args(self) -> Sequence[Value]:
        return []


class MultiplyByScalar(FunctionBase):
    def __init__(self, scalar: Number):
        self._scalar = scalar

    @property
    def _operator_name(self) -> str:
        return "smult"

    @property
    def _args(self) -> Sequence[Value]:
        return [Value(string_value=str(self._scalar))]


class MultiplyByVector(FunctionBase):
    def __init__(self, vector: Sequence[Number]):
        self._vector = vector

    @property
    def _operator_name(self) -> str:
        return "vmult"

    @property
    def _args(self) -> Sequence[Value]:
        return [create_array(self._vector)]


class TupleMultiply(FunctionBase):
    @property
    def _operator_name(self) -> str:
        return "tmult"

    @property
    def _args(self) -> Sequence[Value]:
        return []


ConvolutionMode = Literal["", "valid", "same", "full"]


class Convolution(FunctionBase):
    def __init__(self, constant_vector: Sequence[Number], mode: ConvolutionMode = ""):
        self._constant_vector = constant_vector
        self._mode = mode

    @property
    def _operator_name(self) -> str:
        return "conv"

    @property
    def _args(self) -> Sequence[Value]:
        return [Value(string_value=self._mode), create_array(self._constant_vector)]


class TupleConvolution(FunctionBase):
    def __init__(self, mode: ConvolutionMode = ""):
        self._mode = mode

    @property
    def _operator_name(self) -> str:
        return "conv"

    @property
    def _args(self) -> Sequence[Value]:
        return [Value(string_value=self._mode)]


class FFT(FunctionBase):
    def __init__(self, output: Optional[str] = None):
        self._output = output

    @property
    def _operator_name(self) -> str:
        return "fft"

    @property
    def _args(self) -> Sequence[Value]:
        if self._output is None:
            return []
        else:
            return [Value(string_value=self._output)]


class BooleanToInt(FunctionBase):
    @property
    def _operator_name(self) -> str:
        return "booleancast"

    @property
    def _args(self) -> Sequence[Value]:
        return []


class Demod(FunctionBase):
    def __init__(
        self, frequency: Number, iw_cos: OneOrMore[Number], iw_sin: OneOrMore[Number], integrate: Optional[bool] = None
    ):
        self._frequency = frequency
        self._iw_cos = self._standardize_integration_weights(iw_cos)
        self._iw_sin = self._standardize_integration_weights(iw_sin)
        self._integrate = integrate

    @staticmethod
    def _standardize_integration_weights(iw: OneOrMore[Number]) -> Value:
        if isinstance(iw, Collection):
            return create_array(iw)
        return Value(string_value=str(iw))

    @property
    def _operator_name(self) -> str:
        return "demod"

    @property
    def _args(self) -> Sequence[Value]:
        values = [Value(string_value=str(self._frequency)), self._iw_cos, self._iw_sin]
        if isinstance(self._integrate, bool):
            values.append(Value(string_value=str(int(self._integrate))))
        return values
