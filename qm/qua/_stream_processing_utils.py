from math import ceil
from typing import List, Iterable

from betterproto.lib.google.protobuf import Value, ListValue

from qm.type_hinting import Number

_ARRAY_SYMBOL = "@array"


def create_array(iterable: Iterable[Number]) -> Value:
    values = (_ARRAY_SYMBOL,) + tuple(str(item) for item in iterable)
    return Value(list_value=ListValue(values=[Value(string_value=s) for s in values]))


def bins(start: Number, end: Number, number_of_bins: float) -> List[List[Number]]:
    bin_size = ceil((end - start + 1) / float(number_of_bins))
    bins_list: List[List[Number]] = []
    while start < end:
        step_end = start + bin_size - 1
        if step_end >= end:
            step_end = end
        bins_list = bins_list + [[start, step_end]]
        start += bin_size
    return bins_list
