from typing import Type, Tuple, Union, Optional, overload

import betterproto
from google.protobuf.message import Message as PbMessage

from qm._loc import _get_loc
from qm.exceptions import QmQuaException
from qm.qua._scope_management.scopes import _ArbitraryScope
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.grpc.qua import QuaProgramAnyStatement, QuaProgramArbitraryStatement, QuaProgramArbitraryContextStatement
from qm.qua._dsl.proto_any_converter import (
    ProtoMessageT,
    BetterProtoMessageT,
    any_to_proto,
    proto_to_any,
    any_to_betterproto,
    betterproto_to_any,
)


def get_arbitrary_message(name: str, message: Union[betterproto.Message, PbMessage]) -> QuaProgramAnyStatement:
    """
    Create an arbitrary message statement to support non-qua messages.
    Args:
        name (str): message name, used to identify the message type.
        message (betterproto.Message/pb message): the message needs to be encapsulated.
    Returns:
        QuaProgramAnyStatement: The arbitrary message statement.
    """
    loc = _get_loc()
    betterproto_any = betterproto_to_any(message) if isinstance(message, betterproto.Message) else proto_to_any(message)
    statement = QuaProgramArbitraryStatement(
        loc=loc,
        name=name,
        data=betterproto_any,
    )
    return QuaProgramAnyStatement(arbitrary=statement)


def arbitrary(name: str, message: Union[betterproto.Message, PbMessage]) -> None:
    """arbitrary message to support non-qua messages.

    For example, this can be used to send a protobuf message as long as the client and the server know the message type.

    Args:
        name (str): message name, used to identify the message type.
        message (betterproto.Message/pb message): the message needs to be encapsulated.
    """
    statement = get_arbitrary_message(name, message)
    scopes_manager.append_statement(statement)


def parse_arbitrary(b: bytes) -> QuaProgramArbitraryStatement:
    """
    Parse an arbitrary statement from bytes.

    Args:
        b (bytes): The bytes to parse.
    Returns:
        QuaProgramArbitraryStatement: The parsed arbitrary statement.
    """
    parsed_message = QuaProgramAnyStatement().parse(b)
    if not parsed_message.is_set("arbitrary"):
        raise QmQuaException("Failed to parse arbitrary statement, expected 'arbitrary' field not found.")
    return parsed_message.arbitrary


def arbitrary_context(name: str, data: Optional[Union[betterproto.Message, PbMessage]] = None) -> _ArbitraryScope:
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
    elif isinstance(data, betterproto.Message):
        data_to_context = betterproto_to_any(data)
    else:
        data_to_context = None
    return _ArbitraryScope(loc=_get_loc(), name=name, data=data_to_context)


@overload
def extract_from_arbitrary(
    statement: Union[QuaProgramArbitraryStatement, QuaProgramArbitraryContextStatement],
    message_cls: Type[BetterProtoMessageT],
) -> Tuple[str, Optional[BetterProtoMessageT]]:
    ...


@overload
def extract_from_arbitrary(
    statement: Union[QuaProgramArbitraryStatement, QuaProgramArbitraryContextStatement],
    message_cls: Type[ProtoMessageT],
) -> Tuple[str, Optional[ProtoMessageT]]:
    ...


def extract_from_arbitrary(
    statement: Union[QuaProgramArbitraryStatement, QuaProgramArbitraryContextStatement],
    message_cls: Union[Type[BetterProtoMessageT], Type[ProtoMessageT]],
) -> Tuple[str, Optional[Union[BetterProtoMessageT, ProtoMessageT]]]:
    """
    Extracts the name and data from an arbitrary statement.
    Args:
        statement (QuaProgramArbitraryStatement or QuaProgramArbitraryContextStatement): The statement to extract from.
        message_cls (Type[BetterProtoMessageT] or Type[ProtoMessageT]): The message class to unpack into.
    Returns:
        Tuple[str, Optional[Union[BetterProtoMessageT, ProtoMessageT]]]: The name and the unpacked message.
    """

    message: Union[BetterProtoMessageT, ProtoMessageT, None]
    if statement.data is None:
        message = None
    elif issubclass(message_cls, betterproto.Message):
        message = any_to_betterproto(statement.data, message_cls)
    elif issubclass(message_cls, PbMessage):
        message = any_to_proto(statement.data, message_cls)
    else:
        raise QmQuaException(
            f"unsupported arbitrary statement, support betterproto.Message or PbMessage, got {message_cls}"
        )

    return statement.name, message
