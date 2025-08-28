import abc
import logging
from io import BytesIO
from typing import Union, Generic, TypeVar, BinaryIO, Optional

import numpy.typing

from qm.utils.async_utils import run_async
from qm.api.v2.job_result_api import JobResultApi
from qm.exceptions import InvalidStreamMetadataError
from qm.api.job_result_api import JobResultServiceApi
from qm.utils.general_utils import run_until_with_timeout
from qm.StreamMetadata import StreamMetadata, StreamMetadataError
from qm.api.models.capabilities import QopCaps, ServerCapabilities
from qm._stream_results._multiple_streams_fetcher import MultipleStreamsFetcher
from qm.api.models.jobs import DtypeType, JobStreamingState, JobResultItemSchema, JobNamedResultHeader
from qm._stream_results._utils import (
    _standardize_slice,
    assert_no_dataloss,
    log_execution_errors,
    _create_results_array,
)

logger = logging.getLogger(__name__)


# 23 days. Reduced from 1e8 due to Windows gRPC timeout limits causing server errors (https://quantum-machines.atlassian.net/browse/OPXK-25752).
VERY_LONG_TIME = 2e6


ReturnedT = TypeVar("ReturnedT", Optional[numpy.typing.NDArray[numpy.generic]], numpy.typing.NDArray[numpy.generic])


class BaseSingleStreamFetcher(Generic[ReturnedT], metaclass=abc.ABCMeta):
    def __init__(
        self,
        schema: JobResultItemSchema,
        service: Union[JobResultServiceApi, JobResultApi],
        stream_metadata_errors: list[StreamMetadataError],
        stream_metadata: Optional[StreamMetadata],
        capabilities: ServerCapabilities,
        multiple_streams_fetcher: Optional[MultipleStreamsFetcher],
    ) -> None:
        self._schema = schema
        self._service = service
        self._stream_metadata_errors = stream_metadata_errors
        self._stream_metadata = stream_metadata
        self._has_job_streaming_state = capabilities.supports(QopCaps.job_streaming_state)
        self._multiple_streams_fetcher = multiple_streams_fetcher
        self._validate_schema()

    @property
    def _job_id(self) -> str:
        return self._service.id

    @abc.abstractmethod
    def _validate_schema(self) -> None:
        pass

    @property
    def name(self) -> str:
        """The name of the result this handle is connected to"""
        return self._schema.name

    @property
    def job_id(self) -> str:
        """The job id this result came from"""
        return self._job_id

    @property
    def expected_count(self) -> int:
        return self._schema.expected_count

    @property
    def numpy_dtype(self) -> DtypeType:
        return self._schema.dtype

    @property
    def stream_metadata(self) -> Optional[StreamMetadata]:
        """Provides the StreamMetadata of this stream.

        Metadata currently includes the values and shapes of the automatically identified loops
        in the program.

        """
        if len(self._stream_metadata_errors) > 0:
            logger.error("Error creating stream metadata:")
            for e in self._stream_metadata_errors:
                logger.error(f"{e.error} at: {e.location}")
            raise InvalidStreamMetadataError(self._stream_metadata_errors)
        return self._stream_metadata

    def wait_for_values(self, count: int = 1, timeout: float = VERY_LONG_TIME) -> None:
        """Wait until we know at least `count` values were processed for this named result

        Args:
            count: The number of items to wait for
            timeout: Timeout for waiting in seconds

        """
        run_until_with_timeout(
            lambda: self.count_so_far() >= count,
            timeout=timeout,
            timeout_message=f"result {self.name} was not done in time",
        )

    def wait_for_all_values(self, timeout: float = VERY_LONG_TIME) -> bool:
        """Wait until we know all values were processed for this named result

        Args:
            timeout: Timeout for waiting in seconds

        Returns:
            True if the job finished successfully and False if the job was closed before it was done.
            If the job is still running when reaching the timeout, a TimeoutError is raised.
        """

        def on_iteration() -> bool:
            header = self.get_job_state()
            return header.done or header.closed

        def on_finish() -> bool:
            header = self.get_job_state()
            return header.done

        return run_until_with_timeout(
            on_iteration_callback=on_iteration,
            on_complete_callback=on_finish,
            timeout=timeout,
            timeout_message=f"result {self.name} was not done in time",
        )

    def is_processing(self) -> bool:
        header = self.get_job_state()
        return not (header.done or header.closed)

    def count_so_far(self) -> int:
        """also `len(handle)`

        Returns:
            The number of values this result has so far
        """
        header = self._get_named_header()
        return header.count_so_far

    def __len__(self) -> int:
        return self.count_so_far()

    def has_dataloss(self) -> bool:
        """
        Returns: true if there was data loss during job execution
        """
        state = self.get_job_state()
        return state.has_dataloss

    def get_job_state(self) -> JobStreamingState:
        if self._has_job_streaming_state:
            return self._service.get_job_state()
        #  This is just for backward compatibility
        assert isinstance(self._service, JobResultServiceApi)
        return self._service.get_state_from_header(self.name, False)

    def _get_named_header(self, check_for_errors: bool = True, flat_struct: bool = False) -> JobNamedResultHeader:
        response = self._service.get_named_header(self.name, flat_struct)
        log_execution_errors(response, self.name, check_for_errors)
        return response

    def fetch_all(self, *, check_for_errors: bool = True, flat_struct: bool = False) -> ReturnedT:
        """Fetch a result from the current result stream saved in server memory.
        The result stream is populated by the save() and save_all() statements.
        Note that if save_all() statements are used, calling this function twice
        may give different results.

        Args:
            check_for_errors: If true, the function would also check whether run-time errors happened during the
                program execution and would write to the logger an error message.
            flat_struct: results will have a flat structure - dimensions will be part of the shape and not of the type

        Returns:
            all results of current result stream
        """
        return self.fetch(
            slice(0, None),
            check_for_errors=check_for_errors,
            flat_struct=flat_struct,
        )

    @abc.abstractmethod
    def fetch(
        self,
        item: Union[int, slice],
        *,
        check_for_errors: bool = True,
        flat_struct: bool = False,
        timeout: Optional[float] = None,
    ) -> ReturnedT:
        """Fetch a single result from the current result stream saved in server memory.
        The result stream is populated by the save().

        Args:
            item: ignored
            check_for_errors: If true, the function would also check whether run-time errors happened during the
                program execution and would write to the logger an error message.
            flat_struct: results will have a flat structure - dimensions will be part of the shape and not of the type
            timeout: Timeout for waiting in seconds

        Returns:
            the current result

        Example:
            ```python
            res.fetch() # return the item in the top position
            ```
        """
        pass

    def strict_fetch(
        self,
        item: Union[int, slice],
        *,
        check_for_errors: bool = True,
        flat_struct: bool = False,
        timeout: Optional[float] = None,
    ) -> numpy.typing.NDArray[numpy.generic]:
        """Fetch a result from the current result stream saved in server memory.
        The result stream is populated by the save() and save_all() statements.
        Note that if save_all() statements are used, calling this function twice
        with the same item index may give different results.

        Args:
            item: The index of the result in the saved results stream.
            check_for_errors: If true, the function would also check whether run-time errors happened during the
                program execution and would write to the logger an error message.
            flat_struct: results will have a flat structure - dimensions will be part of the shape and not of the type
            timeout: Timeout for waiting in seconds

        Returns:
            a single result if item is integer or multiple results if item is a Python slice object.

        Raises:
            Exception: If item is not an integer or a slice object.
            StreamProcessingDataLossError: If data loss is detected in the data for the job.

        Example:
            ```python
            res.fetch(0)         #return the item in the top position
            res.fetch(1)         #return the item in position number 2
            res.fetch(slice(1,6))# return items from position 1 to position 6 (exclusive)
                                 # same as res.fetch_all()[1:6]
            ```
        """
        if self._multiple_streams_fetcher is not None:
            flat_struct_items = {self.name} if flat_struct else frozenset()
            return self._multiple_streams_fetcher.strict_fetch(
                {self.name: item}, flat_struct_items, check_for_errors, timeout
            )[self.name]
        # This class tries to use the newer API of fetching multiple stream at once.
        # If the server does not have this capability, it resorts to the older API.
        header = self._get_named_header(check_for_errors=check_for_errors, flat_struct=flat_struct)
        assert_no_dataloss(header, self._job_id)
        slicer = _standardize_slice(self.name, item, header)
        array = self._fetch_results(header, slicer.start, slicer.stop, timeout)

        return array

    def _fetch_results(
        self, header: JobNamedResultHeader, start: int, stop: int, timeout: Optional[float]
    ) -> numpy.typing.NDArray[numpy.generic]:
        data_writer = BytesIO()
        count_data_written = run_async(self._add_results_to_writer(data_writer, start, stop, timeout))
        return _create_results_array(count_data_written, header, data_writer)

    async def _add_results_to_writer(
        self, data_writer: BinaryIO, start: int, stop: int, timeout: Optional[float]
    ) -> int:
        _count_data_written = 0
        async for result in self._service.get_job_named_result(self._schema.name, start, stop - start, timeout):
            data_writer.write(result.data)
            _count_data_written += result.count_of_items

        return _count_data_written


AnySingleStreamFetcher = Union[
    BaseSingleStreamFetcher[Optional[numpy.typing.NDArray[numpy.generic]]],
    BaseSingleStreamFetcher[numpy.typing.NDArray[numpy.generic]],
]
