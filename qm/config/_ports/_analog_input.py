import warnings
from abc import ABC
from typing import Literal

from qm.type_hinting import Number
from qm.config._primitives import NOT_SET, ConfigValue, ConfigOptional, create_value
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
    StandardPort,
    PortReference,
    OpxPlusMockFem,
)


class AnalogInputPort(Port, ABC):
    """Base class for analog input ports of a controller."""

    @property
    def signal_type(self) -> SignalType:
        return "analog"

    @property
    def direction(self) -> Direction:
        return "input"


class AnalogInputPortLf(AnalogInputPort, ABC):
    """Base class for analog input ports on low-frequency hardware (OPX+ and LF-FEM)."""

    def __init__(
        self,
        fem: FemBase,
        index: int,
        offset: ConfigOptional[Number],
        gain_db: ConfigOptional[int],
        shareable: ConfigOptional[bool],
        sampling_rate: ConfigOptional[float],
    ):
        """
        Args:
            fem: The FEM (or mock FEM, for OPX+) the port belongs to.
            index: The 1-based port index on the FEM.
            offset: DC offset to the input.
            gain_db: Gain of the pre-ADC amplifier, in dB. Accepts integers.
            shareable: Whether the port is shareable with other QM instances.
            sampling_rate: Sampling rate for this port.
        """
        super().__init__(fem=fem, index=index, shareable=create_value(shareable, False))
        self.offset = create_value(offset, 0)
        self.gain_db = create_value(gain_db, 0)
        self.sampling_rate = create_value(sampling_rate, 1e9)


class AnalogInputPortOpx(AnalogInputPortLf):
    """Analog input port of an OPX+ controller. Sampling rate is fixed at 1 GS/s."""

    def __init__(
        self,
        controller: OpxPlus,
        index: int,
        offset: ConfigOptional[Number] = NOT_SET,
        gain_db: ConfigOptional[int] = NOT_SET,
        shareable: ConfigOptional[bool] = NOT_SET,
        sampling_rate: float | None = None,  # not needed for OPX+; accepted for BW compatibility
    ):
        """
        Args:
            controller: The OPX+ controller this port belongs to.
            index: The 1-based port index on the controller.
            offset: DC offset to the input.
            gain_db: Gain of the pre-ADC amplifier, in dB. Accepts integers.
            shareable: Whether the port is shareable with other QM instances.
        """
        super().__init__(
            fem=OpxPlusMockFem(controller),
            index=index,
            offset=create_value(offset, 0),
            shareable=create_value(shareable, False),
            gain_db=create_value(gain_db, 0),
            sampling_rate=1e9,
        )
        if sampling_rate is not None:
            warnings.warn("You don't need to state sampling rate in OPX+")


class AnalogInputPortOctoDac(AnalogInputPortLf):
    """Analog input port of an LF-FEM (OPX1000)."""

    def __init__(
        self,
        fem: LfFem,
        index: int,
        offset: ConfigOptional[Number] = NOT_SET,
        gain_db: ConfigOptional[int] = NOT_SET,
        shareable: ConfigOptional[bool] = NOT_SET,
        sampling_rate: ConfigOptional[float] = NOT_SET,
    ):
        """
        Args:
            fem: The LF-FEM the port belongs to.
            index: The 1-based port index on the FEM.
            offset: DC offset to the input.
            gain_db: Gain of the pre-ADC amplifier, in dB. Accepts integers.
            shareable: Whether the port is shareable with other QM instances.
            sampling_rate: Sampling rate for this port. Default 1 GS/s.
        """
        super().__init__(
            fem=fem,
            index=index,
            offset=create_value(offset, 0),
            shareable=create_value(shareable, False),
            gain_db=create_value(gain_db, 0),
            sampling_rate=create_value(sampling_rate, 1e9),
        )


def standardize_lf_input_port(data: tuple[str, int] | StandardPort | AnalogInputPortLf) -> AnalogInputPortLf:
    if isinstance(data, (AnalogInputPortLf, PortReference)):
        return data
    if isinstance(data, (tuple, list)):
        if len(data) == 2:
            return AnalogInputPortOpx(controller=OpxPlus(data[0]), index=data[1])
        elif len(data) == 3:
            return AnalogInputPortOctoDac(fem=LfFem(controller=Opx1000(data[0]), index=data[1]), index=data[2])
        else:
            raise NotImplementedError
    raise NotImplementedError


LoMode = Literal["auto", "always_on"]


class AnalogInputPortMicrowave(AnalogInputPort):
    """Analog input port of an MW-FEM (OPX1000 microwave front-end module)."""

    def __init__(
        self,
        fem: MwFem,
        index: int,
        band: ConfigOptional[Band] = NOT_SET,
        downconverter_frequency: ConfigOptional[float] = NOT_SET,
        gain_db: ConfigOptional[int] = NOT_SET,
        sampling_rate: ConfigOptional[float] = NOT_SET,
        shareable: ConfigOptional[bool] = NOT_SET,
        lo_mode: ConfigOptional[LoMode] = NOT_SET,
    ):
        """
        Args:
            fem: The MW-FEM the port belongs to.
            index: The 1-based port index on the FEM.
            band: The frequency band (1, 2, or 3).
            downconverter_frequency: The frequency of the downconverter attached to
                this port.
            gain_db: Gain of the pre-ADC amplifier, in dB. Accepts integers.
            sampling_rate: Sampling rate of the port.
            shareable: Whether the port is shareable with other QM instances.
            lo_mode: ``"auto"`` (default) or ``"always_on"``.
        """
        super().__init__(fem=fem, index=index, shareable=create_value(shareable, False))
        self.band: ConfigValue[Band] = create_value(band, NOT_SET)
        self.gain_db = create_value(gain_db, 0)
        self.sampling_rate = create_value(sampling_rate, 1e9)
        self.downconverter_frequency = create_value(downconverter_frequency, NOT_SET)
        self.lo_mode: ConfigValue[LoMode] = create_value(lo_mode, "auto")


def standardize_mw_input_port(data: StandardPort | AnalogInputPortMicrowave) -> AnalogInputPortMicrowave:
    if isinstance(data, (AnalogInputPortMicrowave, PortReference)):
        return data
    return AnalogInputPortMicrowave(fem=MwFem(Opx1000(data[0]), index=data[1]), index=data[2])
