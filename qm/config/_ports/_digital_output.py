from abc import ABC
from typing import Literal

from qm.config._primitives import NOT_SET, ConfigValue, ConfigOptional, create_value
from qm.config._ports._port_base import Port, LfFem, MwFem, FemBase, OpxPlus, Direction, SignalType, OpxPlusMockFem

Level = Literal["TTL", "LVTTL"]


class DigitalOutputPort(Port, ABC):
    """Base class for digital output ports of a controller."""

    def __init__(
        self,
        fem: FemBase,
        index: int,
        shareable: ConfigOptional[bool],
        inverted: ConfigOptional[bool],
    ):
        """
        Args:
            fem: The FEM (or mock FEM, for OPX+) the port belongs to.
            index: The 1-based port index on the FEM.
            shareable: Whether the port is shareable with other QM instances.
            inverted: Whether the port is inverted. If ``True``, the output will be
                inverted.
        """
        super().__init__(fem=fem, index=index, shareable=create_value(shareable, False))
        self.inverted = create_value(inverted, False)

    @property
    def signal_type(self) -> SignalType:
        return "digital"

    @property
    def direction(self) -> Direction:
        return "output"


class DigitalOutputPortLf(DigitalOutputPort, ABC):
    """Base class for digital output ports on low-frequency hardware (OPX+ and LF-FEM)."""

    def __init__(
        self,
        fem: FemBase,
        index: int,
        shareable: ConfigOptional[bool] = NOT_SET,
        inverted: ConfigOptional[bool] = NOT_SET,
    ):
        """
        Args:
            fem: The FEM (or mock FEM, for OPX+) the port belongs to.
            index: The 1-based port index on the FEM.
            shareable: Whether the port is shareable with other QM instances.
            inverted: Whether the port is inverted.
        """
        super().__init__(
            fem=fem, index=index, shareable=create_value(shareable, False), inverted=create_value(inverted, False)
        )


class DigitalOutputPortOpx(DigitalOutputPortLf):
    """Digital output port of an OPX+ controller."""

    def __init__(
        self,
        controller: OpxPlus,
        index: int,
        shareable: ConfigOptional[bool] = NOT_SET,
        inverted: ConfigOptional[bool] = NOT_SET,
    ):
        """
        Args:
            controller: The OPX+ controller this port belongs to.
            index: The 1-based port index on the controller.
            shareable: Whether the port is shareable with other QM instances.
            inverted: Whether the port is inverted.
        """
        super().__init__(
            fem=OpxPlusMockFem(controller),
            index=index,
            shareable=create_value(shareable, False),
            inverted=create_value(inverted, False),
        )
        self.controller = controller


class DigitalOutputPortOctoDac(DigitalOutputPortLf):
    """Digital output port of an LF-FEM (OPX1000)."""

    def __init__(
        self,
        fem: LfFem,
        index: int,
        shareable: ConfigOptional[bool] = NOT_SET,
        inverted: ConfigOptional[bool] = NOT_SET,
    ):
        """
        Args:
            fem: The LF-FEM the port belongs to.
            index: The 1-based port index on the FEM.
            shareable: Whether the port is shareable with other QM instances.
            inverted: Whether the port is inverted.
        """
        super().__init__(
            fem=fem, index=index, shareable=create_value(shareable, False), inverted=create_value(inverted, False)
        )


class DigitalOutputPortMicrowave(DigitalOutputPort):
    """Digital output port of an MW-FEM (OPX1000 microwave front-end module)."""

    def __init__(
        self,
        fem: MwFem,
        index: int,
        shareable: ConfigOptional[bool] = NOT_SET,
        inverted: ConfigOptional[bool] = NOT_SET,
        level: ConfigOptional[Level] = NOT_SET,
    ):
        """
        Args:
            fem: The MW-FEM the port belongs to.
            index: The 1-based port index on the FEM.
            shareable: Whether the port is shareable with other QM instances.
            inverted: Whether the port is inverted.
            level: The voltage level of the digital output, ``"TTL"`` or ``"LVTTL"``
                (default). Currently, only ``"LVTTL"`` is supported.
        """
        super().__init__(
            fem=fem, index=index, shareable=create_value(shareable, False), inverted=create_value(inverted, False)
        )
        self.level: ConfigValue[Level] = create_value(level, "LVTTL")
