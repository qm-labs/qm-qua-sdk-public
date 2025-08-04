from typing import Type, TypeVar

import betterproto
from google.protobuf.any_pb2 import Any as PbAny
from google.protobuf.message import Message as PbMessage
from betterproto.lib.google.protobuf import Any as BetterAny

BetterProtoMessageT = TypeVar("BetterProtoMessageT", bound=betterproto.Message)
ProtoMessageT = TypeVar("ProtoMessageT", bound=PbMessage)


def betterproto_to_any(message: betterproto.Message) -> BetterAny:
    """
    Converts a betterproto message to a betterproto Any message.
    Args:
        message (betterproto.Message): A betterproto message instance.
    Returns:
        BetterAny: The packed Any message.
    """
    any_message = BetterAny()
    any_message.type_url = f"type.googleapis.com/{message.__class__.__name__}"
    any_message.value = message.SerializeToString()
    return any_message


def any_to_betterproto(any_message: BetterAny, message_cls: Type[BetterProtoMessageT]) -> BetterProtoMessageT:
    """
    Converts a protobuf Any message to a betterproto message of the given class.

    Args:
        any_message (any_pb2.Any): The protobuf Any message to unpack.
        message_cls (type[betterproto.Message]): The betterproto message class to unpack into.

    Returns:
        betterproto.Message: The unpacked betterproto message.
    """
    message = message_cls().parse(any_message.value)
    return message


def proto_to_any(message: PbMessage) -> BetterAny:
    """
    Packs a standard protobuf message into a betterproto Any message.

    Args:
        message (PbMessage): A protobuf message instance.

    Returns:
        BetterAny: The packed Any message.
    """
    any_pb_message = PbAny()
    any_pb_message.Pack(message)
    return BetterAny(type_url=any_pb_message.type_url, value=any_pb_message.value)


def any_to_proto(any_message: BetterAny, message_cls: Type[ProtoMessageT]) -> ProtoMessageT:
    """
    Converts a betterproto Any message into a standard protobuf message.

    Args:
        any_message (BetterAny): The betterproto Any message.
        message_cls (Type[ProtoMessageT]): The expected protobuf message class to unpack into.

    Returns:
        PbMessage: The unpacked protobuf message.
    """
    message = message_cls()
    message.ParseFromString(any_message.value)
    return message
