import warnings
from typing import Optional

from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.type_hinting.config_types import FullQuaConfig
from qm.api.models.capabilities import ServerCapabilities, offline_capabilities

from ..utils import deprecation_message
from ._dict_to_pb_converter import DictToQuaConfigConverter


def convert_msg_to_config(
    config: inc_qua_config_pb2.QuaConfig,
    capabilities: Optional[ServerCapabilities] = None,
) -> FullQuaConfig:
    """Convert a protobuf config message back into a config dictionary.

    Deprecated since 1.2.4; will be removed in 2.0.0. If you need an alternative, please contact QM.
    """
    capabilities = capabilities if capabilities is not None else offline_capabilities
    warnings.warn(
        deprecation_message(
            method="convert_msg_to_config",
            deprecated_in="1.2.4",
            removed_in="2.0.0",
            details="This function is removed, if you need an alternative, please contact QM.",
        ),
        DeprecationWarning,
    )
    converter = DictToQuaConfigConverter(capabilities)
    return converter.deconvert(config)
