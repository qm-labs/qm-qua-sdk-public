import logging
import warnings

# Suppress protobuf runtime version warnings for cross-version compatibility (must be before protobuf imports)
warnings.filterwarnings("ignore", category=UserWarning, module="google.protobuf.runtime_version")

from qm.jobs.qm_job import QmJob  # noqa: E402
from qm.version import __version__  # noqa: E402
from qm.user_config import UserConfig  # noqa: E402
from qm.program import Program, _Program  # noqa: E402
from qm.logging_utils import config_loggers  # noqa: E402
from qm.jobs.pending_job import QmPendingJob  # noqa: E402
from qm.jobs.job_queue_old_api import QmQueue  # noqa: E402
from qm.quantum_machine import QuantumMachine  # noqa: E402
from qm.api.models.capabilities import QopCaps  # noqa: E402
from qm.type_hinting import DictQuaConfig, FullQuaConfig  # noqa: E402
from qm.api.models.compiler import CompilerOptionArguments  # noqa: E402
from qm.quantum_machines_manager import QuantumMachinesManager  # noqa: E402
from qm.serialization.generate_qua_script import generate_qua_script  # noqa: E402
from qm.simulate import (  # noqa: E402
    InterOpxAddress,
    InterOpxChannel,
    InterOpxPairing,
    SimulationConfig,
    SimulatorSamples,
    LoopbackInterface,
    ControllerConnection,
    SimulatorControllerSamples,
)

from ._stream_results import (  # noqa: E402
    StreamsManager,
    StreamingResultFetcher,
    BaseSingleStreamFetcher,
    SingleStreamingResultFetcher,
    MultipleStreamingResultFetcher,
    SingleStreamSingleResultFetcher,
    SingleStreamMultipleResultFetcher,
)

__all__ = [
    "QuantumMachinesManager",
    "QuantumMachine",
    "QmPendingJob",
    "QmJob",
    "StreamsManager",
    "BaseSingleStreamFetcher",
    "StreamingResultFetcher",
    "SingleStreamingResultFetcher",
    "MultipleStreamingResultFetcher",
    "SingleStreamSingleResultFetcher",
    "SingleStreamMultipleResultFetcher",
    "Program",
    "CompilerOptionArguments",
    "generate_qua_script",
    "config_loggers",
    "UserConfig",
    "SimulationConfig",
    "InterOpxAddress",
    "InterOpxChannel",
    "ControllerConnection",
    "InterOpxPairing",
    "LoopbackInterface",
    "FullQuaConfig",
    "DictQuaConfig",
    "QopCaps",
    "SimulatorSamples",
    "SimulatorControllerSamples",
]

warnings.filterwarnings("default", category=DeprecationWarning, module="qm")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="qm.grpc")

config = UserConfig.create_from_file()
config_loggers(config)


logger = logging.getLogger(__name__)
logger.info(f"Starting session: {config.SESSION_ID}")
