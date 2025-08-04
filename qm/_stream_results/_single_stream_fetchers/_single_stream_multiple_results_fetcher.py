from typing import TYPE_CHECKING, List, Union, Optional, cast

import numpy

from qm.api.v2.job_result_api import JobResultApi
from qm.api.models.jobs import JobResultItemSchema
from qm.api.job_result_api import JobResultServiceApi
from qm.api.models.capabilities import ServerCapabilities
from qm.exceptions import QmNoResultsError, QmInvalidSchemaError
from qm.StreamMetadata import StreamMetadata, StreamMetadataError
from qm._stream_results._multiple_streams_fetcher import MultipleStreamsFetcher
from qm._stream_results._single_stream_fetchers._base_single_stream_fetcher import BaseSingleStreamFetcher

TIMESTAMPS_LEGACY_EXT = "_timestamps"

if TYPE_CHECKING:
    from qm import StreamsManager


class SingleStreamMultipleResultFetcher(BaseSingleStreamFetcher):
    """A handle to a result of a pipeline terminating with ``save_all``"""

    def __init__(
        self,
        job_results: "StreamsManager",
        schema: JobResultItemSchema,
        service: Union[JobResultServiceApi, JobResultApi],
        stream_metadata_errors: List[StreamMetadataError],
        stream_metadata: Optional[StreamMetadata],
        capabilities: ServerCapabilities,
        multiple_streams_fetcher: Optional[MultipleStreamsFetcher],
    ) -> None:
        self.job_results = job_results
        super().__init__(
            schema=schema,
            service=service,
            stream_metadata_errors=stream_metadata_errors,
            stream_metadata=stream_metadata,
            capabilities=capabilities,
            multiple_results_fetcher=multiple_streams_fetcher,
        )

    def _validate_schema(self) -> None:
        if self._schema.is_single:
            raise QmInvalidSchemaError("expecting a multi-result schema")

    def fetch(
        self,
        item: Union[int, slice],
        *,
        check_for_errors: bool = True,
        flat_struct: bool = False,
    ) -> Optional[numpy.typing.NDArray[numpy.generic]]:
        """Fetch a result from the current result stream saved in server memory.
        The result stream is populated by the save() and save_all() statements.
        Note that if save_all() statements are used, calling this function twice
        with the same item index may give different results.

        Args:
            item: The index of the result in the saved results stream.
            check_for_errors: If true, the function would also check whether run-time errors happened during the
                program execution and would write to the logger an error message.
            flat_struct: results will have a flat structure - dimensions will be part of the shape and not of the type

        Returns:
            a single result if item is integer or multiple results if item is Python slice object.

        Example:
            ```python
            res.fetch(0)         # return the item in the top position
            res.fetch(1)         # return the item in position number 2
            res.fetch(slice(1,6))# return items from position 1 to position 6 (exclusive)
                                 # same as res.fetch_all()[1:6]
            ```
        """
        if flat_struct:
            return self.strict_fetch(item, check_for_errors=check_for_errors, flat_struct=flat_struct)
        else:
            # legacy support - reconstruct the old structure
            name = self._schema.name
            timestamps_name = name + TIMESTAMPS_LEGACY_EXT
            timestamps_result_handle = self.job_results.get(timestamps_name)
            if timestamps_result_handle is None:
                return self.strict_fetch(item, check_for_errors=check_for_errors)
            else:
                values_result = self.strict_fetch(item, check_for_errors=check_for_errors, flat_struct=True)

                fetched_length = len(values_result)
                if isinstance(item, slice):
                    start = item.start if item.start is not None else 0
                    item = slice(start, start + fetched_length, item.step)
                else:
                    item = slice(0, fetched_length)

                timestamps_result = timestamps_result_handle.fetch(
                    item, flat_struct=True, check_for_errors=check_for_errors
                )

                if timestamps_result is None:
                    raise QmNoResultsError("Failed to fetch timestamp results, please wait until results are ready")

                dtype = [
                    ("value", values_result.dtype),
                    ("timestamp", timestamps_result.dtype),
                ]
                combined = numpy.rec.fromarrays([values_result, timestamps_result], dtype=dtype)
                return cast(numpy.typing.NDArray[numpy.generic], combined.view(numpy.ndarray).astype(dtype))
