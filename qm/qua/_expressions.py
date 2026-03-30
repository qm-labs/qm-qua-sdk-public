import abc
import warnings
from typing import TYPE_CHECKING, Any, Type, Union, Generic, Literal, TypeVar, Optional, Sequence, overload

import numpy as np

from qm._loc import _get_loc
from qm.grpc.qm.pb import inc_qua_pb2
from qm.exceptions import QmQuaException
from qm.utils import deprecation_message
from qm.type_hinting.general import NumberT
from qm.serialization.expression_serializing_visitor import ExpressionSerializingVisitor

_ScalarExpressionType = inc_qua_pb2.QuaProgram.AnyScalarExpression


if TYPE_CHECKING:
    from qm.qua._qua_struct import _QuaStruct


def to_literal(
    value: Union[bool, int, float], dtype: inc_qua_pb2.QuaProgram.Type
) -> inc_qua_pb2.QuaProgram.LiteralExpression:
    return inc_qua_pb2.QuaProgram.LiteralExpression(value=str(value), type=dtype, loc=_get_loc())


def literal_int(value: int) -> _ScalarExpressionType:
    return inc_qua_pb2.QuaProgram.AnyScalarExpression(literal=to_literal(value, inc_qua_pb2.QuaProgram.Type.INT))


def literal_bool(value: bool) -> _ScalarExpressionType:
    return inc_qua_pb2.QuaProgram.AnyScalarExpression(literal=to_literal(value, inc_qua_pb2.QuaProgram.Type.BOOL))


def literal_real(value: float) -> _ScalarExpressionType:
    return inc_qua_pb2.QuaProgram.AnyScalarExpression(literal=to_literal(value, inc_qua_pb2.QuaProgram.Type.REAL))


def io(number: Literal[1, 2]) -> _ScalarExpressionType:
    return inc_qua_pb2.QuaProgram.AnyScalarExpression(
        variable=inc_qua_pb2.QuaProgram.VarRefExpression(ioNumber=number, loc=_get_loc())
    )


def io1() -> _ScalarExpressionType:
    return io(1)


def io2() -> _ScalarExpressionType:
    return io(2)


ScalarMessageType = TypeVar(
    "ScalarMessageType",
    inc_qua_pb2.QuaProgram.VarRefExpression,
    inc_qua_pb2.QuaProgram.LiteralExpression,
    inc_qua_pb2.QuaProgram.BinaryExpression,
    inc_qua_pb2.QuaProgram.ArrayCellRefExpression,
    inc_qua_pb2.QuaProgram.ArrayLengthExpression,
    inc_qua_pb2.QuaProgram.LibFunctionExpression,
    inc_qua_pb2.QuaProgram.FunctionExpression,
    inc_qua_pb2.QuaProgram.BroadcastExpression,
    inc_qua_pb2.QuaProgram.GlobalVarRefExpression,
)


S = TypeVar(
    "S",
    bound=Union[
        inc_qua_pb2.QuaProgram.ArrayVarRefExpression,
        inc_qua_pb2.QuaProgram.AnyScalarExpression,
        inc_qua_pb2.QuaProgram.StructVarRefExpression,
        inc_qua_pb2.QuaProgram.ExternalStreamRefExpression,
    ],
)


class QuaExpression(Generic[S], metaclass=abc.ABCMeta):
    def __init__(self, expression: S):
        self._expression = expression

    def unwrap(self) -> S:
        return self._expression

    @property
    def unwrapped(self) -> S:
        return self.unwrap()

    def __str__(self) -> str:
        return ExpressionSerializingVisitor(None).serialize(self._expression)

    def __bool__(self) -> bool:
        raise QmQuaException(
            "Attempted to use a Python logical operator on a QUA variable. If you are unsure why you got this message,"
            " please see https://docs.quantum-machines.co/latest/docs/Guides/qua_ref/#boolean-operations"
        )


class QuaNumericExpression(Generic[S, NumberT], QuaExpression[S], metaclass=abc.ABCMeta):
    def __init__(self, expression: S, t: Type[NumberT]):
        super().__init__(expression)
        self._type: Type[NumberT] = t

    @property
    def dtype(self) -> Type[NumberT]:
        return self._type

    @property
    def _qua_type(self) -> inc_qua_pb2.QuaProgram.Type:
        if issubclass(self.dtype, bool):
            return inc_qua_pb2.QuaProgram.Type.BOOL
        if issubclass(self.dtype, int):
            return inc_qua_pb2.QuaProgram.Type.INT
        if issubclass(self.dtype, float):
            return inc_qua_pb2.QuaProgram.Type.REAL
        raise NotImplementedError(f"Unsupported type - {self.dtype}")

    @property
    def _is_input_stream(self) -> bool:
        return isinstance(self, InputStreamOldInterface)

    def empty(self) -> bool:
        warnings.warn(
            deprecation_message(
                method="QuaExpression.empty()",
                deprecated_in="1.1.0",
                removed_in="1.2.0",
                details="This function is going to be removed, as it's not needed.",
            ),
            DeprecationWarning,
        )
        return self._expression is None

    def isFixed(self) -> bool:
        warnings.warn(
            deprecation_message(
                method="QuaVariable.isFixed",
                deprecated_in="1.1.0",
                removed_in="1.2.0",
                details="use: 'QuaVariable.is_fixed()' instead",
            ),
            DeprecationWarning,
        )
        return self.is_fixed()

    def isInt(self) -> bool:
        warnings.warn(
            deprecation_message(
                method="QuaVariable.isInt",
                deprecated_in="1.1.0",
                removed_in="1.2.0",
                details="use: 'QuaVariable.is_int()' instead",
            ),
            DeprecationWarning,
        )
        return self.is_int()

    def isBool(self) -> bool:
        warnings.warn(
            deprecation_message(
                method="QuaVariable.isBool",
                deprecated_in="1.1.0",
                removed_in="1.2.0",
                details="use: 'QuaVariable.is_bool()' instead",
            ),
            DeprecationWarning,
        )
        return self.is_bool()

    def is_fixed(self) -> bool:
        return issubclass(self._type, float)

    def is_int(self) -> bool:
        return self._type == int

    def is_bool(self) -> bool:
        return self._type == bool


class ScalarMessageInterface(Generic[ScalarMessageType], metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def unwrapped_scalar(self) -> ScalarMessageType:
        pass


class QuaScalarExpression(
    QuaNumericExpression[inc_qua_pb2.QuaProgram.AnyScalarExpression, NumberT],
    ScalarMessageInterface[ScalarMessageType],
    metaclass=abc.ABCMeta,
):
    """
    A class representing a QUA scalar - could be a single value (like a variable), or the result of multiple operations
    (between several expressions) that result in a Scalar value.
    """

    def _get_binary_pb_expression(
        self,
        other: "ScalarOfAnyType",
        op: inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator,
        self_is_first: bool = True,
    ) -> inc_qua_pb2.QuaProgram.AnyScalarExpression:
        other_as_exp = to_scalar_pb_expression(other)
        self_as_exp = self.unwrapped
        if self_is_first:
            left, right = self_as_exp, other_as_exp
        else:
            left, right = other_as_exp, self_as_exp

        exp = inc_qua_pb2.QuaProgram.AnyScalarExpression(
            binaryOperation=inc_qua_pb2.QuaProgram.BinaryExpression(loc=_get_loc(), left=left, right=right, op=op)
        )
        return exp

    def _binary(
        self,
        other: "Scalar[NumberT]",
        op: inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator,
        self_is_first: bool = True,
    ) -> "QuaBinaryOperation[NumberT]":
        exp = self._get_binary_pb_expression(other, op, self_is_first)
        return QuaBinaryOperation(exp, self.dtype)

    def _boolean_binary(
        self,
        other: "Scalar[NumberT]",
        op: inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator,
        self_is_first: bool = True,
    ) -> "QuaBinaryOperation[bool]":
        exp = self._get_binary_pb_expression(other, op, self_is_first)
        return QuaBinaryOperation(exp, bool)

    def _shift_operation_binary(
        self,
        other: "Scalar[int]",
        op: inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator,
        self_is_first: bool = True,
    ) -> "QuaBinaryOperation[NumberT]":
        exp = self._get_binary_pb_expression(other, op, self_is_first)
        return QuaBinaryOperation(exp, self.dtype)

    def __add__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.ADD)

    def __radd__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.ADD, self_is_first=False)

    def __sub__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.SUB)

    def __rsub__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.SUB, self_is_first=False)

    def __neg__(self) -> "QuaBinaryOperation[NumberT]":
        return self.cast(0) - self

    def __gt__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[bool]":
        return self._boolean_binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.GT)

    def __ge__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[bool]":
        return self._boolean_binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.GET)

    def __lt__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[bool]":
        return self._boolean_binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.LT)

    def __le__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[bool]":
        return self._boolean_binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.LET)

    def __eq__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[bool]":  # type: ignore[override]
        return self._boolean_binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.EQ)

    def __mul__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.MULT)

    def __rmul__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.MULT, self_is_first=False)

    def __truediv__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.DIV)

    def __rtruediv__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.DIV, self_is_first=False)

    def __lshift__(self, other: "Scalar[int]") -> "QuaBinaryOperation[NumberT]":
        return self._shift_operation_binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.SHL)

    def __rlshift__(self, other: int) -> "QuaBinaryOperation[NumberT]":
        return self._shift_operation_binary(
            other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.SHL, self_is_first=False
        )

    def __rshift__(self, other: "Scalar[int]") -> "QuaBinaryOperation[NumberT]":
        return self._shift_operation_binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.SHR)

    def __rrshift__(self, other: int) -> "QuaBinaryOperation[NumberT]":
        return self._shift_operation_binary(
            other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.SHR, self_is_first=False
        )

    def __and__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.AND)

    def __rand__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.AND, self_is_first=False)

    def __or__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.OR)

    def __ror__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.OR, self_is_first=False)

    def __xor__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.XOR)

    def __rxor__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.XOR, self_is_first=False)

    def __invert__(self) -> "QuaBinaryOperation[NumberT]":
        return self._binary(self.cast(True), inc_qua_pb2.QuaProgram.BinaryExpression.BinaryOperator.XOR)

    def cast(self, n: Union[bool, int, float]) -> NumberT:
        return self.dtype(n)

    @property
    def save_statement(self) -> inc_qua_pb2.QuaProgram.SaveStatement.Source:
        raise QmQuaException("saving is not allowed for this kind of qua expression")


class QuaArrayVariable(QuaNumericExpression[inc_qua_pb2.QuaProgram.ArrayVarRefExpression, NumberT]):
    def __init__(self, name: str, t: Type[NumberT], init_value: Sequence[Union[int, bool, float]], size: int):
        super(QuaArrayVariable, self).__init__(inc_qua_pb2.QuaProgram.ArrayVarRefExpression(name=name), t)
        self._size = size
        self._init_value = [to_literal(t(val), self._qua_type) for val in init_value]

    @property
    def declaration_statement(self) -> inc_qua_pb2.QuaProgram.VarDeclaration:
        return inc_qua_pb2.QuaProgram.VarDeclaration(
            name=self.unwrapped.name,
            value=self._init_value,
            type=self._qua_type,
            size=self._size,
            dim=1,
            isInputStream=self._is_input_stream,
        )

    def __getitem__(self, item: "Scalar[int]") -> "QuaArrayCell[NumberT]":
        idx_as_pb = to_scalar_pb_expression(item)
        arr = self.unwrapped
        loc = _get_loc()
        arr.loc = loc
        item_scalar_expression = inc_qua_pb2.QuaProgram.AnyScalarExpression(
            arrayCell=inc_qua_pb2.QuaProgram.ArrayCellRefExpression(arrayVar=arr, index=idx_as_pb, loc=loc)
        )
        return QuaArrayCell(item_scalar_expression, self.dtype)

    def length(self) -> "QuaArrayLength[int]":
        unwrapped_element = self.unwrapped
        array_exp = inc_qua_pb2.QuaProgram.ArrayLengthExpression(array=unwrapped_element)
        result = inc_qua_pb2.QuaProgram.AnyScalarExpression(arrayLength=array_exp)
        return QuaArrayLength(result, int)


class QuaStructReference(QuaExpression[inc_qua_pb2.QuaProgram.StructVarRefExpression]):
    def __init__(self, name: str):
        super().__init__(inc_qua_pb2.QuaProgram.StructVarRefExpression(name=name, loc=_get_loc()))
        self.name = name


NSize = TypeVar("NSize", bound=int)


class QuaStructArrayVariable(QuaArrayVariable[NumberT], Generic[NumberT, NSize]):
    def __init__(
        self,
        name: str,
        t: Type[NumberT],
        size: int,
        position: int,
        struct: QuaStructReference,
    ):
        super(QuaArrayVariable, self).__init__(
            inc_qua_pb2.QuaProgram.ArrayVarRefExpression(name=name, structVar=struct.unwrapped), t
        )
        self._size = size
        self._init_value = []
        self._position = position
        self._struct: QuaStructReference = struct

    @property
    def declaration_statement(self) -> inc_qua_pb2.QuaProgram.VarDeclaration:
        declaration_statement = super().declaration_statement
        struct_member = inc_qua_pb2.QuaProgram.VarDeclaration.StructMember(
            name=self._struct.name, position=self._position
        )
        declaration_statement.structMember.CopyFrom(struct_member)
        return declaration_statement


class AssignmentTargetInterface(metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def assignment_statement(self) -> inc_qua_pb2.QuaProgram.AssignmentStatement.Target:
        pass


class NotAllowedOperation(QmQuaException):
    def __init__(self, expression_type: str) -> None:
        super(NotAllowedOperation, self).__init__(
            f"In-place operations are not supported for QUA {expression_type}. Please use `assign` instead."
        )


class NotAllowedOperationVariable(NotAllowedOperation):
    def __init__(self) -> None:
        super().__init__("variable")


class NotAllowedOperationArrayCell(NotAllowedOperation):
    def __init__(self) -> None:
        super().__init__("array cell")


class QuaVariable(AssignmentTargetInterface, QuaScalarExpression[NumberT, inc_qua_pb2.QuaProgram.VarRefExpression]):
    """A class representing a QUA scalar variable. Note that a `QuaVariable` is also a `QuaScalarExpression`."""

    def __init__(self, name: str, t: Type[NumberT], init_value: Optional[Union[int, bool, float]]):
        super(QuaScalarExpression, self).__init__(
            inc_qua_pb2.QuaProgram.AnyScalarExpression(variable=inc_qua_pb2.QuaProgram.VarRefExpression(name=name)), t
        )
        self._init_value = [to_literal(t(init_value), self._qua_type)] if init_value is not None else []

    @property
    def declaration_statement(self) -> inc_qua_pb2.QuaProgram.VarDeclaration:
        return inc_qua_pb2.QuaProgram.VarDeclaration(
            name=self.unwrapped.variable.name,
            value=self._init_value,
            type=self._qua_type,
            size=1,
            dim=0,
            isInputStream=self._is_input_stream,
        )

    @property
    def unwrapped_scalar(self) -> inc_qua_pb2.QuaProgram.VarRefExpression:
        return self.unwrapped.variable

    @property
    def save_statement(self) -> inc_qua_pb2.QuaProgram.SaveStatement.Source:
        return inc_qua_pb2.QuaProgram.SaveStatement.Source(variable=self.unwrapped_scalar)

    @property
    def assignment_statement(self) -> inc_qua_pb2.QuaProgram.AssignmentStatement.Target:
        return inc_qua_pb2.QuaProgram.AssignmentStatement.Target(variable=self.unwrapped_scalar)

    def __iadd__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __isub__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __imul__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __itruediv__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __ifloordiv__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __imod__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __ipow__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __ilshift__(self, other: "Scalar[int]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __irshift__(self, other: "Scalar[int]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __iand__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __ior__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable

    def __ixor__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationVariable


class QuaLiteral(QuaScalarExpression[NumberT, inc_qua_pb2.QuaProgram.LiteralExpression]):
    @property
    def unwrapped_scalar(self) -> inc_qua_pb2.QuaProgram.LiteralExpression:
        return self.unwrapped.literal

    @property
    def save_statement(self) -> inc_qua_pb2.QuaProgram.SaveStatement.Source:
        return inc_qua_pb2.QuaProgram.SaveStatement.Source(literal=self.unwrapped_scalar)


class QuaArrayCell(
    AssignmentTargetInterface, QuaScalarExpression[NumberT, inc_qua_pb2.QuaProgram.ArrayCellRefExpression]
):
    """A class representing a QUA variable inside a QUA array cell."""

    @property
    def unwrapped_scalar(self) -> inc_qua_pb2.QuaProgram.ArrayCellRefExpression:
        return self.unwrapped.arrayCell

    @property
    def save_statement(self) -> inc_qua_pb2.QuaProgram.SaveStatement.Source:
        return inc_qua_pb2.QuaProgram.SaveStatement.Source(arrayCell=self.unwrapped_scalar)

    @property
    def assignment_statement(self) -> inc_qua_pb2.QuaProgram.AssignmentStatement.Target:
        return inc_qua_pb2.QuaProgram.AssignmentStatement.Target(arrayCell=self.unwrapped_scalar)

    def __iadd__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __isub__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __imul__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __itruediv__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __ifloordiv__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __imod__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __ipow__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __ilshift__(self, other: "Scalar[int]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __irshift__(self, other: "Scalar[int]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __iand__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __ior__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell

    def __ixor__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        raise NotAllowedOperationArrayCell


class QuaBinaryOperation(QuaScalarExpression[NumberT, inc_qua_pb2.QuaProgram.BinaryExpression]):
    @property
    def unwrapped_scalar(self) -> inc_qua_pb2.QuaProgram.BinaryExpression:
        return self.unwrapped.binaryOperation


class QuaArrayLength(QuaScalarExpression[NumberT, inc_qua_pb2.QuaProgram.ArrayLengthExpression]):
    @property
    def unwrapped_scalar(self) -> inc_qua_pb2.QuaProgram.ArrayLengthExpression:
        return self.unwrapped.arrayLength


class QuaLibFunctionOutput(QuaScalarExpression[NumberT, inc_qua_pb2.QuaProgram.LibFunctionExpression]):
    """A class representing the result of a QUA lib function."""

    @property
    def unwrapped_scalar(self) -> inc_qua_pb2.QuaProgram.LibFunctionExpression:
        return self.unwrapped.libFunction


class QuaFunctionOutput(QuaScalarExpression[NumberT, inc_qua_pb2.QuaProgram.FunctionExpression]):
    def __init__(self, function_expression: inc_qua_pb2.QuaProgram.FunctionExpression, t: Type[NumberT]):
        super(QuaScalarExpression, self).__init__(
            inc_qua_pb2.QuaProgram.AnyScalarExpression(function=function_expression), t
        )

    @property
    def unwrapped_scalar(self) -> inc_qua_pb2.QuaProgram.FunctionExpression:
        return self.unwrapped.function


class QuaBroadcast(QuaScalarExpression[NumberT, inc_qua_pb2.QuaProgram.BroadcastExpression]):
    """A class representing the result of a QUA broadcast expression."""

    def __init__(self, t: Type[NumberT], value: _ScalarExpressionType):
        super(QuaScalarExpression, self).__init__(
            inc_qua_pb2.QuaProgram.AnyScalarExpression(
                broadcast=inc_qua_pb2.QuaProgram.BroadcastExpression(value=value, loc=_get_loc())
            ),
            t,
        )

    @property
    def unwrapped_scalar(self) -> inc_qua_pb2.QuaProgram.BroadcastExpression:
        return self.unwrapped.broadcast


class StreamInterface(abc.ABC):
    @property
    @abc.abstractmethod
    def _direction(self) -> inc_qua_pb2.QuaProgram.Direction:
        pass


class OutputStreamInterface(StreamInterface, abc.ABC):
    @property
    def _direction(self) -> inc_qua_pb2.QuaProgram.Direction:
        return inc_qua_pb2.QuaProgram.Direction.OUTGOING


class InputStreamInterface(StreamInterface, abc.ABC):
    @property
    def _direction(self) -> inc_qua_pb2.QuaProgram.Direction:
        return inc_qua_pb2.QuaProgram.Direction.INCOMING


StructT = TypeVar("StructT", bound="_QuaStruct")


class QuaExternalStream(
    Generic[StructT], QuaExpression[inc_qua_pb2.QuaProgram.ExternalStreamRefExpression], StreamInterface
):
    def __init__(self, stream_id: int, struct_t: Type[StructT]):
        super(QuaExternalStream, self).__init__(
            inc_qua_pb2.QuaProgram.ExternalStreamRefExpression(stream_id=stream_id, loc=_get_loc())
        )
        self._stream_id = stream_id
        self._struct_t = struct_t

    @property
    def declaration_statement(self) -> inc_qua_pb2.QuaProgram.ExternalStreamDeclaration:
        return inc_qua_pb2.QuaProgram.ExternalStreamDeclaration(
            stream_id=self._stream_id,
            expectedTypes=self._struct_t.__underlying_declarations__,
            direction=self._direction,
        )


class QuaExternalIncomingStream(QuaExternalStream[StructT], InputStreamInterface):
    def receive(self, struct: StructT) -> None:
        # Alternative API to directly call `receive_from_opnic_stream`.
        # Importing `_receive_from_opnic_stream` here to avoid circular imports
        from qm.qua._dsl.streams.external_streams import _receive_from_opnic_stream

        _receive_from_opnic_stream(self, struct)


class QuaExternalOutgoingStream(QuaExternalStream[StructT], OutputStreamInterface):
    def send(self, struct: StructT) -> None:
        # Alternative API to directly call `send_to_opnic_stream`.
        # Importing `_send_to_opnic_stream` here to avoid circular imports
        from qm.qua._dsl.streams.external_streams import _send_to_opnic_stream

        _send_to_opnic_stream(self, struct)


class InputStreamOldInterface(InputStreamInterface, abc.ABC):
    @abc.abstractmethod
    def advance(self) -> inc_qua_pb2.QuaProgram.AnyStatement:
        # The statement itself, will be added to the program in the advance_input_stream() method
        pass


class QuaArrayInputStream(QuaArrayVariable[NumberT], InputStreamOldInterface):
    """A class representing the QUA vector that will be used as an input stream from the job to the QUA program."""

    def advance(self) -> inc_qua_pb2.QuaProgram.AnyStatement:
        return inc_qua_pb2.QuaProgram.AnyStatement(
            advanceInputStream=inc_qua_pb2.QuaProgram.AdvanceInputStreamStatement(
                loc=_get_loc(), streamArray=self.unwrapped
            )
        )


class QuaVariableInputStream(QuaVariable[NumberT], InputStreamOldInterface):
    """A class representing the QUA variable that will be used as an input stream from the job to the QUA program."""

    def advance(self) -> inc_qua_pb2.QuaProgram.AnyStatement:
        return inc_qua_pb2.QuaProgram.AnyStatement(
            advanceInputStream=inc_qua_pb2.QuaProgram.AdvanceInputStreamStatement(
                loc=_get_loc(), streamVariable=self.unwrapped.variable
            )
        )


class QuaIO(AssignmentTargetInterface):
    """A class representing the QUA IO type."""

    def __init__(self, number: Literal[1, 2]):
        self._number = number

    @property
    def assignment_statement(self) -> inc_qua_pb2.QuaProgram.AssignmentStatement.Target:
        return inc_qua_pb2.QuaProgram.AssignmentStatement.Target(
            variable=inc_qua_pb2.QuaProgram.VarRefExpression(ioNumber=self._number, loc=_get_loc())
        )


IO1 = QuaIO(1)
IO2 = QuaIO(2)


class _QuaGlobalVarOperation(
    QuaScalarExpression[NumberT, inc_qua_pb2.QuaProgram.GlobalVarRefExpression], metaclass=abc.ABCMeta
):
    def __init__(
        self, bits: Sequence[int], operation: inc_qua_pb2.QuaProgram.GlobalVarOperation, t: Type[NumberT]
    ) -> None:
        super(_QuaGlobalVarOperation, self).__init__(
            inc_qua_pb2.QuaProgram.AnyScalarExpression(
                globalVariable=inc_qua_pb2.QuaProgram.GlobalVarRefExpression(
                    loc=_get_loc(),
                    bits=list(bits),
                    operation=operation,
                ),
            ),
            t,
        )

    @property
    def unwrapped_scalar(self) -> inc_qua_pb2.QuaProgram.GlobalVarRefExpression:
        return self.unwrapped.globalVariable


class QuaGlobalVarRead(_QuaGlobalVarOperation[int]):
    def __init__(self, bits: Sequence[int], shift: bool) -> None:
        operation = (
            inc_qua_pb2.QuaProgram.GlobalVarOperation.read_shift
            if shift
            else inc_qua_pb2.QuaProgram.GlobalVarOperation.read
        )
        super(QuaGlobalVarRead, self).__init__(bits, operation, int)


class QuaGlobalVarXor(_QuaGlobalVarOperation[bool]):
    def __init__(self, bits: Sequence[int]) -> None:
        super(QuaGlobalVarXor, self).__init__(bits, inc_qua_pb2.QuaProgram.GlobalVarOperation.xor, bool)


def _fix_object_data_type(obj: Any) -> Any:
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        obj_item = obj.item()
        if isinstance(obj_item, np.longdouble):
            return float(obj_item)
        else:
            return obj_item
    else:
        return obj


def to_scalar_pb_expression(value: Union["ScalarOfAnyType", QuaIO]) -> _ScalarExpressionType:
    other = _fix_object_data_type(value)
    if isinstance(other, QuaScalarExpression):
        return other.unwrapped
    if isinstance(other, bool):  # Since bool is a subtype of int, it must be before it
        return literal_bool(other)
    if isinstance(other, int):
        return literal_int(other)
    if isinstance(other, float):
        return literal_real(other)
    if other == IO1:
        return io(1)
    if other == IO2:
        return io(2)
    raise QmQuaException(f"invalid expression: '{other}' is not a scalar expression")


@overload
def create_qua_scalar_expression(value: "QuaScalar[NumberT]") -> "QuaScalar[NumberT]":
    ...


@overload
def create_qua_scalar_expression(value: NumberT) -> QuaLiteral[NumberT]:
    ...


def create_qua_scalar_expression(value: "Scalar[NumberT]") -> "QuaScalar[NumberT]":
    if isinstance(value, QuaScalarExpression):
        return value
    if not isinstance(value, (int, float)):
        value = _fix_object_data_type(value)
    if isinstance(value, bool):  # Since bool is a subtype of int, it must be before it
        return QuaLiteral(literal_bool(value), bool)
    if isinstance(value, int):
        return QuaLiteral(literal_int(value), int)
    if isinstance(value, float):
        return QuaLiteral(literal_real(value), float)
    raise NotImplementedError


def validate_scalar_of_any_type(data_type: Any) -> None:
    if not isinstance(data_type, (QuaScalarExpression, bool, int, float)):
        raise QmQuaException(f"Data type must be a ScalarOfAnyType (QUA scalar value), got {type(data_type).__name__}.")


class fixed(float):
    pass


QuaScalar = Union[
    QuaVariable[NumberT],
    QuaLiteral[NumberT],
    QuaBinaryOperation[NumberT],
    QuaArrayCell[NumberT],
    QuaArrayLength[NumberT],
    QuaLibFunctionOutput[NumberT],
    QuaFunctionOutput[NumberT],
    QuaBroadcast[NumberT],
    _QuaGlobalVarOperation[NumberT],
]

Scalar = Union[QuaScalar[NumberT], NumberT]
"""A generic type representing the generic `NumberT` or the QUA equivalent of it."""

Vector = Union[Sequence[NumberT], QuaArrayVariable[NumberT]]
"""A generic type representing a generic array of `NumberT`, or the QUA equivalent of it."""

ScalarOfAnyType = Union[Scalar[bool], Scalar[int], Scalar[float]]
"""A type representing a scalar value in QUA, or the equivalent python type."""

VectorOfAnyType = Union[Vector[bool], Vector[int], Vector[float]]
"""A type representing a vector value in QUA, or the equivalent python type."""
