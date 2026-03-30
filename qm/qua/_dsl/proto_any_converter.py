from typing import Type, TypeVar

from google.protobuf.any_pb2 import Any
from google.protobuf.message import Message

ProtoMessageT = TypeVar("ProtoMessageT", bound=Message)


def proto_to_any(message: Message) -> Any:
    """
    Packs a standard protobuf message into a protobuf Any message.

    Args:
        message (Message): A protobuf message instance.

    Returns:
        Any: The packed Any message.
    """
    any_pb_message = Any()
    any_pb_message.Pack(message)
    return any_pb_message


def any_to_proto(any_message: Any, message_cls: Type[ProtoMessageT]) -> ProtoMessageT:
    """
    Converts a protobuf Any message into a standard protobuf message.

    Args:
        any_message (Any): The protobuf Any message.
        message_cls (Type[ProtoMessageT]): The expected protobuf message class to unpack into.

    Returns:
        Message: The unpacked protobuf message.
    """
    message = message_cls()
    any_message.Unpack(message)
    return message
