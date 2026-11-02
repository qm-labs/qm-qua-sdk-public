from qm.quantum_machine import QuantumMachine  # noqa
from qm.utils.deprecation_utils import QmQuaDeprecationWarning, throw_warning

throw_warning(
    "'qm.QuantumMachine.QuantumMachine' is moved as of 1.2.0 and will be removed in 2.0.0. "
    "use 'qm.QuantumMachine' instead",
    category=QmQuaDeprecationWarning,
    stacklevel=2,
)
