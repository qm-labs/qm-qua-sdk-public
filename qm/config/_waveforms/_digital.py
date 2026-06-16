from typing import Literal

from qm.config._primitives import NamedObject
from qm.exceptions import ConfigValidationException

Sample = Literal[0, 1, False, True]


class DigitalWaveform(NamedObject):
    """The samples of a digital waveform."""

    def __init__(self, samples: list[tuple[Sample, int]], name: str = ""):
        """
        Args:
            samples: The digital waveform as a list of ``(state, duration_ns)``
                tuples. ``state`` is ``0`` or ``1`` (off/on); ``duration`` is in ns.
                A duration of ``0`` means "play until the rest of the analog pulse".
            name: Name used to reference this waveform from a pulse's
                ``digital_marker``. Auto-generated if empty.
        """
        super().__init__(name)
        if not set(state for state, _ in samples) <= {0, 1}:
            raise ConfigValidationException("Invalid state in sample, State must be 0 or 1.")
        self.samples = samples
