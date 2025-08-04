import warnings

from qm.simulate import SimulatorSamples, SimulatorControllerSamples

from ..utils import deprecation_message
from .._stream_results import (
    StreamsManager,
    StreamingResultFetcher,
    SingleStreamingResultFetcher,
    MultipleStreamingResultFetcher,
    SingleStreamSingleResultFetcher,
    SingleStreamMultipleResultFetcher,
)

warnings.warn(
    deprecation_message(
        "qm.results",
        "1.2.3",
        "1.3.0",
        "If you need anything from this module, import it directly from `qm` or from `qm.simulate` for simulator-related functionality.",
    ),
    DeprecationWarning,
)


__all__ = [
    "StreamsManager",
    "StreamingResultFetcher",
    "SingleStreamingResultFetcher",
    "MultipleStreamingResultFetcher",
    "SingleStreamSingleResultFetcher",
    "SingleStreamMultipleResultFetcher",
    "SimulatorSamples",
    "SimulatorControllerSamples",
]
