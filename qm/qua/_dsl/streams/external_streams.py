from enum import Enum
from typing_extensions import deprecated
from typing import Union, Literal, Optional, overload

from qm._loc import _get_loc
from qm.grpc.qm.pb import inc_qua_pb2
from qm.exceptions import QmQuaException
from qm.api.models.capabilities import QopCaps
from qm.utils.deprecation_utils import QmQuaDeprecationWarning
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._expressions import StructT, QuaVariable, QuaExternalIncomingStream, QuaExternalOutgoingStream


class QuaStreamDirection(Enum):
    INCOMING = "INCOMING"
    OUTGOING = "OUTGOING"


@overload
def declare_external_stream(
    struct_type: type[StructT], stream_id: int, direction: Literal[QuaStreamDirection.INCOMING]
) -> QuaExternalIncomingStream[StructT]: ...


@overload
def declare_external_stream(
    struct_type: type[StructT], stream_id: int, direction: Literal[QuaStreamDirection.OUTGOING]
) -> QuaExternalOutgoingStream[StructT]: ...


@deprecated(
    'declare_external_stream is deprecated since "1.2.4" and will be removed in "2.0.0". '
    "Please use declare_input_stream() / declare_output_stream() instead",
    category=QmQuaDeprecationWarning,
    stacklevel=1,
)
def declare_external_stream(
    struct_type: type[StructT], stream_id: int, direction: QuaStreamDirection
) -> Union[QuaExternalIncomingStream[StructT], QuaExternalOutgoingStream[StructT]]:
    """Declare a stream to an external compute resource.

    The stream can be either an incoming or an outgoing stream, which will receive or send data from the external
    compute resource respectively.

    Deprecated since 1.2.4; will be removed in 2.0.0. Use ``declare_input_stream()`` / ``declare_output_stream()`` instead.

    Args:
        struct_type: A QuaStruct type that defines a single packet of the stream.
        stream_id: The ID of the stream, an integer between 0 and 1000.
            Has to match the ID of the stream declared in
            the external compute resource.
        direction: The direction of the stream, either QuaStreamDirection.INCOMING or QuaStreamDirection.OUTGOING.

    Returns:
        An incoming or outgoing external stream object, according to the requested direction.

    Example:
        ```python
        struct = declare_struct(StructType)
        stream = declare_external_stream(StructType, 0, QuaStreamDirection.INCOMING)
        ```

    """
    return _declare_opnic_stream(struct_type, stream_id, direction)


def _declare_opnic_stream(
    struct_type: type[StructT], stream_id: int, direction: QuaStreamDirection
) -> Union[QuaExternalIncomingStream[StructT], QuaExternalOutgoingStream[StructT]]:
    program_scope = scopes_manager.program_scope
    program_scope.add_used_capability(QopCaps.external_stream)

    if not isinstance(struct_type, type):
        raise QmQuaException(f"struct_type must be a type (class), got {type(struct_type).__name__}")

    if not hasattr(struct_type, "__members_initializers__"):
        raise QmQuaException(
            f"struct_type must be a QuaStruct type (decorated with @qua_struct), got {struct_type.__name__ if hasattr(struct_type, '__name__') else type(struct_type).__name__}"
        )

    if not 1 <= stream_id <= 1023:
        raise QmQuaException("stream_id must be between 1 and 1023")

    stream: Union[QuaExternalIncomingStream[StructT], QuaExternalOutgoingStream[StructT]]

    stream_identifier = (stream_id, direction)
    if stream_identifier in program_scope.declared_external_streams:
        raise QmQuaException(f"Opnic stream with id '{stream_id}' already declared")

    if direction == QuaStreamDirection.INCOMING:
        stream = QuaExternalIncomingStream(stream_id, struct_type)
    elif direction == QuaStreamDirection.OUTGOING:
        stream = QuaExternalOutgoingStream(stream_id, struct_type)
    else:
        raise QmQuaException("direction must be either QuaStreamDirection.INCOMING or QuaStreamDirection.OUTGOING")

    program_scope.add_external_stream_declaration(stream_identifier, stream.declaration_statement)
    return stream


@deprecated(
    'send_to_external_stream is deprecated since "1.2.4" and will be removed in "2.0.0". '
    "Please use send_to_stream() instead",
    category=QmQuaDeprecationWarning,
    stacklevel=1,
)
def send_to_external_stream(stream: QuaExternalOutgoingStream[StructT], struct: StructT) -> None:
    """
    Send data to an external compute resource.

    Deprecated since 1.2.4; will be removed in 2.0.0. Use ``send_to_stream()`` instead.

    Args:
        stream: The outgoing stream to send data to.
        struct: The struct containing the data to send.
    """
    _send_to_opnic_stream(stream, struct)


def _send_to_opnic_stream(stream: QuaExternalOutgoingStream[StructT], struct: StructT) -> None:
    try:
        _ = struct.struct_reference
    except AttributeError:
        raise QmQuaException("Data sent to an opnic stream must be a struct instance.")

    statement = inc_qua_pb2.QuaProgram.AnyStatement(
        sendToExternalStream=inc_qua_pb2.QuaProgram.SendToExternalStreamStatement(
            loc=_get_loc(), stream=stream.unwrapped, struct=struct.struct_reference.unwrapped
        )
    )
    scopes_manager.append_statement(statement)


@deprecated(
    'receive_from_external_stream is deprecated since "1.2.4" and will be removed in "2.0.0". '
    "Please use receive_from_stream() instead",
    category=QmQuaDeprecationWarning,
    stacklevel=1,
)
def receive_from_external_stream(stream: QuaExternalIncomingStream[StructT], struct: StructT) -> None:
    """
    Receive data from an external compute resource.

    Deprecated since 1.2.4; will be removed in 2.0.0. Use ``receive_from_stream()`` instead.

    Args:
        stream: The incoming stream to receive data from.
        struct: The struct to store the received data in.
    """
    _receive_from_opnic_stream(stream, struct, is_valid=None, duration=None)


def _receive_from_opnic_stream(
    stream: QuaExternalIncomingStream[StructT],
    struct: StructT,
    is_valid: Optional[QuaVariable[bool]],
    duration: Optional[int],
) -> None:
    try:
        _ = struct.struct_reference
    except AttributeError:
        raise QmQuaException(
            f"Data received from an opnic stream must be saved into a struct instance. got {type(struct).__name__} instead."
        )

    _validate_non_blocking_args(is_valid, duration)

    receive_statement = inc_qua_pb2.QuaProgram.ReceiveFromExternalStreamStatement(
        loc=_get_loc(), stream=stream.unwrapped, struct=struct.struct_reference.unwrapped
    )
    if is_valid is not None and duration is not None:
        scopes_manager.program_scope.add_used_capability(QopCaps.external_stream_blocking_duration)
        receive_statement.is_valid.CopyFrom(is_valid.unwrapped_scalar)
        receive_statement.duration = duration

    statement = inc_qua_pb2.QuaProgram.AnyStatement(receiveFromExternalStream=receive_statement)
    scopes_manager.append_statement(statement)


def _validate_non_blocking_args(is_valid: Optional[QuaVariable[bool]], duration: Optional[int]) -> None:
    if is_valid is None and duration is None:
        return

    if is_valid is None or duration is None:
        raise QmQuaException(
            "'is_valid' and 'duration' must be provided together to enable a non-blocking receive, "
            "or both omitted for the default blocking behavior."
        )

    if not isinstance(is_valid, QuaVariable) or not issubclass(is_valid.dtype, bool):
        raise QmQuaException("'is_valid' must be a QUA boolean variable declared with declare(bool).")

    if not isinstance(duration, int) or isinstance(duration, bool):
        raise QmQuaException(
            "'duration' must be a plain integer number of clock cycles; QUA variables are not supported."
        )
