import os
import pathlib
from typing import Any, Dict, Union, ClassVar, Protocol

import numpy

PathLike = Union[str, bytes, pathlib.Path, os.PathLike]
Number = Union[int, float]
Value = Union[Number, bool]

NumpyNumber = Union[numpy.floating, numpy.integer]
NumpyValue = Union[NumpyNumber, numpy.bool_]

NumpySupportedNumber = Union[Number, NumpyNumber]
NumpySupportedFloat = Union[float, numpy.floating]
NumpySupportedValue = Union[Value, NumpyValue]


class DataClassType(Protocol):
    __dataclass_fields__: ClassVar[Dict[str, Any]]
