import warnings

from qm.utils import deprecation_message
from qm.simulate._simulator_samples import SimulatorSamples, SimulatorControllerSamples

__all__ = ["SimulatorSamples", "SimulatorControllerSamples"]


warnings.warn(
    deprecation_message(
        "qm.results.simulator_samples",
        deprecated_in="1.2.3",
        removed_in="1.3.0",
        details="please import `SimulatorSamples` and `SimulatorControllerSamples` directly from qm.",
    ),
    DeprecationWarning,
    stacklevel=2,
)
