from abc import ABC
from typing import Literal

from qm.type_hinting import Number
from qm.config._primitives import NOT_SET, ConfigValue, ConfigOptional, create_value
from qm.config._ports._port_base import Port, LfFem, MwFem, FemBase, OpxPlus, Direction, SignalType, OpxPlusMockFem

Polarity = Literal["RISING", "FALLING"]


class DigitalInputPort(Port, ABC):
    """Base class for digital input ports of a controller."""

    def __init__(
        self,
        fem: FemBase,
        index: int,
        shareable: ConfigOptional[bool],
        deadtime: ConfigOptional[int],
        polarity: ConfigOptional[Polarity],
        threshold: ConfigOptional[Number],
    ):
        """
        Args:
            fem: The FEM (or mock FEM, for OPX+) the port belongs to.
            index: The 1-based port index on the FEM.
            shareable: Whether the port is shareable with other QM instances.
            deadtime: The minimal time between pulses, in ns.
            polarity: The detection edge - whether to trigger on the rising or falling
                edge of the pulse.
            threshold: The minimum voltage to trigger when a pulse arrives.
        """
        super().__init__(fem, index, shareable)
        self.deadtime = create_value(deadtime, 0)
        self.polarity: ConfigValue[Polarity] = create_value(polarity, "RISING")
        self.threshold = create_value(threshold, 0)

    @property
    def signal_type(self) -> SignalType:
        return "digital"

    @property
    def direction(self) -> Direction:
        return "input"


class DigitalInputPortOpx(DigitalInputPort):
    """Digital input port of an OPX+ controller."""

    def __init__(
        self,
        index: int,
        controller: OpxPlus,
        shareable: ConfigOptional[bool] = NOT_SET,
        deadtime: ConfigOptional[int] = NOT_SET,
        polarity: ConfigOptional[Polarity] = NOT_SET,
        threshold: ConfigOptional[Number] = NOT_SET,
    ):
        """
        Args:
            index: The 1-based port index on the controller.
            controller: The OPX+ controller this port belongs to.
            shareable: Whether the port is shareable with other QM instances.
            deadtime: The minimal time between pulses, in ns.
            polarity: ``"RISING"`` (default) or ``"FALLING"``.
            threshold: The minimum voltage to trigger when a pulse arrives.
        """
        super().__init__(
            fem=OpxPlusMockFem(controller),
            index=index,
            shareable=shareable,
            deadtime=deadtime,
            polarity=polarity,
            threshold=threshold,
        )
        self.controller = controller


class DigitalInputPortOpx1000(DigitalInputPort, ABC):
    """Base class for digital input ports on OPX1000 hardware (LF-FEM and MW-FEM)."""


class DigitalInputPortOctoDac(DigitalInputPortOpx1000):
    """Digital input port of an LF-FEM (OPX1000)."""

    def __init__(
        self,
        fem: LfFem,
        index: int,
        shareable: ConfigOptional[bool] = NOT_SET,
        deadtime: ConfigOptional[int] = NOT_SET,
        polarity: ConfigOptional[Polarity] = NOT_SET,
        threshold: ConfigOptional[Number] = NOT_SET,
    ):
        """
        Args:
            fem: The LF-FEM the port belongs to.
            index: The 1-based port index on the FEM.
            shareable: Whether the port is shareable with other QM instances.
            deadtime: The minimal time between pulses, in ns.
            polarity: ``"RISING"`` (default) or ``"FALLING"``.
            threshold: The minimum voltage to trigger when a pulse arrives.
        """
        super().__init__(
            fem=fem, index=index, shareable=shareable, deadtime=deadtime, polarity=polarity, threshold=threshold
        )


class DigitalInputPortMicrowave(DigitalInputPortOpx1000):
    """Digital input port of an MW-FEM (OPX1000 microwave front-end module)."""

    def __init__(
        self,
        fem: MwFem,
        index: int,
        shareable: ConfigOptional[bool] = NOT_SET,
        deadtime: ConfigOptional[int] = NOT_SET,
        polarity: ConfigOptional[Polarity] = NOT_SET,
        threshold: ConfigOptional[Number] = NOT_SET,
    ):
        """
        Args:
            fem: The MW-FEM the port belongs to.
            index: The 1-based port index on the FEM.
            shareable: Whether the port is shareable with other QM instances.
            deadtime: The minimal time between pulses, in ns.
            polarity: ``"RISING"`` (default) or ``"FALLING"``.
            threshold: The minimum voltage to trigger when a pulse arrives.
        """
        super().__init__(
            fem=fem, index=index, shareable=shareable, deadtime=deadtime, polarity=polarity, threshold=threshold
        )
