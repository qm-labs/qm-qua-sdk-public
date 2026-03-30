from typing import Tuple, BinaryIO

import numpy.typing
from numpy.lib import format as _format


def _write_header(writer: BinaryIO, shape: Tuple[int, ...], d_type: object) -> None:
    corrected_dtype = _fix_unsupported_dtype(d_type)
    _format.write_array_header_2_0(writer, {"descr": corrected_dtype, "fortran_order": False, "shape": shape})  # type: ignore[no-untyped-call]


_NP_BOOL = numpy.dtype(numpy.bool_).str
_UNSUPPORTED_DTYPE = "bool8"


def _fix_unsupported_dtype(d_type: object) -> object:
    # Numpy2 stopped support for bool8, so we need to convert it to a valid bool type
    if d_type == _UNSUPPORTED_DTYPE:
        return _NP_BOOL
    if isinstance(d_type, list):
        return [_fix_unsupported_dtype(elem) for elem in d_type]
    return d_type
