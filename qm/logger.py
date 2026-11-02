import logging

from qm.utils.deprecation_utils import QmQuaDeprecationWarning, throw_warning

logger = logging.getLogger("qm")
throw_warning(
    "Directly importing the logger is deprecated and will not work in future versions. "
    "To change logging levels, you can either use the function `set_logging_level(...)` from `qm.logging_utils` "
    'or you can use python native `logging.getLogger("qm").setLevel(...)`',
    category=QmQuaDeprecationWarning,
    stacklevel=2,
)
