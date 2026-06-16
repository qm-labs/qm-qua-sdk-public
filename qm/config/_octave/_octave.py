from typing import Literal
from collections.abc import Mapping, Collection

from qm.config._primitives import ConfigObject
from qm.exceptions import InvalidOctaveParameter, ConfigValidationException
from qm.config._ports import (
    ElementPortType,
    AnalogInputPortLf,
    PortReferenceType,
    AnalogOutputPortLf,
    standardize_lf_port,
    standardize_lf_input_port,
)

IfMode = Literal["direct", "mixer", "envelope", "off"]
Attenuators = Literal["ON", "OFF"]
RfSource = Literal["RF_in", "loopback_1", "loopback_2", "loopback_3", "loopback_4", "loopback_5"]
LoSourceInput = Literal["internal", "external", "analyzer"]
LoSourceRfOutput = Literal["internal", "external"]

LoSourceGenerator = tuple[str, Literal["Synth1", "Synth2", "Synth3", "Synth4", "Synth5"]]
LoSourceInputLiteral = Literal["Dmd1LO", "Dmd2LO", "LO1", "LO2", "LO3", "LO4", "LO5"]
RfOutputIndex = Literal[1, 2, 3, 4, 5]
RfInputIndex = Literal[1, 2]
IfOutputIndex = Literal[1, 2]


ALLOWED_GAINS = {x / 2 for x in range(-40, 41)}


class Loopback:
    """A loopback connecting an LO source generator on one octave to an LO input on another.

    The legacy schema represents loopbacks as
    ``((source_octave_name, source_port), target_port)``.
    """

    def __init__(
        self,
        lo_source_input: LoSourceInputLiteral,
        lo_source_generator: LoSourceGenerator,
    ) -> None:
        """
        Args:
            lo_source_input: The target LO input
                (e.g. ``"LO1"``, ``"Dmd1LO"``).
            lo_source_generator: The source as a ``(octave_name, synth_name)``
                tuple, where synth is one of ``"Synth1"`` ... ``"Synth5"``.
        """
        self.lo_source_input = lo_source_input
        self.lo_source_generator = lo_source_generator


class OctaveConnectivity(ConfigObject):
    """An octave device's connectivity to the controller.

    Captures what the legacy ``octaves`` entry encodes: the per-octave RF I/Q wiring
    to controller analog outputs, the IF outputs to controller analog inputs, and any
    loopbacks. The legacy ``connectivity`` shorthand is expanded by the caller into
    explicit ``inputs`` / ``outputs`` mappings.
    """

    def __init__(
        self,
        device_name: str,
        inputs: Mapping[RfOutputIndex, tuple[ElementPortType, ElementPortType]],
        outputs: Mapping[IfOutputIndex, PortReferenceType | AnalogInputPortLf],
        loopbacks: Collection[Loopback] = (),
    ) -> None:
        """
        Args:
            device_name: The octave's name (the key under the legacy ``octaves``
                mapping).
            inputs: For each RF-output index, the ``(I, Q)`` controller analog output
                ports wired into that upconverter (legacy
                ``RF_outputs[i].I_connection`` / ``Q_connection``).
            outputs: For each IF-output index, the controller analog input port that
                receives the downconverted signal (legacy
                ``IF_outputs.IF_outN.port``).
            loopbacks: Loopbacks connected to this octave.
        """
        self.device_name = device_name
        self.loopbacks = loopbacks
        self.inputs = {int(k): (standardize_lf_port(v[0]), standardize_lf_port(v[1])) for k, v in inputs.items()}
        self.outputs = {int(k): standardize_lf_input_port(v) for k, v in outputs.items()}


class OctaveRfPort(ConfigObject):
    """Base class for an Octave RF port (output or input)."""

    def __init__(
        self,
        device: OctaveConnectivity,
        index: int,
    ) -> None:
        """
        Args:
            device: The octave this port belongs to.
            index: The 1-based RF port index on the device.
        """
        self.device = device
        self.index = int(index)


class OctaveRfOutput(OctaveRfPort):
    """An Octave RF output (one of the ``RF_outputs`` entries in the legacy schema)."""

    def __init__(
        self,
        device: OctaveConnectivity,
        index: RfOutputIndex,
        lo_frequency: float,
        lo_source: LoSourceRfOutput,
        output_mode: str,
        gain: int | float,
        input_attenuators: Attenuators,
    ) -> None:
        """
        Args:
            device: The octave this output belongs to.
            index: The 1-based RF output index on the device.
            lo_frequency: The frequency of the LO, in Hz. Must be in ``[2e9, 18e9]``.
            lo_source: The source of the LO, ``"internal"`` or ``"external"``.
            output_mode: The output mode of the RF output, one of ``"always_on"``,
                ``"always_off"``, ``"triggered"``, or ``"triggered_reversed"``.
            gain: The gain of the RF output in dB. Half-integer in ``[-20, 20]``.
            input_attenuators: The attenuators of the I and Q inputs (``"ON"`` or
                ``"OFF"``).
        """
        super().__init__(device, index)
        gain = float(gain)
        if gain not in ALLOWED_GAINS:
            raise ConfigValidationException(
                f"Gain should be an integer or half-integer between -20 and 20, got {gain})"
            )
        if not 2e9 <= lo_frequency <= 18e9:
            raise ConfigValidationException(f"LO frequency {lo_frequency} is out of range")
        self.lo_frequency = lo_frequency
        self.lo_source = lo_source
        self.output_mode = output_mode
        self.gain = gain
        self.input_attenuators = input_attenuators

    @property
    def attenuators_are_on(self) -> bool:
        return self.input_attenuators == "ON"

    @property
    def input_ports(self) -> tuple[AnalogOutputPortLf, AnalogOutputPortLf]:
        return self.device.inputs[self.index]

    @property
    def i_connection(self) -> AnalogOutputPortLf:
        return self.input_ports[0]

    @property
    def q_connection(self) -> AnalogOutputPortLf:
        return self.input_ports[1]


class OctaveRfInput(OctaveRfPort):
    """An Octave RF input (one of the ``RF_inputs`` entries in the legacy schema)."""

    def __init__(
        self,
        device: OctaveConnectivity,
        index: RfInputIndex,
        rf_source: RfSource,
        lo_frequency: float,
        lo_source: LoSourceInput | None,
        if_mode_i: IfMode,
        if_mode_q: IfMode,
    ) -> None:
        """
        Args:
            device: The octave this input belongs to.
            index: The 1-based RF input index on the device.
            rf_source: The RF source feeding this downconverter
                (``"RF_in"`` or ``"loopback_1"`` ... ``"loopback_5"``).
            lo_frequency: The frequency of the LO, in Hz.
            lo_source: The source of the LO (``"internal"``, ``"external"``,
                or ``"analyzer"``).
            if_mode_i: The IF mode for I (``"direct"``, ``"mixer"``, ``"envelope"``
                or ``"off"``).
            if_mode_q: The IF mode for Q (``"direct"``, ``"mixer"``, ``"envelope"``
                or ``"off"``).
        """
        super().__init__(device, index)

        input_idx_to_default_lo_source: Mapping[RfInputIndex, LoSourceInput] = {1: "internal", 2: "external"}
        if index == 1 and rf_source.lower() != "rf_in":
            raise InvalidOctaveParameter("Downconverter 1 must be connected to RF-in")

        if lo_source is None:
            lo_source_standardized = input_idx_to_default_lo_source[index]
        else:
            lo_source_standardized = lo_source
        if index == 2 and lo_source_standardized == "internal":
            raise InvalidOctaveParameter("Downconverter 2 does not have internal LO")

        self.rf_source = rf_source
        self.lo_frequency = lo_frequency
        self.lo_source = lo_source_standardized
        self.if_mode_i = if_mode_i
        self.if_mode_q = if_mode_q

    @property
    def outputs(self) -> Mapping[int, AnalogInputPortLf]:
        return self.device.outputs
