from qm.utils.deprecation_utils import throw_warning
from qm.quantum_machine import QuantumMachine  # noqa

throw_warning(
    "'qm.QuantumMachine.QuantumMachine' is moved as of 1.2.0 and will be removed in 1.4.0. "
    "use 'qm.QuantumMachine' instead",
    category=DeprecationWarning,
    stacklevel=2,
)
