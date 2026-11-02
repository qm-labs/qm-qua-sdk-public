from typing import Union
from typing_extensions import deprecated

from qm.exceptions import QmQuaException
from qm.qua._dsl._type_hints import MessageExpressionType
from qm.utils.deprecation_utils import QmQuaDeprecationWarning
from qm.qua._expressions import literal_int, literal_bool, literal_real


@deprecated(
    'L is deprecated since "1.2.3" and will be removed in "2.0.0"',
    category=QmQuaDeprecationWarning,
    stacklevel=1,
)
def L(value: Union[bool, int, float]) -> MessageExpressionType:
    """Create a QUA literal from a Python ``bool``, ``int``, or ``float``.

    Deprecated since 1.2.3; will be removed in 2.0.0.

    Args:
        value: the Python ``bool``, ``int``, or ``float`` to wrap as a QUA literal.

    Returns:
        A QUA literal expression representing the given value.
    """
    if isinstance(value, bool):
        return literal_bool(value)
    if isinstance(value, int):
        return literal_int(value)
    if isinstance(value, float):
        return literal_real(value)
    raise QmQuaException("literal can be bool, int or float")
