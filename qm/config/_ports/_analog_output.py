import warnings
from abc import ABC
from typing import Literal, cast
from collections.abc import Sequence

from qm.type_hinting import Number
from qm.exceptions import ConfigValidationException
from qm.config._primitives import (
    NOT_SET,
    ConfigValue,
    ConfigObject,
    DefaultValue,
    ConfigOptional,
    _NotSet,
    create_value,
)
from qm.config._ports._port_base import (
    Band,
    Port,
    LfFem,
    MwFem,
    FemBase,
    Opx1000,
    OpxPlus,
    Direction,
    SignalType,
    PortReference,
    OpxPlusMockFem,
    PortReferenceType,
)

Amplitude = float
Tau = float


class AnalogOutputFeedbackExponential(ConfigObject):
    """Exponential feedback filter parameters for an analog output port."""

    def __init__(self, exponential: Sequence[tuple[Amplitude, Tau]] = ()):
        """
        Args:
            exponential: Exponential filter parameters as a sequence of
                ``(amplitude, time_constant)`` pairs. IIR filtering approach since
                QOP 3.3.
        """
        self.exponential = exponential

    @property
    def exponential_dc_gain(self) -> ConfigValue[float | None]:
        return DefaultValue(None)

    @property
    def high_pass(self) -> ConfigValue[float | None]:
        return DefaultValue(None)


class AnalogOutputFeedbackFilter35(AnalogOutputFeedbackExponential):
    """Exponential feedback filter with the QOP 3.5 ``exponential_dc_gain`` extension."""

    def __init__(
        self,
        exponential: Sequence[tuple[Amplitude, Tau]] = (),
        exponential_dc_gain: ConfigOptional[float | None] = NOT_SET,
    ):
        """
        Args:
            exponential: Exponential filter parameters as a sequence of
                ``(amplitude, time_constant)`` pairs. IIR filtering approach since
                QOP 3.3.
            exponential_dc_gain: DC gain of the IIR filters, supported since QOP 3.5.
        """
        super().__init__(exponential)
        self._exponential_dc_gain = create_value(exponential_dc_gain, None)

    @property
    def exponential_dc_gain(self) -> ConfigValue[float | None]:
        return self._exponential_dc_gain


class AnalogOutputFeedbackFilter33(AnalogOutputFeedbackExponential):
    """Exponential feedback filter with the QOP 3.3 ``high_pass`` extension."""

    def __init__(
        self,
        exponential: Sequence[tuple[Amplitude, Tau]] = (),
        high_pass: ConfigOptional[float | None] = NOT_SET,
    ):
        """
        Args:
            exponential: Exponential filter parameters as a sequence of
                ``(amplitude, time_constant)`` pairs. IIR filtering approach since
                QOP 3.3.
            high_pass: High-pass compensation filter, used to compensate for the
                low-frequency cutoff of the signal. IIR filtering approach since QOP 3.3.
        """
        super().__init__(exponential)
        self._high_pass = create_value(high_pass, None)

    @property
    def high_pass(self) -> ConfigValue[float | None]:
        return self._high_pass


class AnalogOutputPort(Port, ABC):
    """Base class for analog output ports of a controller."""

    def __init__(self, fem: FemBase, index: int, shareable: ConfigOptional[bool], delay: ConfigOptional[int]):
        """
        Args:
            fem: The FEM (or mock FEM, for OPX+) the port belongs to.
            index: The 1-based port index on the FEM.
            shareable: Whether the port is shareable with other QM instances.
            delay: Output's delay, in units of ns. Must be non-negative.
        """
        super().__init__(fem=fem, index=index, shareable=shareable)
        _delay = create_value(delay, 0)
        if _delay.get_value() < 0:
            raise ConfigValidationException(f"analog output delay cannot be a negative value, given value: {delay}")

        self.delay = _delay

    @property
    def signal_type(self) -> SignalType:
        return "analog"

    @property
    def direction(self) -> Direction:
        return "output"


class AnalogOutputPortLf(AnalogOutputPort, ABC):
    """Base class for analog output ports on low-frequency hardware (OPX+ and LF-FEM)."""

    def __init__(
        self,
        fem: FemBase,
        index: int,
        offset: ConfigOptional[Number],
        delay: ConfigOptional[int],
        crosstalk: ConfigOptional[dict[int, float]],
        shareable: ConfigOptional[bool],
        filter_feedforward: ConfigOptional[Sequence[float]],
    ):
        """
        Args:
            fem: The FEM (or mock FEM, for OPX+) the port belongs to.
            index: The 1-based port index on the FEM.
            offset: DC offset to the output. Applied while the quantum machine is open.
            delay: Output's delay, in units of ns. Must be non-negative.
            crosstalk: Crosstalk coefficients keyed by destination port index.
            shareable: Whether the port is shareable with other QM instances.
            filter_feedforward: Feedforward taps for the analog output filter, as a
                sequence of floats.
        """
        super().__init__(fem=fem, index=index, delay=delay, shareable=shareable)
        self.offset = create_value(offset, 0)
        if isinstance(crosstalk, dict):
            crosstalk = {int(k): v for k, v in crosstalk.items()}
        self.crosstalk = create_value(crosstalk, {})
        self.filter_feedforward = create_value(filter_feedforward, tuple())


class AnalogOutputPortOpx(AnalogOutputPortLf):
    """Analog output port of an OPX+ controller."""

    def __init__(
        self,
        controller: OpxPlus,
        index: int,
        offset: ConfigOptional[Number] = NOT_SET,
        delay: ConfigOptional[int] = NOT_SET,
        crosstalk: ConfigOptional[dict[int, float]] = NOT_SET,
        shareable: ConfigOptional[bool] = NOT_SET,
        filter_feedforward: ConfigOptional[Sequence[float]] = NOT_SET,
        filter_feedback: ConfigOptional[Sequence[float]] = NOT_SET,
        sampling_rate: float | None = None,  # sampling rate is not needed for OPX+ it is kept here for BW compatibility
    ):
        """
        Args:
            controller: The OPX+ controller this port belongs to.
            index: The 1-based port index on the controller.
            offset: DC offset to the output. Applied while the quantum machine is open.
            delay: Output's delay, in units of ns. Must be non-negative.
            crosstalk: Crosstalk coefficients keyed by destination port index.
            shareable: Whether the port is shareable with other QM instances.
            filter_feedforward: Feedforward taps for the analog output filter.
            filter_feedback: Feedback taps for the analog output filter (sequence of
                floats). IIR filtering approach prior to QOP 3.3.
        """
        super().__init__(
            fem=OpxPlusMockFem(controller),
            index=index,
            delay=delay,
            shareable=shareable,
            crosstalk=crosstalk,
            offset=offset,
            filter_feedforward=filter_feedforward,
        )
        self.filter_feedback_seq = create_value(filter_feedback, tuple())
        self.controller = controller
        if sampling_rate is not None:
            warnings.warn("You don't need to state sampling rate in OPX+")
        self.sampling_rate = sampling_rate


UpsamplingMode = Literal["mw", "pulse"]
OutputMode = Literal["direct", "amplified"]


class AnalogOutputPortOctoDac(AnalogOutputPortLf):
    """Analog output port of an LF-FEM (OPX1000)."""

    def __init__(
        self,
        fem: LfFem,
        index: int,
        offset: ConfigOptional[Number] = NOT_SET,
        delay: ConfigOptional[int] = NOT_SET,
        crosstalk: ConfigOptional[dict[int, float]] = NOT_SET,
        shareable: ConfigOptional[bool] = NOT_SET,
        filter_feedforward: ConfigOptional[Sequence[float]] = NOT_SET,
        filter_feedback: ConfigOptional[AnalogOutputFeedbackExponential] | Sequence[float] = NOT_SET,
        sampling_rate: ConfigOptional[float] = NOT_SET,
        upsampling_mode: ConfigOptional[UpsamplingMode] = NOT_SET,
        output_mode: ConfigOptional[OutputMode] = NOT_SET,
        min_voltage_limit: ConfigOptional[Number | None] = NOT_SET,
        max_voltage_limit: ConfigOptional[Number | None] = NOT_SET,
    ):
        """
        Args:
            fem: The LF-FEM the port belongs to.
            index: The 1-based port index on the FEM.
            offset: DC offset to the output. Applied while the quantum machine is open.
            delay: Output's delay, in units of ns. Must be non-negative.
            crosstalk: Crosstalk coefficients keyed by destination port index.
            shareable: Whether the port is shareable with other QM instances.
            filter_feedforward: Feedforward taps for the analog output filter.
            filter_feedback: Either an ``AnalogOutputFeedbackExponential`` describing
                the IIR filter (preferred) or a feedback-taps sequence (legacy).
            sampling_rate: Sampling rate of the port. Default 1 GS/s.
            upsampling_mode: ``"mw"`` (default) or ``"pulse"``. Only valid when
                ``sampling_rate`` is 1 GHz.
            output_mode: ``"direct"`` (default) or ``"amplified"``.
            min_voltage_limit: Minimum voltage limit for the output port.
            max_voltage_limit: Maximum voltage limit for the output port.
        """
        super().__init__(
            fem=fem,
            index=index,
            delay=delay,
            shareable=shareable,
            crosstalk=crosstalk,
            offset=offset,
            filter_feedforward=filter_feedforward,
        )
        _upsampling_mode: ConfigValue[UpsamplingMode] = create_value(upsampling_mode, "mw")
        _sampling_rate = create_value(sampling_rate, 1e9)
        if _upsampling_mode.is_set and _sampling_rate.get_value() != 1e9:
            raise ConfigValidationException("'upsampling_mode' is only relevant for 'sampling_rate' of 1GHz.")

        self.sampling_rate = _sampling_rate
        self.upsampling_mode = _upsampling_mode
        self.output_mode = cast(ConfigValue[OutputMode], create_value(output_mode, "direct"))
        self.min_voltage_limit = create_value(min_voltage_limit, None)
        self.max_voltage_limit = create_value(max_voltage_limit, None)

        if isinstance(filter_feedback, (AnalogOutputFeedbackExponential, ConfigValue, _NotSet)):
            self.filter_feedback_seq: Sequence[float] | None = None
            self.filter_feedback_inst = create_value(filter_feedback, AnalogOutputFeedbackExponential())
        else:
            warnings.warn("The feedback filter changed its API, please use the new format", DeprecationWarning)
            self.filter_feedback_seq = filter_feedback
            self.filter_feedback_inst = create_value(NOT_SET, AnalogOutputFeedbackExponential())


class AnalogOutputPortMicrowave(AnalogOutputPort):
    """Analog output port of an MW-FEM (OPX1000 microwave front-end module)."""

    def __init__(
        self,
        fem: MwFem,
        index: int,
        band: ConfigOptional[Band] = NOT_SET,
        upconverter1_frequency: ConfigOptional[float] = NOT_SET,
        upconverter2_frequency: ConfigOptional[float] = NOT_SET,
        full_scale_power_dbm: ConfigOptional[int] = NOT_SET,
        sampling_rate: ConfigOptional[float] = NOT_SET,
        shareable: ConfigOptional[bool] = NOT_SET,
        delay: ConfigOptional[int] = NOT_SET,
    ):
        """
        Args:
            fem: The MW-FEM the port belongs to.
            index: The 1-based port index on the FEM.
            band: The frequency band (1, 2, or 3).
            upconverter1_frequency: Frequency of the first upconverter, in Hz.
            upconverter2_frequency: Frequency of the second upconverter, in Hz.
            full_scale_power_dbm: The power in dBm of the full scale of the output
                (integer).
            sampling_rate: Sampling rate of the port.
            shareable: Whether the port is shareable with other QM instances.
            delay: Output's delay, integer in units of ns. Must be non-negative.
        """
        super().__init__(fem=fem, index=index, shareable=shareable, delay=delay)
        self.band: ConfigValue[Band] = create_value(band, NOT_SET)
        self.full_scale_power_dbm = create_value(full_scale_power_dbm, -11)
        self.sampling_rate = create_value(sampling_rate, 1e9)
        self.upconverter1_frequency = create_value(upconverter1_frequency, NOT_SET)
        self.upconverter2_frequency = create_value(upconverter2_frequency, NOT_SET)


ElementPortType = PortReferenceType | AnalogOutputPortLf


def standardize_lf_port(port: ElementPortType) -> AnalogOutputPortLf:
    if isinstance(port, (AnalogOutputPortLf, PortReference)):
        return port
    if len(port) == 3:
        cont, fem, idx = port
        return AnalogOutputPortOctoDac(fem=LfFem(controller=Opx1000(cont), index=fem), index=idx)
    cont, idx = port
    return AnalogOutputPortOpx(controller=OpxPlus(cont), index=idx)
