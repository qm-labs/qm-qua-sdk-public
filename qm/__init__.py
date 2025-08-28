import logging
import warnings

from qm.jobs.qm_job import QmJob  # noqa
from qm.version import __version__  # noqa
from qm.logging_utils import config_loggers
from qm.jobs.job_queue_old_api import QmQueue
from qm.user_config import UserConfig  # noqa
from qm.program import Program, _Program  # noqa
from qm.jobs.pending_job import QmPendingJob  # noqa
from qm.quantum_machine import QuantumMachine  # noqa
from qm.api.models.capabilities import QopCaps  # noqa
from qm.type_hinting import DictQuaConfig, FullQuaConfig  # noqa
from qm.api.models.compiler import CompilerOptionArguments  # noqa
from qm.quantum_machines_manager import QuantumMachinesManager  # noqa
from qm.serialization.generate_qua_script import generate_qua_script  # noqa
from qm.simulate import (  # noqa
    InterOpxAddress,
    InterOpxChannel,
    InterOpxPairing,
    SimulationConfig,
    SimulatorSamples,
    LoopbackInterface,
    ControllerConnection,
    SimulatorControllerSamples,
)

from ._stream_results import (  # noqa
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
