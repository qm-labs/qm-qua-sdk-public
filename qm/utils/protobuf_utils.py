import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Union, TypeVar, MutableMapping, MutableSequence

from google.protobuf.message import Message
from google.protobuf.timestamp_pb2 import Timestamp

from qm.exceptions import QmQuaException
from qm.grpc.qm.pb import general_messages_pb2

LOG_LEVEL_MAP = {
    general_messages_pb2.MessageLevel.Message_LEVEL_ERROR: logging.ERROR,
    general_messages_pb2.MessageLevel.Message_LEVEL_WARNING: logging.WARN,
    general_messages_pb2.MessageLevel.Message_LEVEL_INFO: logging.INFO,
}


Node = Union[Message, Iterable["Node"]]
PROTOBUF_SCALAR_TYPES = (int, float, bool, str, bytes)


def list_fields(node: Message) -> dict[str, Node]:
    output: dict[str, Node] = {}
    for field in node.DESCRIPTOR.fields:
        field_value = getattr(node, field.name)
        if isinstance(field_value, PROTOBUF_SCALAR_TYPES):
            continue
        if isinstance(field_value, Iterable):
            output[field.name] = field_value
        elif node.HasField(field.name):
            if isinstance(field_value, Message) and serialized_on_wire(field_value):
                output[field.name] = field_value

    return output


def which_one_of(message: Message, oneof_group: str) -> tuple[str, Union[Any, None]]:
    """Return the name of the field set in the oneof group, or None if none is set."""
    oneof_name = message.WhichOneof(oneof_group)
    if oneof_name is None:
        return "None", None
    return oneof_name, getattr(message, oneof_name)


K = TypeVar("K")
V = TypeVar("V")


def update_map(map_container: MutableMapping[K, V], data: dict[K, V]) -> None:
    """Update the map with new values."""
    for key, value in data.items():
        if value:
            if isinstance(value, PROTOBUF_SCALAR_TYPES):
                map_container[key] = value
            elif isinstance(value, Message):
                item = map_container[key]
                if not isinstance(item, Message):
                    raise QmQuaException(
                        f"not matching map value to dict value, expected {type(value)}, got {type(item)}"
                    )
                item.CopyFrom(value)
            else:
                raise QmQuaException(f"not supported protobuf type: {type(value)}")
        else:
            del map_container[key]


def proto_map_to_dict(map_container: MutableMapping[K, V]) -> dict[K, V]:
    return {k: v for k, v in map_container.items()}


def assign_map(map_container: MutableMapping[K, V], data: dict[K, V]) -> None:
    """Assign a mapping to a map field in the protobuf message."""
    if hasattr(map_container, "clear"):
        map_container.clear()
    else:
        for k in list(map_container.keys()):
            del map_container[k]
    update_map(map_container, data)


T = TypeVar("T")


def proto_repeated_to_list(repeated_container: MutableSequence[T]) -> list[T]:
    return [v for v in repeated_container]


def assign_repeated(repeated_container: MutableSequence[T], items: Iterable[T]) -> None:
    """Assign a sequence to a repeated field in the protobuf message."""
    if hasattr(repeated_container, "clear"):
        repeated_container.clear()
    else:
        # Fallback for older protobuf versions without clear()
        del repeated_container[:]
    repeated_container.extend(items)


def assign_to_proto(msg: Message, field_name: str, value: Any) -> None:
    value_field = getattr(msg, field_name)
    if isinstance(value_field, MutableMapping):
        assign_map(value_field, value)
    elif isinstance(value_field, MutableSequence):
        assign_repeated(value_field, value)
    elif isinstance(value_field, Message):
        value_field.CopyFrom(value)
    elif isinstance(value_field, PROTOBUF_SCALAR_TYPES):
        setattr(msg, field_name, value)
    else:
        raise QmQuaException(f"not supported protobuf type: {type(value_field)}")


def serialized_on_wire(message: Message) -> bool:
    """Check if message would be serialized (has non-default content)"""
    serialized = message.SerializeToString()
    return len(serialized) > 0


def timestamp_to_datetime(ts: Timestamp) -> datetime:
    # Convert protobuf Timestamp → Python datetime (UTC)
    return ts.ToDatetime().replace(tzinfo=timezone.utc)
