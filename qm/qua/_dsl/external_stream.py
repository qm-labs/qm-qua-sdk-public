from enum import Enum
from typing import Union, Literal, overload

from qm._loc import _get_loc
from qm.exceptions import QmQuaException
from qm.api.models.capabilities import QopCaps
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._expressions import StructT, QuaExternalIncomingStream, QuaExternalOutgoingStream
from qm.grpc.qua import (
    QuaProgramAnyStatement,
    QuaProgramSendToExternalStreamStatement,
    QuaProgramReceiveFromExternalStreamStatement,
)


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

    Note:
        Alpha version.
        This function may change its signature and behavior in the future without obeying semantic
        versioning and without maintaining backward compatibility.

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
    program_scope = scopes_manager.program_scope
    program_scope.add_used_capability(QopCaps.external_stream)

    if not isinstance(stream_id, int):
        raise QmQuaException("stream_id must be an integer")

    if not 1 <= stream_id <= 1023:
        raise QmQuaException("stream_id must be between 1 and 1023")

    stream: Union[QuaExternalIncomingStream[StructT], QuaExternalOutgoingStream[StructT]]

    stream_identifier = (stream_id, direction)
    if stream_identifier in program_scope.declared_external_streams:
        raise QmQuaException("external stream already declared")

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

    Note:
        Alpha version.
        This function may change its signature and behavior in the future without obeying semantic
        versioning and without maintaining backward compatibility.

    Args:
        stream: The outgoing stream to send data to.
        struct: The struct containing the data to send.
    """
    statement = QuaProgramAnyStatement(
        send_to_external_stream=QuaProgramSendToExternalStreamStatement(
            loc=_get_loc(), stream=stream.unwrapped, struct=struct.struct_reference.unwrapped
        )
    )
    scopes_manager.append_statement(statement)


def receive_from_external_stream(stream: QuaExternalIncomingStream[StructT], struct: StructT) -> None:
    """
    Receive data from an external compute resource.

    Note:
        Alpha version.
        This function may change its signature and behavior in the future without obeying semantic
        versioning and without maintaining backward compatibility.

    Args:
        stream: The incoming stream to receive data from.
        struct: The struct to store the received data in.
    """
    statement = QuaProgramAnyStatement(
        receive_from_external_stream=QuaProgramReceiveFromExternalStreamStatement(
            loc=_get_loc(), stream=stream.unwrapped, struct=struct.struct_reference.unwrapped
        )
    )
    scopes_manager.append_statement(statement)
