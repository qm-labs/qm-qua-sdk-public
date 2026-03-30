from typing import Any, List, Union, Mapping, TypeVar, Iterator, Sequence

import numpy as np

from qm.type_hinting.general import Number
from qm.qua._expressions import QuaVariable

V = TypeVar("V")
T = TypeVar("T", float, int)

QuaIterableArrayType = Sequence[T]
AnyQuaIterableArrayType = Union[QuaIterableArrayType[float], QuaIterableArrayType[int]]
MetaDataType = Mapping[str, Any]
QuaIterableArrayInputInt = Union[np.typing.NDArray[np.integer[Any]], QuaIterableArrayType[int]]
QuaIterableArrayInputFloat = Union[np.typing.NDArray[np.floating[Any]], QuaIterableArrayType[float]]
QuaIterableArrayInput = Union[QuaIterableArrayInputInt, QuaIterableArrayInputFloat]
NativeArrayType = Sequence[Any]

QuaIterablesDType = type[Number]
MultiIteratorsValuesType = List[Union[NativeArrayType, AnyQuaIterableArrayType]]

NativeIteratorItemType = Any  # Supporting any iterable for native type
QuaVariableTypes = Union[QuaVariable[float], QuaVariable[int]]

IteratorContentTypes = Union[
    NativeArrayType, AnyQuaIterableArrayType, NativeIteratorItemType, QuaVariableTypes, "QuaNamedTuple"
]

# iterator types
QuaIteratorType = Iterator[QuaVariable[T]]
AnyQuaIteratorType = Union[QuaIteratorType[float], QuaIteratorType[int]]
MultiIteratorType = Iterator["QuaNamedTuple"]
NativeIteratorType = Iterator[V]
IteratorType = Union[AnyQuaIteratorType, MultiIteratorType, NativeIteratorType[Any]]


class QuaNamedTuple:
    def __init__(self, names: Sequence[str], values: Sequence[Any]) -> None:
        self._fields = tuple(names)
        for key, value in zip(names, values):
            setattr(self, key, value)
        self._frozen = True

    # The -> Any return type hint tells IDEs that dynamic attribute access is valid,
    # suppressing "unresolved attribute" warnings for fields set via setattr in __init__.
    def __getattr__(self, key: str) -> Any:
        raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{key}'")

    def __setattr__(self, key: str, value: Any) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError(f"Cannot modify attribute '{key}' of {self.__class__.__name__}")
        super().__setattr__(key, value)

    def __iter__(self) -> MultiIteratorType:
        for field in self._fields:
            yield getattr(self, field)

    def __repr__(self) -> str:
        values = ", ".join(f"{f}={getattr(self, f)!r}" for f in self._fields)
        return f"{self.__class__.__name__}({values})"

    @property
    def name(self) -> str:
        return "_".join(self._fields)
