from qm.octave_sdk.octave import IFMode, ClockInfo
from qm.utils.deprecation_utils import throw_warning
from qm.octave_sdk import (
    ClockType,
    OctaveOutput,
    RFOutputMode,
    ClockFrequency,
    OctaveLOSource,
    RFInputLOSource,
    RFInputRFSource,
)

__all__ = [
    "RFInputRFSource",
    "RFOutputMode",
    "OctaveLOSource",
    "RFInputLOSource",
    "ClockType",
    "ClockFrequency",
    "OctaveOutput",
    "IFMode",
    "ClockInfo",
]

throw_warning(
    "Octave enums should be directly imported from the octave_sdk "
    "(IFMode, and ClockInfo are imported from qm.octave_sdk.octave), this file (qm.octave.enums)"
    "will be removed in the next version",
    category=DeprecationWarning,
)
