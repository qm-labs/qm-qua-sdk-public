from dependency_injector.wiring import Provide, inject

from qm.grpc.qua_config import QuaConfig
from qm.type_hinting.config_types import FullQuaConfig
from qm.api.models.capabilities import ServerCapabilities
from qm.containers.capabilities_container import CapabilitiesContainer

from ._dict_to_pb_converter import DictToQuaConfigConverter


@inject
def convert_msg_to_config(
    config: QuaConfig,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> FullQuaConfig:
    converter = DictToQuaConfigConverter(capabilities)
    return converter.deconvert(config)
