import warnings
from typing import Union

from qm.exceptions import QmQuaException
from qm.utils import deprecation_message
from qm.qua._dsl._type_hints import MessageExpressionType
from qm.qua._expressions import literal_int, literal_bool, literal_real


def L(value: Union[bool, int, float]) -> MessageExpressionType:
    warnings.warn(deprecation_message("L", "1.2.3", "1.3.0"), DeprecationWarning, stacklevel=2)
    if isinstance(value, bool):
        return literal_bool(value)
    if isinstance(value, int):
        return literal_int(value)
    if isinstance(value, float):
        return literal_real(value)
    raise QmQuaException("literal can be bool, int or float")
