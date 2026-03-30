from typing import Union, TypeVar, Sequence

from qm.grpc.qm.pb import inc_qua_pb2

# The public name for the QuaProgramAnyScalarExpression type.
MessageExpressionType = inc_qua_pb2.QuaProgram.AnyScalarExpression

MessageVarType = inc_qua_pb2.QuaProgram.VarRefExpression

T = TypeVar("T")
OneOrMore = Union[T, Sequence[T]]
