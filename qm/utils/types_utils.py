from collections.abc import Iterable as IterableClass
from typing import (
    Any,
    Set,
    Type,
    Union,
    TypeVar,
    Iterable,
    Sequence,
    Collection,
    SupportsInt,
    SupportsFloat,
    SupportsIndex,
    cast,
)

import numpy as np
import numpy.typing

from qm.exceptions import QmValueError
from qm.type_hinting.general import Value, NumberT

GeneralConversionType = Union[str, bytes, bytearray, memoryview]
FloatConversionType = Union[SupportsFloat, SupportsIndex, GeneralConversionType]
IntConversionType = Union[SupportsInt, SupportsIndex, GeneralConversionType]
Bool = Union[bool, np.bool_]

ConversionType = TypeVar("ConversionType", IntConversionType, FloatConversionType, Bool)


def convert_object_type(obj: ConversionType) -> Value:
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    raise QmValueError(f"cannot convert {type(obj)} to int | float | bool")


def get_all_iterable_data_types(it: Iterable[Any]) -> Set[Type[Any]]:
    return {type(e) for e in it}


NumberType = TypeVar("NumberType")


def collection_has_type(
    collection: Collection[NumberType], type_to_check: Type[NumberType], include_subclasses: bool
) -> bool:
    if include_subclasses:
        return any(isinstance(i, type_to_check) for i in collection)
    else:
        return any(type(i) is type_to_check for i in collection)


def collection_has_type_bool(collection: Collection[NumberType]) -> bool:
    return collection_has_type(collection, bool, False) or collection_has_type(collection, np.bool_, True)


def collection_has_type_int(collection: Collection[NumberType]) -> bool:
    return collection_has_type(collection, int, False) or collection_has_type(collection, np.integer, True)


def collection_has_type_float(collection: Collection[NumberType]) -> bool:
    return collection_has_type(collection, float, False) or collection_has_type(collection, np.floating, True)


def get_iterable_elements_datatype(
    it: Union[numpy.typing.NDArray[NumberT], Sequence[NumberT], NumberT]  # type: ignore[type-var]
) -> Type[NumberT]:
    if isinstance(it, np.ndarray):
        item = cast("NumberT", it[0].item())
        return type(item)

    elif isinstance(it, IterableClass):
        if len(get_all_iterable_data_types(it)) > 1:
            raise ValueError("Multiple datatypes encountered in iterable object")
        item = next(iter(it))
        if isinstance(item, np.generic):
            return type(item.item())
        else:
            return type(item)
    else:
        raise ValueError(f"Did not found the type of {it}, maybe it's not an iterable")
