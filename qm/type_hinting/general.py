import os
import pathlib
import dataclasses
from typing import Any, Union, TypeVar, Protocol, runtime_checkable

import numpy

PathLike = Union[str, bytes, pathlib.Path, os.PathLike]  # type: ignore[type-arg]
Number = Union[int, float]
Value = Union[Number, bool]
NumberT = TypeVar("NumberT", int, bool, float)
"""A generic type variable that can be used to represent a pythonic `int`, `bool` or `float`."""

NumpyNumber = Union[numpy.floating[Any], numpy.integer[Any]]
NumpyValue = Union[NumpyNumber, numpy.bool_]

NumpySupportedNumber = Union[Number, NumpyNumber]
NumpySupportedFloat = Union[float, numpy.floating[Any]]
NumpySupportedValue = Union[Value, NumpyValue]


@runtime_checkable
@dataclasses.dataclass
class DataclassProtocol(Protocol):
    pass
