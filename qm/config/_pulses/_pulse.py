from abc import ABC
from collections.abc import Mapping, Collection

from qm.config._primitives import NamedObject
from qm.config._waveforms import DigitalWaveform
from qm.config._pulses._integration_weights import IntegrationWeights
from qm.config._waveforms._analog import SingleWaveformOptions, standardize_waveform


class Pulse(NamedObject, ABC):
    """The specification and properties of a single pulse and the measurement associated with it.

    Concrete subclasses are ``DigitalPulse``, ``SinglePulse``, and ``DualPulse``. The
    legacy schema field ``operation`` (``"control"``/``"measurement"``) is implicit:
    pulses with ``integration_weights`` are measurements.
    """

    def __init__(
        self,
        length: int,
        digital_waveform: DigitalWaveform | None = None,
        integration_weights: Mapping[str, IntegrationWeights] | Collection[IntegrationWeights] = (),
        name: str = "",
    ):
        """
        Args:
            length: The length of the pulse, in ns.
            digital_waveform: The digital waveform played alongside this pulse (legacy
                ``digital_marker``).
            integration_weights: The integration weights to use during measurement.
                Either a mapping of ``alias -> IntegrationWeights`` (alias becomes the
                key in the configuration), or a collection of ``IntegrationWeights``
                (each weight's own name is used as the key).
            name: Name used to reference this pulse from operations. Auto-generated
                if empty.
        """
        super().__init__(name)
        if isinstance(integration_weights, Mapping):
            self.integration_weights = {**integration_weights}
        else:
            self.integration_weights = {iw.name: iw for iw in integration_weights}
        self.length = length
        self.digital_waveform = digital_waveform

    def add_integration_weights(self, weights: IntegrationWeights) -> None:
        if weights.name in self.integration_weights:
            return
        self.integration_weights[weights.name] = weights


class DigitalPulse(Pulse):
    """A pulse that has only a digital waveform (no analog component)."""

    def __init__(
        self,
        length: int,
        digital_waveform: DigitalWaveform,
        name: str = "",
    ) -> None:
        """
        Args:
            length: The length of the pulse, in ns.
            digital_waveform: The digital waveform played by this pulse.
            name: Name used to reference this pulse from operations. Auto-generated
                if empty.
        """
        super().__init__(length=length, digital_waveform=digital_waveform, name=name)


class SinglePulse(Pulse):
    """A pulse for an element with a single analog input."""

    def __init__(
        self,
        waveform: SingleWaveformOptions,
        length: int,
        digital_waveform: DigitalWaveform | None = None,
        integration_weights: Mapping[str, IntegrationWeights] | Collection[IntegrationWeights] = (),
        name: str = "",
    ):
        """
        Args:
            waveform: The analog waveform played to the element's single input.
                Accepts a scalar (constant), a flat sequence (arbitrary), a
                ``WaveformArray``, or any ``AnalogWaveform`` instance.
            length: The length of the pulse, in ns.
            digital_waveform: Optional digital waveform to play alongside the pulse.
            integration_weights: Integration weights for measurement pulses (see
                ``Pulse`` for accepted formats).
            name: Name used to reference this pulse from operations. Auto-generated
                if empty.
        """
        super().__init__(
            length=length, digital_waveform=digital_waveform, integration_weights=integration_weights, name=name
        )
        self.waveform = standardize_waveform(waveform)


class DualPulse(Pulse):
    """A pulse for an element with two analog inputs (I/Q or MW)."""

    def __init__(
        self,
        waveform_i: SingleWaveformOptions,
        waveform_q: SingleWaveformOptions,
        length: int,
        digital_waveform: DigitalWaveform | None = None,
        integration_weights: Mapping[str, IntegrationWeights] | Collection[IntegrationWeights] = (),
        name: str = "",
    ):
        """
        Args:
            waveform_i: The analog waveform played to the I input. Accepted forms
                are the same as ``SinglePulse.waveform``.
            waveform_q: The analog waveform played to the Q input.
            length: The length of the pulse, in ns.
            digital_waveform: Optional digital waveform to play alongside the pulse.
            integration_weights: Integration weights for measurement pulses (see
                ``Pulse`` for accepted formats).
            name: Name used to reference this pulse from operations. Auto-generated
                if empty.
        """
        super().__init__(
            length=length, digital_waveform=digital_waveform, integration_weights=integration_weights, name=name
        )
        self.waveform_i = standardize_waveform(waveform_i)
        self.waveform_q = standardize_waveform(waveform_q)
