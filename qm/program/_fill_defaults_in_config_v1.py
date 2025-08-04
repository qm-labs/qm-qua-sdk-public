from dataclasses import fields, is_dataclass
from typing import Any, Type, Union, get_args, get_origin, get_type_hints

import betterproto

from qm.utils.config_utils import get_controller_pb_config
from qm.grpc.qua_config import QuaConfig, QuaConfigQuaConfigV1


def fill_defaults_in_config_v1(config: QuaConfig) -> None:
    """
    Since proto values for the controller configuration were made optional, a subtle bug was introduced in the older
    config version (v1). When fetching the config from the gateway, it returns None for fields with default gRPC values.
    For instance, the default gRPC value for a float is 0.0. If a user set an offset of 0.0 and fetched the config,
    they would receive None. This issue arose with the introduction of "optional" labels in config_v2, because beforehand
    when fields were not marked as optional, the None values would automatically be converted to the default grpc value.
    TLDR: SDK version with optional labels result in None values when working with gateway version that doesn't have
    optional labels.
    Consequently, validation tests such as test_config_supports_shareable_ports and test_config_without_shareable would
    fail.
    """
    controller_config = get_controller_pb_config(config)
    if isinstance(controller_config, QuaConfigQuaConfigV1):
        for _, control_devices_data in controller_config.control_devices.items():
            _fill_defaults(control_devices_data)

        for _, controllers_data in controller_config.controllers.items():
            _fill_defaults(controllers_data)


# These fields should remain with None values.
FIELDS_TO_EXCLUDE = [
    "high_pass"
]  # The high_pass field was configured as optional before config_v2, and therefore should remain as None.

PRIMITIVE_TYPES = (int, float, str, bool)


def _fill_defaults(obj: betterproto.Message) -> None:
    """Fill default values for fields of a single message object (with recursive functionality)."""
    if not is_dataclass(obj):
        return

    hints = get_type_hints(type(obj))
    for field in fields(obj):
        field_name = field.name

        # Skip unset "oneof" fields to avoid exceptions when accessing them. Also skip fields that are explicitly excluded.
        if not hasattr(obj, field_name) or field_name in FIELDS_TO_EXCLUDE:
            continue

        value = getattr(obj, field_name)

        typ = _unwrap_optional(hints.get(field_name))

        if value is None:
            default_value = _get_default_value(typ)
            if default_value is not None:
                setattr(obj, field_name, default_value)
        else:
            _apply_to_nested(value)


def _unwrap_optional(typ: Type[Any]) -> Any:
    """Return the inner type from Optional[T], or the original type."""
    origin = get_origin(typ)
    if origin is Union:
        args = get_args(typ)
        none_type = type(None)  # We don't use it directly in the list comprehension just for flake8 reasons
        non_none_args = [arg for arg in args if arg is not none_type]
        if len(non_none_args) > 1:
            raise TypeError(
                f"Unexpected Union with multiple non-None types: {non_none_args}."
                f"Expected a simple Optional[T] (i.e., Union[T, NoneType]) with exactly one non-None type."
            )
        return non_none_args[0]
    return typ


def _apply_to_nested(value: Any) -> None:
    """Recursively apply the 'fill_defaults' function to messages, lists, or dicts of messages."""
    if isinstance(value, PRIMITIVE_TYPES):
        # Not nested, so we skip
        pass
    elif isinstance(value, betterproto.Message):
        _fill_defaults(value)
    # Tuples and sets aren't standard in proto, but included for forward compatibility and custom extensions.
    elif isinstance(value, list) or isinstance(value, tuple) or isinstance(value, set):
        for item in value:
            _apply_to_nested(item)
    elif isinstance(value, dict):
        for val in value.values():
            _apply_to_nested(val)
    else:
        raise TypeError(f"Unsupported nested value type: {type(value)}")


def _get_default_value(typ: Type[Any]) -> Any:
    """Return the default value for the given type."""
    if typ in PRIMITIVE_TYPES:
        return typ()  # Returns the default value for each primitive type (0 for int, etc.)
    if isinstance(typ, type) and issubclass(typ, betterproto.Enum):
        # For enums, the first value is the default value
        return next(iter(typ))
    return None
