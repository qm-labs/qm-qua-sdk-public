import numbers
from typing import cast

from qm.config._primitives import NamedObject
from qm.exceptions import ConfigValidationException
from qm.utils.list_compression_utils import split_list_to_chunks


class IntegrationWeights(NamedObject):
    """The specification of measurement integration weights."""

    def __init__(
        self,
        cosine: list[tuple[float, int]] | list[float],
        sine: list[tuple[float, int]] | list[float],
        name: str = "",
    ):
        """
        Args:
            cosine: Integration weights for the cosine. Either a list of
                ``(weight, duration_ns)`` tuples, or a flat list of floats (one
                sample per ns) which is auto-compressed. Weight range is
                ``[-2048, 2048]`` in steps of ``2**-15``; durations must be
                multiples of 4.
            sine: Integration weights for the sine. Same format as ``cosine``.
            name: Name used to reference this set of weights from a measurement
                pulse. Auto-generated if empty.
        """
        super().__init__(name)
        self.cosine = self._standardize_iw_data(cosine)
        self.sine = self._standardize_iw_data(sine)

    @staticmethod
    def _standardize_iw_data(data: list[tuple[float, int]] | list[float]) -> list[tuple[float, int]]:
        if len(data) == 0 or isinstance(data[0], (tuple, list)):
            to_return = []
            for x in data:
                x = cast(tuple[float, int], x)
                to_return.append((x[0], x[1]))
            return to_return

        if isinstance(data[0], numbers.Number):
            if len(data) == 2:
                d0, d1 = cast(tuple[float, int], data)
                return [(float(d0), int(d1))]

            data = cast(list[float], data)
            chunks = split_list_to_chunks([round(2**-15 * round(s * 2**15), 20) for s in data])
            new_data: list[tuple[float, int]] = []
            for chunk in chunks:
                if chunk.accepts_different:
                    new_data.extend([(float(u), 4) for u in chunk.data])
                else:
                    new_data.append((chunk.first, 4 * len(chunk)))
            return new_data

        raise ConfigValidationException(f"Invalid IW data, data must be a list of numbers or 2-tuples, got {data}.")
