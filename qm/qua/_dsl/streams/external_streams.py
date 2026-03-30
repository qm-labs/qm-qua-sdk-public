import warnings
from enum import Enum
from typing import Union, Literal, overload

from qm._loc import _get_loc
from qm.grpc.qm.pb import inc_qua_pb2
from qm.exceptions import QmQuaException
from qm.utils import deprecation_message
from qm.api.models.capabilities import QopCaps
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._expressions import StructT, QuaExternalIncomingStream, QuaExternalOutgoingStream


class QuaStreamDirection(Enum):
    INCOMING = "INCOMING"
    OUTGOING = "OUTGOING"


@overload
def declare_external_stream(
    struct_type: type[StructT], stream_id: int, direction: Literal[QuaStreamDirection.INCOMING]
) -> QuaExternalIncomingStream[StructT]:
    ...


@overload
def declare_external_stream(
    struct_type: type[StructT], stream_id: int, direction: Literal[QuaStreamDirection.OUTGOING]
) -> QuaExternalOutgoingStream[StructT]:
    ...


def declare_external_stream(
    struct_type: type[StructT], stream_id: int, direction: QuaStreamDirection
) -> Union[QuaExternalIncomingStream[StructT], QuaExternalOutgoingStream[StructT]]:
    """Declare a stream to an external compute resource.

    The stream can be either an incoming or an outgoing stream, which will receive or send data from the external
    compute resource respectively.

    Args:
        struct_type: A QuaStruct type that defines a single packet of the stream.
        stream_id: The ID of the stream, an integer between 0 and 1000.
            Has to match the ID of the stream declared in
            the external compute resource.
        direction: The direction of the stream, either QuaStreamDirection.INCOMING or QuaStreamDirection.OUTGOING.

    Example:
        ```python
        struct = declare_struct(StructType)
        stream = declare_external_stream(StructType, 0, QuaStreamDirection.INCOMING)
        ```

    """
    warnings.warn(
        deprecation_message(
            "declare_external_stream",
            deprecated_in="1.2.4",
            removed_in="2.0.0",
            details="Please use declare_input_stream() / declare_output_stream() instead.",
        ),
        DeprecationWarning,
        stacklevel=2,
    )
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


def send_to_external_stream(stream: QuaExternalOutgoingStream[StructT], struct: StructT) -> None:
    """
    Send data to an external compute resource.

    Args:
        stream: The outgoing stream to send data to.
        struct: The struct containing the data to send.
    """
    warnings.warn(
        deprecation_message(
            "send_to_external_stream",
            deprecated_in="1.2.4",
            removed_in="2.0.0",
            details="Please use send_to_stream() instead.",
        ),
        DeprecationWarning,
        stacklevel=2,
    )
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


def receive_from_external_stream(stream: QuaExternalIncomingStream[StructT], struct: StructT) -> None:
    """
    Receive data from an external compute resource.

    Args:
        stream: The incoming stream to receive data from.
        struct: The struct to store the received data in.
    """
    warnings.warn(
        deprecation_message(
            "receive_from_external_stream",
            deprecated_in="1.2.4",
            removed_in="2.0.0",
            details="Please use receive_from_stream() instead.",
        ),
        DeprecationWarning,
        stacklevel=2,
    )
    _receive_from_opnic_stream(stream, struct)


def _receive_from_opnic_stream(stream: QuaExternalIncomingStream[StructT], struct: StructT) -> None:
    try:
        _ = struct.struct_reference
    except AttributeError:
        raise QmQuaException(
            f"Data received from an opnic stream must be saved into a struct instance. got {type(struct).__name__} instead."
        )

    statement = inc_qua_pb2.QuaProgram.AnyStatement(
        receiveFromExternalStream=inc_qua_pb2.QuaProgram.ReceiveFromExternalStreamStatement(
            loc=_get_loc(), stream=stream.unwrapped, struct=struct.struct_reference.unwrapped
        )
    )
    scopes_manager.append_statement(statement)
