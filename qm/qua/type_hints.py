# This file provides type hints for the Qua DSL, allowing users to import them from `qm.qua.type_hints` instead of
# protected files.
from qm.qua._dsl.play import ChirpUnits
from qm.qua import ChirpType, StreamType
from qm.type_hinting.general import NumberT
from qm.qua._dsl.stream_processing.stream_processing import ResultStreamSource
from qm.qua._expressions import (
    NSize,
    QuaIO,
    Scalar,
    Vector,
    QuaScalar,
    QuaVariable,
    QuaArrayCell,
    QuaBroadcast,
    ScalarOfAnyType,
    VectorOfAnyType,
    QuaArrayInputStream,
    QuaScalarExpression,
    QuaLibFunctionOutput,
    QuaVariableInputStream,
)

__all__ = [
    "NumberT",
    "ChirpType",
    "ChirpUnits",
    "Scalar",
    "Vector",
    "QuaScalar",
    "ScalarOfAnyType",
    "VectorOfAnyType",
    "QuaVariable",
    "QuaArrayCell",
    "QuaLibFunctionOutput",
    "QuaBroadcast",
    "QuaScalarExpression",
    "QuaArrayInputStream",
    "QuaVariableInputStream",
    "QuaIO",
    "StreamType",
    "NSize",
    "ResultStreamSource",
]
