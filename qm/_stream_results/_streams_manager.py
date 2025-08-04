import logging
import warnings
from typing_extensions import Mapping  # Mapping in 3.8 does not support class indexing
from typing import (
    Dict,
    List,
    Tuple,
    Union,
    Literal,
    TypeVar,
    Callable,
    KeysView,
    Optional,
    Generator,
    ItemsView,
    Collection,
    ValuesView,
    overload,
)

import numpy

from qm.utils import deprecation_message
from qm.api.v2.job_result_api import JobResultApi
from qm.api.job_result_api import JobResultServiceApi
from qm.exceptions import JobFailedError, QmQuaException
from qm.utils.general_utils import run_until_with_timeout
from qm.StreamMetadata import StreamMetadata, StreamMetadataError
from qm.api.models.capabilities import QopCaps, ServerCapabilities
from qm._stream_results._multiple_streams_fetcher import MultipleStreamsFetcher
from qm._stream_results._single_stream_fetchers._single_stream_single_result_fetcher import (
    SingleStreamSingleResultFetcher,
)
from qm._stream_results._single_stream_fetchers._base_single_stream_fetcher import (
    VERY_LONG_TIME,
    BaseSingleStreamFetcher,
)
from qm._stream_results._single_stream_fetchers._single_stream_multiple_results_fetcher import (
    SingleStreamMultipleResultFetcher,
)

logger = logging.getLogger(__name__)


_T = TypeVar("_T")


class StreamsManager(Mapping[str, Optional[BaseSingleStreamFetcher]]):
    """Access to the results of a QmJob

    This object is created by calling [QmJob.result_handles][qm.jobs.running_qm_job.RunningQmJob.result_handles]

    Assuming you have an instance of StreamsManager:
    ```python
        job_results: StreamsManager
    ```
    This object is iterable:

    ```python
        for name, handle in job_results:
            print(name)
    ```

    Can detect if a name exists:

    ```python
    if "somename" in job_results:
        print("somename exists!")
        handle = job_results.get("somename")
    ```
    """

    def __init__(
        self,
        service: Union[JobResultServiceApi, JobResultApi],
        capabilities: ServerCapabilities,
        wait_until_func: Optional[Callable[[Literal["Done"], float], None]],
    ) -> None:
        self._service = service
        self._capabilities = capabilities
        self._wait_until_func = wait_until_func

        self._schema_items = service.get_job_result_schema()
        self._multiple_streams_fetcher: Optional[MultipleStreamsFetcher] = self._create_multiple_streams_fetcher()
        self._single_stream_fetchers = self._create_all_single_stream_fetchers()

    def _create_multiple_streams_fetcher(self) -> Optional[MultipleStreamsFetcher]:
        if self._capabilities.supports(QopCaps.multiple_streams_fetching) and isinstance(self._service, JobResultApi):
            # This MultipleStreamsFetcher implements the fetching of many streams at once, using a new API.
            return MultipleStreamsFetcher(self._schema_items, self._service)
        return None

    def _create_all_single_stream_fetchers(self) -> Mapping[str, BaseSingleStreamFetcher]:
        _all_fetchers: Dict[str, BaseSingleStreamFetcher] = {}

        stream_metadata_errors, stream_metadata_dict = self._get_stream_metadata()

        for name, item_schema in self._schema_items.items():
            stream_metadata = stream_metadata_dict.get(name)
            if item_schema.is_single:
                _all_fetchers[name] = SingleStreamSingleResultFetcher(
                    schema=item_schema,
                    service=self._service,
                    stream_metadata_errors=stream_metadata_errors,
                    stream_metadata=stream_metadata,
                    capabilities=self._capabilities,
                    multiple_results_fetcher=self._multiple_streams_fetcher,
                )
            else:
                _all_fetchers[name] = SingleStreamMultipleResultFetcher(
                    job_results=self,
                    schema=item_schema,
                    service=self._service,
                    stream_metadata_errors=stream_metadata_errors,
                    stream_metadata=stream_metadata,
                    capabilities=self._capabilities,
                    multiple_streams_fetcher=self._multiple_streams_fetcher,
                )
        return _all_fetchers

    def __len__(self) -> int:
        return len(self._single_stream_fetchers)

    def __getitem__(self, item: str) -> Optional[BaseSingleStreamFetcher]:
        return self.get(item)

    def __getattr__(self, item: str) -> Optional[BaseSingleStreamFetcher]:
        if item == "shape" or item == "__len__":
            return (
                None  # this is here because of a bug in pycharm debugger: ver: 2022.3.2 build #PY-223.8617.48 (24/1/23)
            )
        return self.get(item)

    def _get_stream_metadata(self) -> Tuple[List[StreamMetadataError], Dict[str, StreamMetadata]]:
        return self._service.get_program_metadata()

    def __iter__(self) -> Generator[Tuple[str, Optional[BaseSingleStreamFetcher]], None, None]:  # type: ignore[override]
        warnings.warn(
            deprecation_message(
                method="streaming_result_fetcher.__iter__",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This function is going to change its API to be similar to this of a dictionary, "
                "Use `iterate_results` for the old API.",
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        return self.iterate_results()

    def iterate_results(self) -> Generator[Tuple[str, Optional[BaseSingleStreamFetcher]], None, None]:
        for item in self._schema_items.values():
            yield item.name, self.get(item.name)

    def keys(self) -> KeysView[str]:
        """
        Returns a view of the names of the results
        """
        return self._single_stream_fetchers.keys()

    def items(self) -> ItemsView[str, BaseSingleStreamFetcher]:
        """
        Returns a view, in which the first item is the name of the result and the second is the result
        """
        return self._single_stream_fetchers.items()

    def values(self) -> ValuesView[BaseSingleStreamFetcher]:
        """
        Returns a view of the results
        """
        return self._single_stream_fetchers.values()

    def is_processing(self) -> bool:
        """Check if the job is still processing results

        Returns:
            True if results are still being processed, False otherwise
        """
        key = list(self._single_stream_fetchers.keys())[0]
        return self._single_stream_fetchers[key].is_processing()

    def get(
        self, name: str, /, default: Optional[Union[BaseSingleStreamFetcher, _T]] = None
    ) -> Optional[Union[BaseSingleStreamFetcher, _T]]:
        """Get a handle to a named result from [stream_processing][qm.qua.stream_processing]

        Args:
            name: The named result using in [stream_processing][qm.qua.stream_processing]
            default: The default value to return if the named result is unknown


        Returns:
            A handle object to the results `MultipleNamedJobResult` or `SingleNamedJobResult` or None if the named results in unknown
        """
        return self._single_stream_fetchers.get(name)

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        return name in self._single_stream_fetchers

    def wait_for_all_values(self, timeout: Optional[float] = None) -> bool:
        """Wait until we know all values were processed for all named results

        Args:
            timeout: Timeout for waiting in seconds

        Returns:
            Returns True if all completed successfully; False if any result stream was closed prematurely (e.g., due to job failure or cancellation).

        """
        if self._wait_until_func is not None:
            try:
                self._wait_until_func("Done", timeout if timeout else VERY_LONG_TIME)
                return True
            except JobFailedError:
                logger.warning("Job failed or canceled, data processing has stopped, not all data is available.")
                return False
        else:

            def on_iteration() -> bool:
                all_job_states = [fetcher.get_job_state() for fetcher in self._single_stream_fetchers.values()]
                all_done = all(state.done for state in all_job_states)
                any_closed = any(state.closed for state in all_job_states)
                return all_done or any_closed

            def on_complete() -> bool:
                if all(fetcher.get_job_state().done for fetcher in self._single_stream_fetchers.values()):
                    return True
                logger.warning("Job failed or canceled, data processing has stopped, not all data is available.")
                return False

            return run_until_with_timeout(
                on_iteration_callback=on_iteration,
                on_complete_callback=on_complete,
                timeout=timeout if timeout else VERY_LONG_TIME,
                timeout_message="Job was not done in time",
            )

    @overload
    def fetch_results(
        self,
        wait_until_done: bool = True,
        timeout: float = VERY_LONG_TIME,
        stream_names: Optional[Mapping[str, Union[int, slice]]] = None,
        item: None = None,
    ) -> Mapping[str, numpy.typing.NDArray[numpy.generic]]:
        pass

    @overload
    def fetch_results(
        self,
        wait_until_done: bool = True,
        timeout: float = VERY_LONG_TIME,
        stream_names: Optional[Collection[str]] = None,
        item: Optional[Union[int, slice]] = None,
    ) -> Mapping[str, numpy.typing.NDArray[numpy.generic]]:
        pass

    def fetch_results(
        self,
        wait_until_done: bool = True,
        timeout: float = VERY_LONG_TIME,
        stream_names: Optional[Union[Mapping[str, Union[int, slice]], Collection[str]]] = None,
        item: Optional[Union[int, slice]] = None,
    ) -> Mapping[str, numpy.typing.NDArray[numpy.generic]]:
        """Fetch results from the specified streams

        Args:
            wait_until_done: If True, will wait until all results are processed before fetching
            timeout: Timeout for waiting in seconds
            stream_names: A mapping of stream names to indices or slices to fetch, or a collection of stream names to fetch all items from
            item: An index or slice to fetch from each stream

        Returns:
            A mapping of stream names to their fetched results as numpy arrays
        """
        data_to_fetch = self._standardize_fetch_args(items_to_slice=item, stream_names=stream_names)

        if wait_until_done:
            self.wait_for_all_values(timeout=timeout)

        return self._fetch_by_standard_query(data_to_fetch)

    def _fetch_by_standard_query(
        self, data_to_fetch: Mapping[str, Union[int, slice]]
    ) -> Mapping[str, numpy.typing.NDArray[numpy.generic]]:
        if self._multiple_streams_fetcher is not None:
            return self._multiple_streams_fetcher.fetch(data_to_fetch)
        else:
            results = {}
            for name, curr_item in data_to_fetch.items():
                val = self._single_stream_fetchers[name].fetch(item=curr_item)
                if val is not None:
                    results[name] = val
                else:
                    logger.warning(f"Failed to fetch results for stream '{name}'")

            return results

    def _standardize_fetch_args(
        self,
        items_to_slice: Optional[Union[int, slice]] = None,
        stream_names: Optional[Union[Mapping[str, Union[int, slice]], Collection[str]]] = None,
    ) -> Mapping[str, Union[int, slice]]:
        """Standardize the fetch arguments to a common format"""
        if isinstance(stream_names, dict) and items_to_slice is not None:
            raise QmQuaException("Cannot specify both stream_names and item")
        if stream_names is None:
            stream_names = self.keys()

        unknown_streams = set(stream_names) - set(self.keys())
        if unknown_streams:
            raise QmQuaException(f"Unknown stream names: {unknown_streams}")

        if isinstance(stream_names, dict):
            return stream_names
        else:
            items_to_slice = (
                items_to_slice if items_to_slice is not None else slice(None)
            )  # Default to fetching all items
            return {name: items_to_slice for name in stream_names}
