from typing_extensions import Literal
from typing import Tuple, Union, TypeVar, Iterable, Optional, Sequence

from qm.qua._expressions import Scalar, QuaArrayVariable
from qm.grpc.qua import (
    QuaProgramRampPulse,
    QuaProgramVarRefExpression,
    QuaProgramAnyScalarExpression,
    QuaProgramArrayVarRefExpression,
)

ChirpType = Union[
    Tuple[Union[Iterable[int], QuaArrayVariable[int], Scalar[int]], str],
    Tuple[Iterable[int], Iterable[int], str],
]
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


class fixed(float):
    pass


ConvolutionMode = Literal["", "valid", "same", "full"]
