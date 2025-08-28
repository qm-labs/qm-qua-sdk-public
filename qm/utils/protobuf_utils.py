import logging
import dataclasses
from typing import Union, cast
from collections.abc import Iterable

import betterproto

from qm.grpc.general_messages import MessageLevel
from qm.type_hinting.general import DataclassProtocol

LOG_LEVEL_MAP = {
    MessageLevel.Message_LEVEL_ERROR: logging.ERROR,
    MessageLevel.Message_LEVEL_WARNING: logging.WARN,
    MessageLevel.Message_LEVEL_INFO: logging.INFO,
}


Node = Union[betterproto.Message, Iterable["Node"]]


def list_fields(node: Node) -> dict[str, Node]:
    fields = dataclasses.fields(cast(DataclassProtocol, node))
    output = {}
    for field in fields:
        try:
            field_value = getattr(node, field.name)
        except AttributeError:  # this deals with non-serialized fields in betterproto
            continue
        if isinstance(field_value, Iterable) or (
            isinstance(field_value, betterproto.Message) and betterproto.serialized_on_wire(field_value)
        ):
            output[field.name] = field_value
    return output
