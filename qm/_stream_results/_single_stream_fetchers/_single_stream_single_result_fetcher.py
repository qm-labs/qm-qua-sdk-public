import logging
from typing import Union, Optional

import numpy

from qm.exceptions import QmInvalidSchemaError
from qm._stream_results._utils import postprocess_single_result
from qm._stream_results._single_stream_fetchers._base_single_stream_fetcher import (
    VERY_LONG_TIME,
    BaseSingleStreamFetcher,
)

logger = logging.getLogger(__name__)


class SingleStreamSingleResultFetcher(BaseSingleStreamFetcher[Optional[numpy.typing.NDArray[numpy.generic]]]):
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
    ) -> Optional[numpy.typing.NDArray[numpy.generic]]:
        """Fetch a result from the current result stream saved in server memory.
        The result stream is populated by the save() and save_all() statements.
        Note that if save_all() statements are used, calling this function twice
        may give different results.

        Args:
            check_for_errors: If true, the function would also check whether run-time errors happened during the
                program execution and would write to the logger an error message.
            flat_struct: results will have a flat structure - dimensions will be part of the shape and not of the type

        Returns:
            all result of current result stream
        """
        return self.fetch(0, flat_struct=flat_struct, check_for_errors=check_for_errors)

    def fetch(
        self,
        item: Union[int, slice],
        *,
        check_for_errors: bool = True,
        flat_struct: bool = False,
        timeout: Optional[float] = None,
    ) -> Optional[numpy.typing.NDArray[numpy.generic]]:
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
        if (isinstance(item, int) and item != 0) or isinstance(item, slice):
            logger.warning("Fetching single result will always return the single value")
        value = self.strict_fetch(0, check_for_errors=check_for_errors, flat_struct=flat_struct, timeout=timeout)
        return postprocess_single_result(value, flat_struct)
