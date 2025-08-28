import abc
from enum import Enum
from dataclasses import dataclass
from collections.abc import Sequence, Collection
from typing import Union, Literal, Optional, overload

import numpy as np

from qm._loc import _get_loc
from qm.type_hinting import NumberT
from qm.exceptions import QmQuaException
from qm.qua._dsl._utils import _declare_save
from qm.qua._dsl._type_hints import OneOrMore
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._dsl.stream_processing.stream_processing import ResultStreamSource
from qm.grpc.qua import QuaProgramAnyStatement, QuaProgramSaveStatement, QuaProgramAssignmentStatement
from qm.qua._expressions import (
    NSize,
    QuaIO,
    Scalar,
    StructT,
    QuaVariable,
    QuaArrayCell,
    ScalarOfAnyType,
    QuaArrayVariable,
    QuaStructReference,
    QuaArrayInputStream,
    QuaStructArrayVariable,
    QuaVariableInputStream,
    to_scalar_pb_expression,
    create_qua_scalar_expression,
)


class DeclarationType(Enum):
    EmptyScalar = 0
    InitScalar = 1
    EmptyArray = 2
    InitArray = 3


class _DeclarationParams(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def create_variable(
        self, var_name: str, t: type[NumberT]
    ) -> Union[QuaArrayVariable[NumberT], QuaVariable[NumberT]]:
        pass

    @abc.abstractmethod
    def create_input_stream(
        self, var_name: str, t: type[NumberT]
    ) -> Union[QuaArrayInputStream[NumberT], QuaVariableInputStream[NumberT]]:
        pass


@dataclass
class _ArrayDeclarationParams(_DeclarationParams):
    size: int
    values: Sequence[Union[bool, int, float]]

    def create_variable(self, var_name: str, t: type[NumberT]) -> QuaArrayVariable[NumberT]:
        return QuaArrayVariable(var_name, t, size=self.size, init_value=self.values)

    def create_input_stream(self, var_name: str, t: type[NumberT]) -> QuaArrayInputStream[NumberT]:
        return QuaArrayInputStream(var_name, t, size=self.size, init_value=self.values)


@dataclass
class _StructArrayDeclarationParams(_DeclarationParams):
    size: int
    position: int
    struct_ref: QuaStructReference

    def create_variable(self, var_name: str, t: type[NumberT]) -> QuaStructArrayVariable[NumberT, NSize]:
        return QuaStructArrayVariable(var_name, t, size=self.size, position=self.position, struct=self.struct_ref)

    def create_input_stream(self, var_name: str, t: type[NumberT]) -> QuaArrayInputStream[NumberT]:
        raise NotImplementedError("Struct members cannot be used as input streams")


@dataclass
class _ScalarDeclarationParams(_DeclarationParams):
    value: Optional[Union[bool, int, float]]

    def create_variable(self, var_name: str, t: type[NumberT]) -> QuaVariable[NumberT]:
        return QuaVariable(var_name, t, init_value=self.value)

    def create_input_stream(self, var_name: str, t: type[NumberT]) -> QuaVariableInputStream[NumberT]:
        return QuaVariableInputStream(var_name, t, init_value=self.value)


def _standardize_value_and_size(
    value: Optional[OneOrMore[Union[bool, int, float]]] = None, size: Optional[int] = None
) -> _DeclarationParams:

    if size is not None:
        size = size.item() if isinstance(size, np.integer) else size
        if not (isinstance(size, int) and size > 0):
            raise QmQuaException("size must be a positive integer")
        if value is not None:
            raise QmQuaException("size declaration cannot be made if value is declared")
        return _ArrayDeclarationParams(size=size, values=[])

    if isinstance(value, Collection):
        size = len(value)
        return _ArrayDeclarationParams(size=size, values=list(value))

    return _ScalarDeclarationParams(value=value)


@overload
def declare(t: type[NumberT]) -> QuaVariable[NumberT]:
    ...


@overload
def declare(t: type[NumberT], value: Literal[None], size: int) -> QuaArrayVariable[NumberT]:
    ...


@overload
def declare(t: type[NumberT], *, size: int) -> QuaArrayVariable[NumberT]:
    ...


@overload
def declare(t: type[NumberT], value: Union[int, bool, float]) -> QuaVariable[NumberT]:
    ...


@overload
def declare(t: type[NumberT], value: Sequence[Union[int, bool, float]]) -> QuaArrayVariable[NumberT]:
    ...


def declare(
    t: type[NumberT],
    value: Optional[OneOrMore[Union[int, bool, float]]] = None,
    size: Optional[int] = None,
) -> Union[QuaVariable[NumberT], QuaArrayVariable[NumberT]]:
    r"""Declare a single QUA variable or QUA vector to be used in subsequent expressions and assignments.

    Declaration is performed by declaring a python variable with the return value of this function.

    Args:
        t: The type of QUA variable. Possible values: ``int``,
            ``fixed``, ``bool``, where:

            ``int``
                a signed 32-bit number
            ``fixed``
                a signed 4.28 fixed point number
            ``bool``
                either `True` or `False`
        value: An initial value for the variable or a list of initial
            values for a vector
        size: If declaring a vector without explicitly specifying a
            value, this parameter is used to specify the length of the
            array

    Returns:
        The variable or vector

    Warning:

        some QUA statements accept a variable with a valid range smaller than the full size of the generic
        QUA variable. For example, ``amp()`` accepts numbers between -2 and 2.
        In case the value stored in the variable is larger than the valid input range, unexpected results
        may occur.

    Example:
        ```python
        a = declare(fixed, value=0.3)
        play('pulse' * amp(a), 'element')

        array1 = declare(int, value=[1, 2, 3])
        array2 = declare(fixed, size=5)
        ```
    """
    params = _standardize_value_and_size(value, size)

    scope = scopes_manager.program_scope
    # We could move the following logic inside the classes, but then we would have to deal with the scope there.
    #  Additionally, we want to separate the concern of choosing the variable name from the declaration logic,
    if isinstance(params, _ArrayDeclarationParams):
        scope.array_index += 1
        var = f"a{scope.array_index}"
    else:
        scope.var_index += 1
        var = f"v{scope.var_index}"

    result = params.create_variable(var, t)
    scope.add_var_declaration(result.declaration_statement)

    return result


@overload
def declare_input_stream(t: type[NumberT], name: str) -> QuaVariableInputStream[NumberT]:
    ...


@overload
def declare_input_stream(t: type[NumberT], name: str, value: Literal[None], size: int) -> QuaArrayInputStream[NumberT]:
    ...


@overload
def declare_input_stream(t: type[NumberT], name: str, *, size: int) -> QuaArrayInputStream[NumberT]:
    ...


@overload
def declare_input_stream(
    t: type[NumberT], name: str, value: Union[int, bool, float]
) -> QuaVariableInputStream[NumberT]:
    ...


@overload
def declare_input_stream(
    t: type[NumberT], name: str, value: Sequence[Union[int, bool, float]]
) -> QuaArrayInputStream[NumberT]:
    ...


def declare_input_stream(
    t: type[NumberT],
    name: str,
    value: Optional[OneOrMore[Union[int, bool, float]]] = None,
    size: Optional[int] = None,
) -> Union[QuaVariableInputStream[NumberT], QuaArrayInputStream[NumberT]]:
    """Declare a QUA variable or a QUA vector to be used as an input stream from the job to the QUA program.

    Declaration is performed by declaring a python variable with the return value of this function.

    Declaration is similar to the normal QUA variable declaration. See [qm.qua.declare][] for available
    parameters.

    See [Input streams](../../Guides/features.md#input-streams) for more information.

    -- Available from QOP 2.0 --

    Example:
        ```python
        tau = declare_input_stream(int)
        ...
        advance_input_stream(tau)
        play('operation', 'element', duration=tau)
        ```
    """
    if name is None:
        raise QmQuaException("input stream declared without a name")

    scope = scopes_manager.program_scope
    var = f"input_stream_{name}"

    if var in scope.declared_input_streams:
        raise QmQuaException("input stream already declared")

    params = _standardize_value_and_size(value, size)

    scope.add_input_stream_declaration(var)
    result = params.create_input_stream(var, t)

    scope.add_var_declaration(result.declaration_statement)

    return result


def _declare_struct_array_variable(
    t: type[NumberT],
    size: int,
    position: int,
    struct_ref: QuaStructReference,
) -> QuaStructArrayVariable[NumberT, NSize]:
    """
    Declare a struct member variable. This function is used internally when a struct is initialized.
    """
    params = _StructArrayDeclarationParams(size=size, position=position, struct_ref=struct_ref)

    scope = scopes_manager.program_scope
    scope.array_index += 1
    var = f"a{scope.array_index}"

    result: QuaStructArrayVariable[NumberT, NSize] = params.create_variable(var, t)
    scope.add_var_declaration(result.declaration_statement)

    return result


def declare_struct(struct_t: type[StructT]) -> StructT:
    scope = scopes_manager.program_scope
    scope.struct_index += 1
    name = f"s{scope.struct_index}"

    struct_reference = QuaStructReference(name)

    return struct_t(
        _struct_reference=struct_reference,  # type: ignore[call-arg]
        **{
            member_name: factory.create(struct_reference)
            for member_name, factory in struct_t.__members_initializers__.items()
        },
    )


def assign(var: Union[QuaArrayCell[NumberT], QuaVariable[NumberT], QuaIO], _exp: Union[Scalar[NumberT], QuaIO]) -> None:
    """Set the value of a given QUA variable, a QUA array cell or an IO to the value of a given expression.

    Args:
        var (QUA variable): A QUA variable, a QUA array cell or an IO for which to assign.
        _exp (QUA expression): An expression for which to set the variable

    Example:
        ```python
        with program() as prog:
            v1 = declare(fixed)
            assign(v1, 1.3)
            play('pulse1' * amp(v1), 'element1')
        ```
    """
    statement = QuaProgramAssignmentStatement(
        loc=_get_loc(), target=var.assignment_statement, expression=to_scalar_pb_expression(_exp)
    )
    scopes_manager.append_statement(QuaProgramAnyStatement(assign=statement))


def save(var: ScalarOfAnyType, stream_or_tag: Union[str, "ResultStreamSource"]) -> None:
    """Stream a QUA variable, a QUA array cell, or a constant scalar.
    the variable is streamed and not immediately saved (see [Stream processing](../../Guides/stream_proc.md#stream-processing)).
    In case ``result_or_tag`` is a string, the data will be immediately saved to a result handle under the same name.

    If result variable is used, it can be used in results analysis scope see [stream_processing][qm.qua.stream_processing]
    if string tag is used, it will let you receive result with [qm.QmJob.result_handles][qm.jobs.running_qm_job.RunningQmJob.result_handles].
    The type of the variable determines the stream datatype, according to the following rule:

    - int -> int64
    - fixed -> float64
    - bool -> bool

    Note:

        Saving arrays as arrays is not currently supported. Please use a QUA for loop to save an array.

    Example:
        ```python
        # basic save
        a = declare(int, value=2)
        save(a, "a")

        # fetching the results from python (job is a QmJob object):
        a_handle = job.result_handles.get("a")
        a_data = a_handle.fetch_all()

        # save the third array cell
        vec = declare(fixed, value=[0.2, 0.3, 0.4, 0.5])
        save(vec[2], "ArrayCellSave")

        # array iteration
        i = declare(int)
        array = declare(fixed, value=[x / 10 for x in range(30)])
        with for_(i, 0, i < 30, i + 1):
            save(array[i], "array")

        # save a constant
        save(3, "a")
        ```

    Args:
        var (Union[QUA variable, a QUA array cell]): A QUA variable or a
            QUA array cell to save
        stream_or_tag (Union[str, stream variable]): A stream variable
            or string tag name to save the value under
    """
    if isinstance(stream_or_tag, str):
        result_obj = _declare_save(stream_or_tag, add_legacy_timestamp=True)
    else:
        result_obj = stream_or_tag

    if result_obj.is_adc_trace:
        raise QmQuaException("adc_trace can't be used in save")
    statement = QuaProgramSaveStatement(
        loc=_get_loc(), source=create_qua_scalar_expression(var).save_statement, tag=result_obj.get_var_name()
    )
    scopes_manager.append_statement(QuaProgramAnyStatement(save=statement))


def advance_input_stream(
    input_stream: Union[
        QuaVariableInputStream[bool],
        QuaVariableInputStream[int],
        QuaVariableInputStream[float],
        QuaArrayInputStream[bool],
        QuaArrayInputStream[int],
        QuaArrayInputStream[float],
    ]
) -> None:
    """Advances the input stream pointer to the next available variable/vector.

    If there is no new data waiting in the stream, this command will wait until it is available.

    The variable/vector can then be used as a normal QUA variable.

    See [Input streams](../../Guides/features.md#input-streams) for more information.

    -- Available from QOP 2.0 --
    """
    scopes_manager.append_statement(input_stream.advance())
