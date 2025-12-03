import logging
from typing import Union, Optional, cast

from qm.exceptions import QmInvalidSchemaError
from qm.type_hinting.general import NumpyArray
from qm._stream_results._single_stream_fetchers._base_single_stream_fetcher import (
    VERY_LONG_TIME,
    BaseSingleStreamFetcher,
    NumpyArrayOrSingleValue,
)

logger = logging.getLogger(__name__)


class SingleStreamSingleResultFetcher(BaseSingleStreamFetcher[Optional[NumpyArrayOrSingleValue]]):
    """A handle to a result of a pipeline terminating with ``save``"""

    def _validate_schema(self) -> None:
        if not self._schema.is_single:
            raise QmInvalidSchemaError("expecting a single-result schema")

    def wait_for_values(self, count: int = 1, timeout: float = VERY_LONG_TIME) -> None:
        if count != 1:
            raise RuntimeError("single result can wait only for a single value")
        super().wait_for_values(1, timeout)

    def fetch_all(
        self, *, check_for_errors: bool = True, flat_struct: bool = False
    ) -> Optional[NumpyArrayOrSingleValue]:
        """
        Fetches the results from the current result stream saved in server memory.
        The result stream is populated by the `save()` statement.

        Args:
            check_for_errors: If true, the function would also check whether run-time errors happened during the
                program execution and would write to the logger an error message.
            flat_struct: Results will have a flat structure - dimensions will be part of the shape and not of the type

        Returns:
            The current result from the stream. This can be a single numpy scalar or a numpy array, which depends
            on the stream operators that were used. For example, using a buffer or 'with_timestamps' will return a
            numpy array.
        """
        return self.fetch(0, flat_struct=flat_struct, check_for_errors=check_for_errors)

    def fetch(
        self,
        item: Union[int, slice],
        *,
        check_for_errors: bool = True,
        flat_struct: bool = False,
        timeout: Optional[float] = None,
    ) -> Optional[NumpyArrayOrSingleValue]:
        """
        Fetches the results from the current result stream saved in server memory.
        The result stream is populated by the `save()` statement.

        Args:
            item: The index, or a slice indicating a range, of the result in the stream.
            check_for_errors: If true, the function would also check whether run-time errors happened during the
                program execution and would write to the logger an error message.
            flat_struct: Results will have a flat structure - dimensions will be part of the shape and not of the type
            timeout: Timeout for waiting in seconds.

        Returns:
            The current result. This can be a single numpy scalar or a numpy array, which depends
            on the stream operators that were used. For example, using a buffer or 'with_timestamps' will return a
            numpy array.

        Example:
            ```python
            res.fetch() # return the item in the top position
            ```
        """
        if item not in [0, slice(None), slice(1), slice(0, 1), slice(0, 1, 1)]:
            logger.warning("Fetching single result will always return the single value")
        return super().fetch(0, check_for_errors=check_for_errors, flat_struct=flat_struct, timeout=timeout)

    @staticmethod
    def _postprocess(fetched_data: NumpyArray, flat_struct: bool) -> Optional[NumpyArrayOrSingleValue]:
        """
        Peel a single layer of the fetched data array, if possible.
        It does not mean that the returned value is a scalar - it can be still an array. In the case of an array that is
        "double layered" (happens when with_timestamps is used for example), the returned value will be the underlying array.
        Also, cases where a regular array is passed with flat_struct=True are handled here, so that the returned value is the
        same as the input value.
        """
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
        return cast(NumpyArrayOrSingleValue, to_return)
