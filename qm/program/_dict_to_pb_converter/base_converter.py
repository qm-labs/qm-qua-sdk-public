from copy import copy
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type, Generic, Mapping, TypeVar, Optional, Collection, cast

import betterproto

from qm.exceptions import ConfigValidationException
from qm.api.models.capabilities import QopCaps, ServerCapabilities

InputType = TypeVar("InputType", bound=Mapping[str, Any])
OutputType = TypeVar("OutputType", bound=betterproto.Message)
T = TypeVar("T", bound=Mapping[str, Any])


class BaseDictToPbConverter(Generic[InputType, OutputType], ABC):
    def __init__(self, capabilities: ServerCapabilities, init_mode: bool) -> None:
        self._capabilities = capabilities
        self._init_mode = init_mode

    @abstractmethod
    def convert(self, input_data: InputType) -> OutputType:
        pass

    @abstractmethod
    def deconvert(self, output_data: OutputType) -> InputType:
        pass

    def _apply_defaults(
        self,
        config: T,
        default_schema: T,
    ) -> T:
        """
        Merge default values into the configuration dictionary, if applicable.

        If `init_mode` is True, missing keys from `config` will be filled in using `default_schema`.
        If `init_mode` is False and the server supports `config_v2`, the original `config` is returned unchanged (in
        config_v1 defaults will always be applied).

        Args:
            config (T): A user-defined config, possibly missing some keys.
            default_schema (T): Schema with default values for keys (possibly missing some keys).

        Returns:
            A new config dictionary with defaults applied, or the original config.
        """

        if not self._init_mode and self._capabilities.supports(QopCaps.config_v2):
            return config

        # The casting is that mypy will allow the update method
        new_config = cast(Dict[Any, Any], copy(default_schema))
        new_config.update(config)
        return cast(T, new_config)

    def _set_pb_attr_config_v2(
        self,
        item: betterproto.Message,
        value: Any,
        v1_attr: str,
        v2_attr: str,
        allow_nones: bool = False,
        create_container: Optional[Type[betterproto.Message]] = None,
    ) -> None:
        if not hasattr(item, v1_attr) or not hasattr(item, v2_attr):
            raise AttributeError(f"Either {v1_attr} or {v2_attr} do not exist in {item}")

        if value is None and not allow_nones:
            return

        if self._capabilities.supports(QopCaps.config_v2):
            container_message = getattr(item, v2_attr)

            if container_message is None and create_container:
                container_message = create_container()
                setattr(item, v2_attr, container_message)

            if not hasattr(container_message, "value"):
                raise AttributeError(f"{v2_attr} does not have a 'value' attribute")

            container_message.value = value
        else:
            setattr(item, v1_attr, value)

    @staticmethod
    def _validate_required_fields(config: Mapping[str, Any], fields: List[str], parent_field: str) -> None:
        for field in fields:
            if field not in config:
                raise ConfigValidationException(f"{field} should be declared when initializing a {parent_field}")

    @staticmethod
    def _validate_unsupported_params(
        data: Collection[str],
        unsupported_params: Collection[str],
        supported_params: Collection[str],
        supported_from: Optional[str] = None,
        supported_until: Optional[str] = None,
    ) -> None:
        if set(data) & set(unsupported_params):
            if supported_from:
                unsupported_message = f"supported only from QOP {supported_from} and later"
            elif supported_until:
                unsupported_message = f"supported only until QOP {supported_until}"
            else:
                raise ValueError("Either 'supported_from' or 'supported_until' must be provided.")

            raise ConfigValidationException(
                f"The configuration keys {unsupported_params} are {unsupported_message}. "
                f"Use the keys {supported_params} instead."
            )
