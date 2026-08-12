from abc import ABC, abstractmethod
from typing import Any, Type, Generic, TypeVar

from google.protobuf.message import Message

from qm.config._primitives import NOT_SET
from qm.utils.protobuf_utils import assign_to_proto
from qm.api.models.capabilities import QopCaps, ServerCapabilities

InputType = TypeVar("InputType")
OutputType = TypeVar("OutputType")


class BaseModelToPbConverter(Generic[InputType, OutputType], ABC):
    def __init__(self, capabilities: ServerCapabilities, init_mode: bool) -> None:
        self._capabilities = capabilities
        self._init_mode = init_mode

    @property
    def _should_apply_defaults(self) -> bool:
        return self._init_mode or not self._capabilities.supports(QopCaps.config_v2)

    @abstractmethod
    def convert(self, input_data: InputType) -> OutputType:
        pass

    @abstractmethod
    def deconvert(self, output_data: OutputType) -> InputType:
        pass

    def _set_pb_attr_config_v2(
        self,
        item: Message,
        value: Any,
        v1_attr: str,
        v2_attr: str,
        allow_nones: bool = False,
        create_container: Type[Message] | None = None,
    ) -> None:
        if not hasattr(item, v1_attr) or not hasattr(item, v2_attr):
            raise AttributeError(f"Either {v1_attr} or {v2_attr} do not exist in {item}")

        if value == NOT_SET and not allow_nones:
            return

        if self._capabilities.supports(QopCaps.config_v2):
            container_message = getattr(item, v2_attr)

            if container_message is None and create_container:
                container_message = create_container()
                setattr(item, v2_attr, container_message)

            if not hasattr(container_message, "value"):
                raise AttributeError(f"{v2_attr} does not have a 'value' attribute")
            assign_to_proto(container_message, "value", value)
        else:
            if value:
                assign_to_proto(item, v1_attr, value)
