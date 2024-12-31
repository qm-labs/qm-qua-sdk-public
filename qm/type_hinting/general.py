import os
import pathlib
from typing import Union, TypeVar

import numpy

PathLike = Union[str, bytes, pathlib.Path, os.PathLike]  # type: ignore[type-arg]
Number = Union[int, float]
Value = Union[Number, bool]
NumberT = TypeVar("NumberT", int, bool, float)

NumpyNumber = Union[numpy.floating, numpy.integer]  # type: ignore[type-arg]
NumpyValue = Union[NumpyNumber, numpy.bool_]

NumpySupportedNumber = Union[Number, NumpyNumber]
NumpySupportedFloat = Union[float, numpy.floating]  # type: ignore[type-arg]
NumpySupportedValue = Union[Value, NumpyValue]
