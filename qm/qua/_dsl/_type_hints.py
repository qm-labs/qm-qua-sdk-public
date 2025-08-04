from typing import Union, TypeVar, Sequence

from qm.grpc.qua import QuaProgramVarRefExpression, QuaProgramAnyScalarExpression

# The public name for the QuaProgramAnyScalarExpression type.
MessageExpressionType = QuaProgramAnyScalarExpression

MessageVarType = QuaProgramVarRefExpression

T = TypeVar("T")
OneOrMore = Union[T, Sequence[T]]
