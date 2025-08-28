import logging
from io import BytesIO
from typing import Tuple, Union, BinaryIO, Optional, cast

import numpy
import numpy.typing
from numpy.lib import format as _format

from qm.api.models.jobs import JobNamedResultHeader
from qm.exceptions import StreamProcessingDataLossError

logger = logging.getLogger(__name__)


def _create_results_array(
    count_data_written: int, header: JobNamedResultHeader, data_writer: BytesIO
) -> numpy.typing.NDArray[numpy.generic]:
    final_shape = _get_final_shape(count_data_written, header.shape)
    writer = BytesIO()
    _write_header(writer, final_shape, header.d_type)

    data_writer.seek(0)
    for d in data_writer:
        writer.write(d)

    writer.seek(0)
    return cast(numpy.typing.NDArray[numpy.generic], numpy.load(writer))


def _write_header(writer: BinaryIO, shape: Tuple[int, ...], d_type: object) -> None:
    # Numpy2 stopped support for bool8, so we need to convert it to a valid bool type
    if d_type == "bool8":
        d_type = numpy.dtype(numpy.bool_).str

    _format.write_array_header_2_0(writer, {"descr": d_type, "fortran_order": False, "shape": shape})  # type: ignore[no-untyped-call]


def _get_final_shape(count: int, shape: Tuple[int, ...]) -> Tuple[int, ...]:
    if count == 1:
        final_shape = shape
    else:
        if len(shape) == 1 and shape[0] == 1:
            final_shape = (count,)
        else:
            final_shape = (count,) + shape
    return final_shape


def _standardize_slice(name: str, item: Union[int, slice], header: JobNamedResultHeader) -> slice:
    if isinstance(item, int):
        return slice(item, item + 1)
    elif isinstance(item, slice):
        step = item.step
        if step != 1 and step is not None:
            raise Exception(f"Got step={step} for item named '{name}', Fetch supports step=1 or None in slices.")
        stop = header.count_so_far if item.stop is None else item.stop
        start = 0 if item.start is None else item.start
        return slice(start, stop, step)
    raise Exception(f"fetch supports only int or slice for item named '{name}'")


def assert_no_dataloss(header: JobNamedResultHeader, job_id: str) -> None:
    if header.has_dataloss:
        raise StreamProcessingDataLossError(f"Data loss detected in data for job: {job_id}")


def log_execution_errors(header: JobNamedResultHeader, name: str, log_error: bool) -> None:
    if log_error and header.has_execution_errors:
        logger.error(
            f"Runtime errors were detected for stream named '{name}'. "
            f"Please fetch the execution report using job.execution_report() for more information."
        )


def postprocess_single_result(
    fetched_data: numpy.typing.NDArray[numpy.generic], flat_struct: bool
) -> Optional[numpy.typing.NDArray[numpy.generic]]:
    # We assume here that we have at most a single value in array (or nothing)
    if len(fetched_data) == 0:
        logger.warning("Nothing to fetch: no results were found. Please wait until the results are ready.")
        return None
    if flat_struct:
        data = fetched_data
    else:
        data = fetched_data[0]

    if len(data) == 1:
        to_return = data[0]
    else:
        to_return = data
    return cast(numpy.typing.NDArray[numpy.generic], to_return)
