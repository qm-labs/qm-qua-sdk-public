import copy
import warnings
from typing import Generic, Literal, TypeVar
from collections.abc import Mapping, Collection

from qm.utils import deprecation_message
from qm.config._pulses._pulse import Pulse
from qm.config._octave import OctaveRfInput
from qm.config._ports._port_base import Port
from qm.config._ports import AnalogOutputPort
from qm.exceptions import ConfigValidationException
from qm.config._ports._analog_input import AnalogInputPort
from qm.config._ports._digital_input import DigitalInputPort
from qm.config._ports._digital_output import DigitalOutputPort
from qm.config._primitives import Frequency, NamedObject, ConfigObject
from qm.config._elements._analog_inputs import Mixer, MixInput, ElementInput
from qm.config._elements._digital import ElementDigitalInput, ElementDigitalOutput
from qm.config._elements._analog_outputs import OutputOptions, ElementOutputLf, ElementOutputMw, standardize_output

ElementInputT = TypeVar("ElementInputT", bound=ElementInput)


Polarity = Literal["ABOVE", "BELOW"]


class StickyParams(ConfigObject):
    """When defined, makes the element sticky."""

    def __init__(self, analog: bool = True, digital: bool = False, duration_ns: int = 4) -> None:
        """
        Args:
            analog: Whether the analog part of the pulse is sticky.
            digital: Whether the digital part of the pulse is sticky.
            duration_ns: The analog's ramp-to-zero duration, in ns. Must be a
                multiple of 4.
        """
        self.analog = analog
        self.digital = digital
        if duration_ns is not None and (duration_ns % 4) != 0:
            raise Exception("Sticky's element duration must be a multiple of 4")

        self.duration = duration_ns

    @property
    def duration_cycles(self) -> int:
        return self.duration // 4


class HoldOffset(StickyParams):
    """When defined, makes the element sticky (legacy ``hold_offset`` API)."""

    def __init__(self, duration_cycles: int) -> None:
        """
        Args:
            duration_cycles: The ramp-to-zero duration, in clock cycles (4 ns each).
        """
        super().__init__(duration_ns=duration_cycles * 4)


def _standardize_polarity(polarity: str) -> Polarity:
    # Direct equality comparisons (instead of `in (...)`) so mypy can narrow the str
    # to the Literal members declared on `Polarity`.
    polarity = polarity.upper()
    if polarity == "ABOVE":
        return "ABOVE"
    if polarity == "BELOW":
        return "BELOW"
    if polarity == "ASCENDING":
        warnings.warn(deprecation_message("ASCENDING", "1.2.2", "2.0.0", "Use 'ABOVE' instead"), DeprecationWarning)
        return "ABOVE"
    if polarity == "DESCENDING":
        warnings.warn(deprecation_message("DESCENDING", "1.2.2", "2.0.0", "Use 'BELOW' instead"), DeprecationWarning)
        return "BELOW"
    raise ConfigValidationException(f"Invalid signal polarity: {polarity}")


class TimeTaggingParams(ConfigObject):
    """Pulse parameters for Time-Tagging."""

    def __init__(
        self, threshold: int, signal_polarity: Polarity, derivative_threshold: int, derivative_polarity: Polarity
    ) -> None:
        """
        Args:
            threshold: The signal threshold (raw ADC units).
            signal_polarity: The polarity of the signal threshold (``"ABOVE"``
                or ``"BELOW"``).
            derivative_threshold: The derivative threshold.
            derivative_polarity: The polarity of the derivative threshold (``"ABOVE"``
                or ``"BELOW"``).
        """
        self.signal_threshold = threshold
        self.signal_polarity = _standardize_polarity(signal_polarity)
        self.derivative_threshold = derivative_threshold
        self.derivative_polarity = _standardize_polarity(derivative_polarity)


class Oscillator(NamedObject):
    """An oscillator used to drive elements. Can be shared between elements."""

    def __init__(
        self, intermediate_frequency: float, lo_frequency: float = 0, mixer: Mixer | None = None, name: str = ""
    ) -> None:
        """
        Args:
            intermediate_frequency: The frequency of this oscillator [Hz].
            lo_frequency: The frequency of the local oscillator which drives the
                mixer [Hz]. Default 0.
            mixer: The mixer used to drive the input of the oscillator. ``None`` if
                no mixer correction is needed.
            name: Name used to reference this oscillator from elements. Auto-generated
                if empty.
        """
        super().__init__(name)
        self.intermediate_frequency = Frequency(intermediate_frequency)
        self.lo_frequency = Frequency(lo_frequency)
        self.mixer = mixer


class Element(Generic[ElementInputT], NamedObject):
    """The specifications, parameters and connections of a single element.

    An element represents and describes a controlled entity which is connected to the
    ports of the controller.
    """

    def __init__(
        self,
        input_: ElementInputT,
        intermediate_freq_or_oscillator: float | Oscillator | None,
        time_of_flight: int | None = None,
        smearing: int | None = None,
        outputs: Collection[OutputOptions | OctaveRfInput] = (),
        digital_inputs: Collection[ElementDigitalInput] = (),
        digital_outputs: Collection[ElementDigitalOutput] = (),
        time_tagging_parameters: TimeTaggingParams | None = None,
        sticky: StickyParams | None = None,
        core: str = "",
        name: str = "",
    ) -> None:
        """
        Args:
            input_: The input of the element. An instance of ``ElementInput`` such as
                ``SingleInput``, ``MixInput``, ``MicrowaveInput``, ``UpconvertedRfInput``,
                ``SingleInputCollection``, ``MultipleInputs``, or ``NoInput``.
            intermediate_freq_or_oscillator: Either the frequency [Hz] at which the
                controller modulates the output to this element, an ``Oscillator``
                instance to share modulation across elements, or ``None`` to leave
                modulation unset.
            time_of_flight: The delay, in ns, from the start of a measurement pulse
                until it reaches back into the controller. Must be calibrated by
                looking at the raw ADC data.
            smearing: Padding time, in ns, to add to both the start and end of the
                raw ADC data window during a measure command. Defaults to 0 if any
                output is declared.
            outputs: The output ports of the element. Each entry can be a controller
                analog input port, a port reference tuple, or an ``OctaveRfInput``.
            digital_inputs: Digital inputs to the element.
            digital_outputs: Digital outputs from the element.
            time_tagging_parameters: Pulse parameters for Time-Tagging.
            sticky: When defined, makes the element sticky. Pass either a
                ``StickyParams`` (preferred) or a legacy ``HoldOffset``.
            core: Element core (replaces the deprecated ``thread`` field).
            name: Element name. Auto-generated if empty.
        """
        super().__init__(name)
        self.input: ElementInputT = input_
        if isinstance(intermediate_freq_or_oscillator, Oscillator):
            self.intermediate_frequency: Frequency | None = None
            self.oscillator: Oscillator | None = intermediate_freq_or_oscillator
        elif intermediate_freq_or_oscillator is None:
            # Neither `intermediate_frequency` nor `oscillator` supplied in the source config.
            # Preserve this "not set" distinction so the pb emits the `noOscillator` oneof arm.
            self.intermediate_frequency = None
            self.oscillator = None
        else:
            self.oscillator = None
            self.intermediate_frequency = Frequency(intermediate_freq_or_oscillator)

        if isinstance(input_, MixInput) and self.intermediate_frequency is not None:
            # Seed the mixer with an identity correction for (lo, if) if the user
            # didn't already declare one. Uses setdefault (non-overwriting).
            input_.add_identity_correction_to_mixer(self.intermediate_frequency.as_float)

        self.microwave_output: ElementOutputMw | None = None
        self.outputs: list[ElementOutputLf] = []
        self.outputs_connected_to_octave: list[OctaveRfInput] = []
        for output in outputs:
            self.add_output(output)

        self.digital_inputs = digital_inputs
        self.digital_outputs = digital_outputs
        self._pulses: dict[str, Pulse] = {}

        self.time_of_flight = int(time_of_flight) if time_of_flight is not None else None
        # Match the dict-to-pb path: any kind of output (analog, MW, digital) implies a default
        # smearing of 0. Without this, elements like `digitalout_element` (which only declare
        # `digitalOutputs`) would lose `smearing { }` when round-tripped through the model.
        if smearing is None and (self.has_outputs or bool(self.digital_outputs)):
            smearing = 0
        self.smearing = int(smearing) if smearing is not None else None

        self.time_tagging_parameters = time_tagging_parameters
        self.sticky = sticky
        self.core = core

    @property
    def has_outputs(self) -> bool:
        return bool(self.outputs) or bool(self.microwave_output)

    def add_output(self, output: OutputOptions | OctaveRfInput) -> None:
        if isinstance(output, OctaveRfInput):
            self.outputs_connected_to_octave.append(output)
            for i, port in output.outputs.items():
                curr_standardized = ElementOutputLf(port, name=f"out{i}")
                if curr_standardized not in self.outputs:
                    self.outputs.append(curr_standardized)
            return

        standardized = standardize_output(output)
        if isinstance(standardized, ElementOutputLf):
            if standardized not in self.outputs:
                self.outputs.append(standardized)
                return
        elif isinstance(standardized, ElementOutputMw):
            if self.microwave_output is not None:
                if standardized.port != self.microwave_output.port:
                    raise ValueError("Microwave output already set")
                return
            self.microwave_output = standardized

    def add_pulse(self, pulse: Pulse, name: str = "") -> None:
        # todo - check pulse compatibility with the input
        pulse_copy = copy.deepcopy(pulse)
        name = name or pulse.name
        self._pulses[name] = pulse_copy

    def get_pulse(self, name: str) -> Pulse:
        return self._pulses[name]

    @property
    def pulses(self) -> Mapping[str, Pulse]:
        return self._pulses

    @property
    def analog_input_ports(self) -> Collection[AnalogOutputPort]:
        return self.input.ports

    @property
    def analog_output_ports(self) -> Collection[AnalogInputPort]:
        to_return: tuple[AnalogInputPort, ...] = tuple(x.port for x in self.outputs)
        if self.microwave_output is not None:
            to_return += (self.microwave_output.port,)
        return to_return

    @property
    def digital_input_ports(self) -> Collection[DigitalOutputPort]:
        return tuple(x.port for x in self.digital_inputs)

    @property
    def digital_output_ports(self) -> Collection[DigitalInputPort]:
        return tuple(x.port for x in self.digital_outputs)

    @property
    def all_ports(self) -> Collection[Port]:
        return (
            tuple(self.analog_input_ports)
            + tuple(self.analog_output_ports)
            + tuple(self.digital_input_ports)
            + tuple(self.digital_output_ports)
        )
