import logging
from io import BytesIO
from collections import defaultdict
from typing import Dict, Tuple, Union, Literal, Mapping, BinaryIO, Optional, Collection

import numpy.typing

from qm.utils.async_utils import run_async
from qm.api.v2.job_result_api import JobResultApi
from qm.api.models.jobs import JobResultItemSchema, JobNamedResultHeader
from qm._stream_results._utils import (
    _standardize_slice,
    assert_no_dataloss,
    log_execution_errors,
    _create_results_array,
    postprocess_single_result,
)

logger = logging.getLogger(__name__)


class MultipleStreamsFetcher:
    def __init__(
        self,
        schemas: Mapping[str, JobResultItemSchema],
        service: JobResultApi,
    ) -> None:
        self._schemas = schemas
        self._service = service

    @property
    def _job_id(self) -> str:
        return self._service.id

    def fetch(
        self,
        items: Mapping[str, Union[int, slice]],
        flat_struct_items: Union[Collection[str], Literal["all"]] = frozenset(),
        check_for_errors: bool = True,
        timeout: Optional[float] = None,
    ) -> Mapping[str, Optional[numpy.typing.NDArray[numpy.generic]]]:
        bare_results = self.strict_fetch(items, flat_struct_items, check_for_errors, timeout)
        results: dict[str, Optional[numpy.typing.NDArray[numpy.generic]]] = {}
        for name, result in bare_results.items():
            if self._schemas[name].is_single:
                is_flat_struct = flat_struct_items == "all" or name in flat_struct_items
                results[name] = postprocess_single_result(result, is_flat_struct)
            else:
                results[name] = result
        return results

    def strict_fetch(
        self,
        items: Mapping[str, Union[int, slice]],
        flat_struct_items: Union[Collection[str], Literal["all"]] = frozenset(),
        check_for_errors: bool = True,
        timeout: Optional[float] = None,
    ) -> Mapping[str, numpy.typing.NDArray[numpy.generic]]:

        headers = self._get_named_headers(items, flat_struct_items)
        name_to_slice, name_to_header = self._standardize_query_params(items, headers, check_for_errors)
        return self._fetch_results(name_to_slice, name_to_header, timeout=timeout)

    def _get_named_headers(
        self, items: Collection[str], flat_struct_items: Union[Collection[str], Literal["all"]]
    ) -> Mapping[str, JobNamedResultHeader]:
        if flat_struct_items == "all":
            flat_struct_items = frozenset(items)
        return self._service.get_named_headers({name: (name in flat_struct_items) for name in items})

    def _fetch_results(
        self,
        name_to_slice: Mapping[str, slice],
        name_to_header: Mapping[str, JobNamedResultHeader],
        timeout: Optional[float],
    ) -> Mapping[str, numpy.typing.NDArray[numpy.generic]]:
        name_to_writer = {n: BytesIO() for n in name_to_slice}
        name_to_count_data_written = run_async(
            self._add_results_to_writers(name_to_slice, name_to_writer, timeout=timeout)
        )
        name_to_array = {
            n: _create_results_array(
                name_to_count_data_written[n],
                name_to_header[n],
                name_to_writer[n],
            )
            for n in name_to_slice
        }
        return name_to_array

    def _get_and_validate_header(
        self, name: str, headers: Mapping[str, JobNamedResultHeader], check_for_errors: bool = True
    ) -> JobNamedResultHeader:
        if name not in headers:
            raise Exception(f"Result named '{name}' not found for job {self._job_id}")
        header = headers[name]
        log_execution_errors(header, name, check_for_errors)
        assert_no_dataloss(header, self._job_id)
        return header

    def _standardize_query_params(
        self,
        items: Mapping[str, Union[int, slice]],
        headers: Mapping[str, JobNamedResultHeader],
        check_for_errors: bool = True,
    ) -> Tuple[Mapping[str, slice], Mapping[str, JobNamedResultHeader]]:
        name_to_slice = {}
        name_to_header = {}
        for name, item in items.items():
            header = self._get_and_validate_header(name, headers, check_for_errors)
            slicer = _standardize_slice(name, item, header)
            name_to_slice[name] = slicer
            name_to_header[name] = header
        return name_to_slice, name_to_header

    async def _add_results_to_writers(
        self,
        name_to_slice: Mapping[str, slice],
        name_to_writer: Mapping[str, BinaryIO],
        timeout: Optional[float],
    ) -> Mapping[str, int]:
        name_to_count_data_written: Dict[str, int] = defaultdict(int)
        async for result in self._service.get_job_named_results(name_to_slice, timeout=timeout):
            data_writer = name_to_writer[result.output_name]
            data_writer.write(result.data)
            name_to_count_data_written[result.output_name] += result.count_of_items

        return name_to_count_data_written
