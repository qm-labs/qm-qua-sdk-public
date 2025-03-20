# This file provides type hints for the Qua DSL, allowing users to import them from `qm.qua.type_hints` instead of
# protected files.

from qm.qua._dsl import StreamType
from qm.type_hinting import NumberT
from qm.qua._dsl_specific_type_hints import ChirpType, ChirpUnits
from qm.qua._expressions import (
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
]
