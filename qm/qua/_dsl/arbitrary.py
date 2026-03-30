from typing import Type, Tuple, Union, Optional

from google.protobuf.message import Message as PbMessage

from qm._loc import _get_loc
from qm.grpc.qm.pb import inc_qua_pb2
from qm.exceptions import QmQuaException
from qm.qua._scope_management.scopes import _ArbitraryScope
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._dsl.proto_any_converter import ProtoMessageT, any_to_proto, proto_to_any


def get_arbitrary_message(name: str, message: PbMessage) -> inc_qua_pb2.QuaProgram.AnyStatement:
    """
    Create an arbitrary message statement to support non-qua messages.

    Args:
        name (str): message name, used to identify the message type.
        message (PbMessage): the message needs to be encapsulated.

    Returns:
        QuaProgram.AnyStatement: The arbitrary message statement.
    """
    loc = _get_loc()
    proto_any = proto_to_any(message)
    statement = inc_qua_pb2.QuaProgram.ArbitraryStatement(
        loc=loc,
        name=name,
        data=proto_any,
    )
    return inc_qua_pb2.QuaProgram.AnyStatement(arbitrary=statement)


def arbitrary(name: str, message: PbMessage) -> None:
    """arbitrary message to support non-qua messages.

    For example, this can be used to send a protobuf message as long as the client and the server know the message type.

    Args:
        name (str): message name, used to identify the message type.
        message (PbMessage): the message needs to be encapsulated.
    """
    statement = get_arbitrary_message(name, message)
    scopes_manager.append_statement(statement)


def parse_arbitrary(b: bytes) -> inc_qua_pb2.QuaProgram.ArbitraryStatement:
    """
    Parse an arbitrary statement from bytes.

    Args:
        b (bytes): The bytes to parse.

    Returns:
        QuaProgram.ArbitraryStatement: The parsed arbitrary statement.
    """
    parsed_message = inc_qua_pb2.QuaProgram.AnyStatement()
    parsed_message.ParseFromString(b)
    if not parsed_message.HasField("arbitrary"):
        raise QmQuaException("Failed to parse arbitrary statement, expected 'arbitrary' field not found.")
    return parsed_message.arbitrary


def arbitrary_context(name: str, data: Optional[PbMessage] = None) -> _ArbitraryScope:
    """
    arbitrary context message to support non-qua contexts.

    For example, this can be used to send a protobuf message as long as the client and the server know the message type.

    Args:
        name (str): message name, used to identify the message type.
        data (Any): the message name data.

    Returns:
        Scope: An arbitrary scope that can be used to wrap statements.
    """
    if isinstance(data, PbMessage):
        data_to_context = proto_to_any(data)
    else:
        data_to_context = None
    return _ArbitraryScope(loc=_get_loc(), name=name, data=data_to_context)


def extract_from_arbitrary(
    statement: Union[inc_qua_pb2.QuaProgram.ArbitraryStatement, inc_qua_pb2.QuaProgram.ArbitraryContextStatement],
    message_cls: Type[ProtoMessageT],
) -> Tuple[str, Optional[ProtoMessageT]]:
    """
    Extracts the name and data from an arbitrary statement.

    Args:
        statement (QuaProgram.ArbitraryStatement or QuaProgram.ArbitraryContextStatement): The statement to extract from.
        message_cls (Type[ProtoMessageT]): The message class to unpack into.

    Returns:
        Tuple[str, Optional[ProtoMessageT]]: The name and the unpacked message.
    """

    message: Union[ProtoMessageT, None]
    if statement.HasField("data"):
        if issubclass(message_cls, PbMessage):
            message = any_to_proto(statement.data, message_cls)
        else:
            raise QmQuaException(f"unsupported arbitrary statement, expected PbMessage, got {message_cls}")
    else:
        message = None

    return statement.name, message
