from typing import Tuple, Union, Literal, TypeVar, Iterable, Optional, Sequence

from qm.qua._expressions import Scalar, QuaArrayVariable
from qm.grpc.qua import (
    QuaProgramRampPulse,
    QuaProgramVarRefExpression,
    QuaProgramAnyScalarExpression,
    QuaProgramArrayVarRefExpression,
)

ChirpUnits = Literal[
    "Hz/nsec",
    "GHz/sec",
    "mHz/nsec",
    "MHz/sec",
    "uHz/nsec",
    "KHz/sec",
    "nHz/nsec",
    "Hz/sec",
    "pHz/nsec",
    "mHz/sec",
]
ChirpType = Union[
    Tuple[Union[Iterable[int], QuaArrayVariable[int], Scalar[int]], ChirpUnits],
    Tuple[Iterable[int], Iterable[int], ChirpUnits],
]
"""A type for performing piecewise linear sweep of the element’s intermediate frequency in time.
A tuple, with the 1st element being a list of rates and the second should be a string with the unit type.
See the ChirpUnits type for the complete list of supported units.
"""

MessageExpressionType = QuaProgramAnyScalarExpression
AmpValuesType = Tuple[
    MessageExpressionType,
    Optional[MessageExpressionType],
    Optional[MessageExpressionType],
    Optional[MessageExpressionType],
]
MeasurePulseType = Union[str, Tuple[str, AmpValuesType]]
PlayPulseType = Union[MeasurePulseType, QuaProgramRampPulse]
MessageArrayVarType = QuaProgramArrayVarRefExpression
MessageVarType = QuaProgramVarRefExpression

T = TypeVar("T")
OneOrMore = Union[T, Sequence[T]]

ConvolutionMode = Literal["", "valid", "same", "full"]
