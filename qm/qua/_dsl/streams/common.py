from typing import Any, Literal

from qm.type_hinting import NumberT
from qm.exceptions import QmQuaException

StreamEndpoints = Literal["client", "opnic"]


def _validate_number_type(dtype: Any, stream_type: Literal["input", "output"]) -> None:
    # Dynamically extract valid NumberT types from TypeVar constraints
    number_types = NumberT.__constraints__
    if not (isinstance(dtype, type) and issubclass(dtype, tuple(number_types))):
        raise QmQuaException(
            f"Client {stream_type} streams require a NumberT type (one of {', '.join(t.__name__ for t in number_types)}), "
            f"got '{dtype}'"
        )
