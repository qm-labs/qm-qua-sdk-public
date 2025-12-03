from typing import Union, Optional, cast

from qm.exceptions import QmInvalidSchemaError
from qm.type_hinting.general import NumpyArray
from qm._stream_results._single_stream_fetchers._base_single_stream_fetcher import BaseSingleStreamFetcher


class SingleStreamMultipleResultFetcher(BaseSingleStreamFetcher[NumpyArray]):
    """
    A handle to a result of a pipeline terminating with ``save_all``, or to a legacy ``save`` (save using a tag,
    instead of a stream)
    """

    def _validate_schema(self) -> None:
        if self._schema.is_single:
            raise QmInvalidSchemaError("expecting a multi-result schema")

    def fetch(
        self,
        item: Union[int, slice],
        *,
        check_for_errors: bool = True,
        flat_struct: bool = False,
        timeout: Optional[float] = None,
    ) -> NumpyArray:
        """
        Fetches specific results from the current result stream saved in server memory.
        The result stream is populated by the `save()` or `save_all()` statement (or by a legacy `save` statement).

        Args:
            item: The index, or a slice indicating a range, of the result in the stream.
            check_for_errors: If true, the function would also check whether run-time errors happened during the
                program execution and would write to the logger an error message.
            flat_struct: Results will have a flat structure - dimensions will be part of the shape and not of the type
            timeout: Timeout for waiting in seconds.

        Returns:
            The requested result from this stream. This can be a single numpy scalar or a numpy array, which depends
            on the stream operators that were used. For example, using a buffer or 'with_timestamps' will return a
            numpy array.

        Example:
            ```python
            res.fetch(0)         # return the item in the top position
            res.fetch(1)         # return the item in position number 2
            res.fetch(slice(1,6))# return items from position 1 to position 6 (exclusive)
                                 # same as res.fetch_all()[1:6]
            ```
        """
        return super().fetch(
            item, check_for_errors=check_for_errors, flat_struct=flat_struct, timeout=timeout
        )  # here just to keep the upper docstring.

    @staticmethod
    def _postprocess(fetched_data: NumpyArray, flat_struct: bool) -> NumpyArray:
        # When doing with_timestamps().save_all() the resulting data structure is a bit messed up, this fixes it.
        if (
            fetched_data.dtype.fields
            and fetched_data.dtype.fields.keys() == {"value"}
            and fetched_data["value"].dtype.fields  # type: ignore[call-overload]
            and fetched_data["value"].dtype.fields.keys() == {"value", "timestamp"}  # type: ignore[call-overload]
        ):
            data_to_return = cast(NumpyArray, fetched_data["value"])  # type: ignore[call-overload]
            if data_to_return.shape[0] == 1:  # In the case of a single row, return a 1D array
                return cast(NumpyArray, data_to_return[0])
            return data_to_return
        else:
            return fetched_data
