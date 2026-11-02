from typing import Optional
from typing_extensions import deprecated

from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.type_hinting.config_types import FullQuaConfig
from qm.utils.deprecation_utils import QmQuaDeprecationWarning
from qm.api.models.capabilities import ServerCapabilities, offline_capabilities

from ._dict_to_pb_converter import DictToQuaConfigConverter


@deprecated(
    'convert_msg_to_config is deprecated since "1.2.4" and will be removed in "2.0.0". This function is removed, if you need an alternative, please contact QM.',
    category=QmQuaDeprecationWarning,
    stacklevel=1,
)
def convert_msg_to_config(
    config: inc_qua_config_pb2.QuaConfig,
    capabilities: Optional[ServerCapabilities] = None,
) -> FullQuaConfig:
    """Convert a protobuf config message back into a config dictionary.

    Deprecated since 1.2.4; will be removed in 2.0.0. If you need an alternative, please contact QM.

    Args:
        config: The protobuf config message to convert.
        capabilities: The server capabilities used during conversion. If ``None``, the offline capabilities are used.

    Returns:
        The config as a dictionary.
    """
    capabilities = capabilities if capabilities is not None else offline_capabilities
    converter = DictToQuaConfigConverter(capabilities)
    return converter.deconvert(config)
