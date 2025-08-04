import abc
import warnings
from typing import TYPE_CHECKING, Any, Type, Union, Generic, Literal, TypeVar, Optional, Sequence, overload

import numpy as np

from qm._loc import _get_loc
from qm.exceptions import QmQuaException
from qm.utils import deprecation_message
from qm.type_hinting.general import NumberT
from qm.serialization.expression_serializing_visitor import ExpressionSerializingVisitor
from qm.grpc.qua import (
    QuaProgramType,
    QuaProgramDirection,
    QuaProgramAnyStatement,
    QuaProgramVarDeclaration,
    QuaProgramBinaryExpression,
    QuaProgramVarRefExpression,
    QuaProgramLiteralExpression,
    QuaProgramFunctionExpression,
    QuaProgramAnyScalarExpression,
    QuaProgramBroadcastExpression,
    QuaProgramSaveStatementSource,
    QuaProgramArrayLengthExpression,
    QuaProgramArrayVarRefExpression,
    QuaProgramLibFunctionExpression,
    QuaProgramArrayCellRefExpression,
    QuaProgramStructVarRefExpression,
    QuaProgramAssignmentStatementTarget,
    QuaProgramExternalStreamDeclaration,
    QuaProgramVarDeclarationStructMember,
    QuaProgramAdvanceInputStreamStatement,
    QuaProgramExternalStreamRefExpression,
    QuaProgramBinaryExpressionBinaryOperator,
)

_ScalarExpressionType = QuaProgramAnyScalarExpression


if TYPE_CHECKING:
    from qm.qua._qua_struct import _QuaStruct


def to_literal(value: Union[bool, int, float], dtype: QuaProgramType) -> QuaProgramLiteralExpression:
    return QuaProgramLiteralExpression(value=str(value), type=dtype, loc=_get_loc())


def literal_int(value: int) -> _ScalarExpressionType:
    return QuaProgramAnyScalarExpression(literal=to_literal(value, QuaProgramType.INT))  # type: ignore[arg-type]


def literal_bool(value: bool) -> _ScalarExpressionType:
    return QuaProgramAnyScalarExpression(literal=to_literal(value, QuaProgramType.BOOL))  # type: ignore[arg-type]


def literal_real(value: float) -> _ScalarExpressionType:
    return QuaProgramAnyScalarExpression(literal=to_literal(value, QuaProgramType.REAL))  # type: ignore[arg-type]


def io(number: Literal[1, 2]) -> _ScalarExpressionType:
    return QuaProgramAnyScalarExpression(variable=QuaProgramVarRefExpression(io_number=number, loc=_get_loc()))


def io1() -> _ScalarExpressionType:
    return io(1)


def io2() -> _ScalarExpressionType:
    return io(2)


ScalarMessageType = TypeVar(
    "ScalarMessageType",
    QuaProgramVarRefExpression,
    QuaProgramLiteralExpression,
    QuaProgramBinaryExpression,
    QuaProgramArrayCellRefExpression,
    QuaProgramArrayLengthExpression,
    QuaProgramLibFunctionExpression,
    QuaProgramFunctionExpression,
    QuaProgramBroadcastExpression,
)


S = TypeVar(
    "S",
    bound=Union[
        QuaProgramArrayVarRefExpression,
        QuaProgramAnyScalarExpression,
        QuaProgramStructVarRefExpression,
        QuaProgramExternalStreamRefExpression,
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
            " please see https://qm-docs.qualang.io/guides/qua_ref#boolean-operations"
        )


class QuaNumericExpression(Generic[S, NumberT], QuaExpression[S], metaclass=abc.ABCMeta):
    def __init__(self, expression: S, t: Type[NumberT]):
        super().__init__(expression)
        self._type: Type[NumberT] = t

    @property
    def dtype(self) -> Type[NumberT]:
        return self._type

    @property
    def _qua_type(self) -> QuaProgramType:
        if issubclass(self.dtype, bool):
            return QuaProgramType.BOOL  # type: ignore[return-value]
        if issubclass(self.dtype, int):
            return QuaProgramType.INT  # type: ignore[return-value]
        if issubclass(self.dtype, float):
            return QuaProgramType.REAL  # type: ignore[return-value]
        raise NotImplementedError(f"Unsupported type - {self.dtype}")

    @property
    def _is_input_stream(self) -> bool:
        return isinstance(self, InputStreamInterface)

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
    QuaNumericExpression[QuaProgramAnyScalarExpression, NumberT],
    ScalarMessageInterface[ScalarMessageType],
    metaclass=abc.ABCMeta,
):
    """
    A class representing a QUA scalar - could be a single value (like a variable), or the result of multiple operations
    (between several expressions) that result in a Scalar value.
    """

    def _get_binary_pb_expression(
        self, other: "ScalarOfAnyType", op: QuaProgramBinaryExpressionBinaryOperator, self_is_first: bool = True
    ) -> QuaProgramAnyScalarExpression:
        other_as_exp = to_scalar_pb_expression(other)
        self_as_exp = self.unwrapped
        if self_is_first:
            left, right = self_as_exp, other_as_exp
        else:
            left, right = other_as_exp, self_as_exp

        exp = QuaProgramAnyScalarExpression(
            binary_operation=QuaProgramBinaryExpression(loc=_get_loc(), left=left, right=right, op=op)
        )
        return exp

    def _binary(
        self, other: "Scalar[NumberT]", op: QuaProgramBinaryExpressionBinaryOperator, self_is_first: bool = True
    ) -> "QuaBinaryOperation[NumberT]":
        exp = self._get_binary_pb_expression(other, op, self_is_first)
        return QuaBinaryOperation(exp, self.dtype)

    def _boolean_binary(
        self, other: "Scalar[NumberT]", op: QuaProgramBinaryExpressionBinaryOperator, self_is_first: bool = True
    ) -> "QuaBinaryOperation[bool]":
        exp = self._get_binary_pb_expression(other, op, self_is_first)
        return QuaBinaryOperation(exp, bool)

    def _shift_operation_binary(
        self, other: "Scalar[int]", op: QuaProgramBinaryExpressionBinaryOperator, self_is_first: bool = True
    ) -> "QuaBinaryOperation[NumberT]":
        exp = self._get_binary_pb_expression(other, op, self_is_first)
        return QuaBinaryOperation(exp, self.dtype)

    def __add__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.ADD)  # type: ignore[arg-type]

    def __radd__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.ADD, self_is_first=False)  # type: ignore[arg-type]

    def __sub__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.SUB)  # type: ignore[arg-type]

    def __rsub__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.SUB, self_is_first=False)  # type: ignore[arg-type]

    def __neg__(self) -> "QuaBinaryOperation[NumberT]":
        return self.cast(0) - self

    def __gt__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[bool]":
        return self._boolean_binary(other, QuaProgramBinaryExpressionBinaryOperator.GT)  # type: ignore[arg-type]

    def __ge__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[bool]":
        return self._boolean_binary(other, QuaProgramBinaryExpressionBinaryOperator.GET)  # type: ignore[arg-type]

    def __lt__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[bool]":
        return self._boolean_binary(other, QuaProgramBinaryExpressionBinaryOperator.LT)  # type: ignore[arg-type]

    def __le__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[bool]":
        return self._boolean_binary(other, QuaProgramBinaryExpressionBinaryOperator.LET)  # type: ignore[arg-type]

    def __eq__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[bool]":  # type: ignore[override]
        return self._boolean_binary(other, QuaProgramBinaryExpressionBinaryOperator.EQ)  # type: ignore[arg-type]

    def __mul__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.MULT)  # type: ignore[arg-type]

    def __rmul__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.MULT, self_is_first=False)  # type: ignore[arg-type]

    def __truediv__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.DIV)  # type: ignore[arg-type]

    def __rtruediv__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.DIV, self_is_first=False)  # type: ignore[arg-type]

    def __lshift__(self, other: "Scalar[int]") -> "QuaBinaryOperation[NumberT]":
        return self._shift_operation_binary(other, QuaProgramBinaryExpressionBinaryOperator.SHL)  # type: ignore[arg-type]

    def __rlshift__(self, other: int) -> "QuaBinaryOperation[NumberT]":
        return self._shift_operation_binary(other, QuaProgramBinaryExpressionBinaryOperator.SHL, self_is_first=False)  # type: ignore[arg-type]

    def __rshift__(self, other: "Scalar[int]") -> "QuaBinaryOperation[NumberT]":
        return self._shift_operation_binary(other, QuaProgramBinaryExpressionBinaryOperator.SHR)  # type: ignore[arg-type]

    def __rrshift__(self, other: int) -> "QuaBinaryOperation[NumberT]":
        return self._shift_operation_binary(other, QuaProgramBinaryExpressionBinaryOperator.SHR, self_is_first=False)  # type: ignore[arg-type]

    def __and__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.AND)  # type: ignore[arg-type]

    def __rand__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.AND, self_is_first=False)  # type: ignore[arg-type]

    def __or__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.OR)  # type: ignore[arg-type]

    def __ror__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.OR, self_is_first=False)  # type: ignore[arg-type]

    def __xor__(self, other: "Scalar[NumberT]") -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.XOR)  # type: ignore[arg-type]

    def __rxor__(self, other: NumberT) -> "QuaBinaryOperation[NumberT]":
        return self._binary(other, QuaProgramBinaryExpressionBinaryOperator.XOR, self_is_first=False)  # type: ignore[arg-type]

    def __invert__(self) -> "QuaBinaryOperation[NumberT]":
        return self._binary(self.cast(True), QuaProgramBinaryExpressionBinaryOperator.XOR)  # type: ignore[arg-type]

    def cast(self, n: Union[bool, int, float]) -> NumberT:
        return self.dtype(n)

    @property
    def save_statement(self) -> QuaProgramSaveStatementSource:
        raise QmQuaException("saving is not allowed for this kind of qua expression")


class QuaArrayVariable(QuaNumericExpression[QuaProgramArrayVarRefExpression, NumberT]):
    def __init__(self, name: str, t: Type[NumberT], init_value: Sequence[Union[int, bool, float]], size: int):
        super(QuaArrayVariable, self).__init__(QuaProgramArrayVarRefExpression(name=name), t)
        self._size = size
        self._init_value = [to_literal(t(val), self._qua_type) for val in init_value]

    @property
    def declaration_statement(self) -> QuaProgramVarDeclaration:
        return QuaProgramVarDeclaration(
            name=self.unwrapped.name,
            value=self._init_value,
            type=self._qua_type,
            size=self._size,
            dim=1,
            is_input_stream=self._is_input_stream,
        )

    def __getitem__(self, item: "Scalar[int]") -> "QuaArrayCell[NumberT]":
        idx_as_pb = to_scalar_pb_expression(item)
        arr = self.unwrapped
        loc = _get_loc()
        arr.loc = loc
        item_scalar_expression = QuaProgramAnyScalarExpression(
            array_cell=QuaProgramArrayCellRefExpression(array_var=arr, index=idx_as_pb, loc=loc)
        )
        return QuaArrayCell(item_scalar_expression, self.dtype)

    def length(self) -> "QuaArrayLength[int]":
        unwrapped_element = self.unwrapped
        array_exp = QuaProgramArrayLengthExpression(array=unwrapped_element)
        result = QuaProgramAnyScalarExpression(array_length=array_exp)
        return QuaArrayLength(result, int)


class QuaStructReference(QuaExpression[QuaProgramStructVarRefExpression]):
    def __init__(self, name: str):
        super().__init__(QuaProgramStructVarRefExpression(name=name, loc=_get_loc()))
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
            QuaProgramArrayVarRefExpression(name=name, struct_var=struct.unwrapped), t
        )
        self._size = size
        self._init_value = []
        self._position = position
        self._struct: QuaStructReference = struct

    @property
    def declaration_statement(self) -> QuaProgramVarDeclaration:
        declaration_statement = super().declaration_statement
        struct_member = QuaProgramVarDeclarationStructMember(name=self._struct.name, position=self._position)
        declaration_statement.struct_member = struct_member
        return declaration_statement


class AssignmentTargetInterface(metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def assignment_statement(self) -> QuaProgramAssignmentStatementTarget:
        pass


class QuaVariable(AssignmentTargetInterface, QuaScalarExpression[NumberT, QuaProgramVarRefExpression]):
    """A class representing a QUA scalar variable. Note that a `QuaVariable` is also a `QuaScalarExpression`."""

    def __init__(self, name: str, t: Type[NumberT], init_value: Optional[Union[int, bool, float]]):
        super(QuaScalarExpression, self).__init__(
            QuaProgramAnyScalarExpression(variable=QuaProgramVarRefExpression(name)), t
        )
        self._init_value = [to_literal(t(init_value), self._qua_type)] if init_value is not None else []

    @property
    def declaration_statement(self) -> QuaProgramVarDeclaration:
        return QuaProgramVarDeclaration(
            name=self.unwrapped.variable.name,
            value=self._init_value,
            type=self._qua_type,
            size=1,
            dim=0,
            is_input_stream=self._is_input_stream,
        )

    @property
    def unwrapped_scalar(self) -> QuaProgramVarRefExpression:
        return self.unwrapped.variable

    @property
    def save_statement(self) -> QuaProgramSaveStatementSource:
        return QuaProgramSaveStatementSource(variable=self.unwrapped_scalar)

    @property
    def assignment_statement(self) -> QuaProgramAssignmentStatementTarget:
        return QuaProgramAssignmentStatementTarget(variable=self.unwrapped_scalar)


class QuaLiteral(QuaScalarExpression[NumberT, QuaProgramLiteralExpression]):
    @property
    def unwrapped_scalar(self) -> QuaProgramLiteralExpression:
        return self.unwrapped.literal

    @property
    def save_statement(self) -> QuaProgramSaveStatementSource:
        return QuaProgramSaveStatementSource(literal=self.unwrapped_scalar)


class QuaArrayCell(AssignmentTargetInterface, QuaScalarExpression[NumberT, QuaProgramArrayCellRefExpression]):
    """A class representing a QUA variable inside a QUA array cell."""

    @property
    def unwrapped_scalar(self) -> QuaProgramArrayCellRefExpression:
        return self.unwrapped.array_cell

    @property
    def save_statement(self) -> QuaProgramSaveStatementSource:
        return QuaProgramSaveStatementSource(array_cell=self.unwrapped_scalar)

    @property
    def assignment_statement(self) -> QuaProgramAssignmentStatementTarget:
        return QuaProgramAssignmentStatementTarget(array_cell=self.unwrapped_scalar)


class QuaBinaryOperation(QuaScalarExpression[NumberT, QuaProgramBinaryExpression]):
    @property
    def unwrapped_scalar(self) -> QuaProgramBinaryExpression:
        return self.unwrapped.binary_operation


class QuaArrayLength(QuaScalarExpression[NumberT, QuaProgramArrayLengthExpression]):
    @property
    def unwrapped_scalar(self) -> QuaProgramArrayLengthExpression:
        return self.unwrapped.array_length


class QuaLibFunctionOutput(QuaScalarExpression[NumberT, QuaProgramLibFunctionExpression]):
    """A class representing the result of a QUA lib function."""

    @property
    def unwrapped_scalar(self) -> QuaProgramLibFunctionExpression:
        return self.unwrapped.lib_function


class QuaFunctionOutput(QuaScalarExpression[NumberT, QuaProgramFunctionExpression]):
    def __init__(self, function_expression: QuaProgramFunctionExpression, t: Type[NumberT]):
        super(QuaScalarExpression, self).__init__(QuaProgramAnyScalarExpression(function=function_expression), t)

    @property
    def unwrapped_scalar(self) -> QuaProgramFunctionExpression:
        return self.unwrapped.function


class QuaBroadcast(QuaScalarExpression[NumberT, QuaProgramBroadcastExpression]):
    """A class representing the result of a QUA broadcast expression."""

    def __init__(self, t: Type[NumberT], value: _ScalarExpressionType):
        super(QuaScalarExpression, self).__init__(
            QuaProgramAnyScalarExpression(broadcast=QuaProgramBroadcastExpression(value, loc=_get_loc())), t
        )

    @property
    def unwrapped_scalar(self) -> QuaProgramBroadcastExpression:
        return self.unwrapped.broadcast


StructT = TypeVar("StructT", bound="_QuaStruct")


class QuaExternalStream(Generic[StructT], QuaExpression[QuaProgramExternalStreamRefExpression], metaclass=abc.ABCMeta):
    def __init__(self, stream_id: int, struct_t: Type[StructT]):
        super(QuaExternalStream, self).__init__(
            QuaProgramExternalStreamRefExpression(stream_id=stream_id, loc=_get_loc())
        )
        self._stream_id = stream_id
        self._struct_t = struct_t

    @property
    @abc.abstractmethod
    def _direction(self) -> QuaProgramDirection:
        pass

    @property
    def declaration_statement(self) -> QuaProgramExternalStreamDeclaration:
        return QuaProgramExternalStreamDeclaration(
            stream_id=self._stream_id,
            expected_types=self._struct_t.__underlying_declarations__,
            direction=self._direction,
        )


class QuaExternalIncomingStream(QuaExternalStream[StructT]):
    @property
    def _direction(self) -> QuaProgramDirection:
        return QuaProgramDirection.INCOMING  # type: ignore[return-value]

    def receive(self, struct: StructT) -> None:
        # Alternative API to directly call `receive_from_external_stream`.
        # Importing `receive_from_external_stream` here to avoid circular imports
        from qm.qua._dsl.external_stream import receive_from_external_stream

        receive_from_external_stream(self, struct)


class QuaExternalOutgoingStream(QuaExternalStream[StructT]):
    @property
    def _direction(self) -> QuaProgramDirection:
        return QuaProgramDirection.OUTGOING  # type: ignore[return-value]

    def send(self, struct: StructT) -> None:
        # Alternative API to directly call `send_to_external_stream`.
        # Importing `send_to_external_stream` here to avoid circular imports
        from qm.qua._dsl.external_stream import send_to_external_stream

        send_to_external_stream(self, struct)


class InputStreamInterface(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def advance(self) -> QuaProgramAnyStatement:
        pass


class QuaArrayInputStream(QuaArrayVariable[NumberT], InputStreamInterface):
    """A class representing the QUA vector that will be used as an input stream from the job to the QUA program."""

    def advance(self) -> QuaProgramAnyStatement:
        return QuaProgramAnyStatement(
            advance_input_stream=QuaProgramAdvanceInputStreamStatement(loc=_get_loc(), stream_array=self.unwrapped)
        )


class QuaVariableInputStream(QuaVariable[NumberT], InputStreamInterface):
    """A class representing the QUA variable that will be used as an input stream from the job to the QUA program."""

    def advance(self) -> QuaProgramAnyStatement:
        return QuaProgramAnyStatement(
            advance_input_stream=QuaProgramAdvanceInputStreamStatement(
                loc=_get_loc(), stream_variable=self.unwrapped.variable
            )
        )


class QuaIO(AssignmentTargetInterface):
    """A class representing the QUA IO type."""

    def __init__(self, number: Literal[1, 2]):
        self._number = number

    @property
    def assignment_statement(self) -> QuaProgramAssignmentStatementTarget:
        return QuaProgramAssignmentStatementTarget(
            variable=QuaProgramVarRefExpression(io_number=self._number, loc=_get_loc())
        )


IO1 = QuaIO(1)
IO2 = QuaIO(2)


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
]

Scalar = Union[QuaScalar[NumberT], NumberT]
"""A generic type representing the generic `NumberT` or the QUA equivalent of it."""

Vector = Union[Sequence[NumberT], QuaArrayVariable[NumberT]]
"""A generic type representing a generic array of `NumberT`, or the QUA equivalent of it."""

ScalarOfAnyType = Union[Scalar[bool], Scalar[int], Scalar[float]]
"""A type representing a scalar value in QUA, or the equivalent python type."""

VectorOfAnyType = Union[Vector[bool], Vector[int], Vector[float]]
"""A type representing a vector value in QUA, or the equivalent python type."""
