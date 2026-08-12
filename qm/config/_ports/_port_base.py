from typing import Literal
from abc import ABC, abstractmethod

from qm.api.models.capabilities import OPX_FEM_IDX
from qm.config._primitives import ConfigObject, ConfigOptional, create_value

StandardPort = tuple[str, int, int]
PortReferenceType = tuple[str, int] | StandardPort
SignalType = Literal["analog", "digital"]
Direction = Literal["input", "output"]
Band = Literal[1, 2, 3]


class Controller(ConfigObject, ABC):
    """A class that represents a device, either OPX+ or OPX1000"""

    def __init__(self, name: str) -> None:
        """
        Args:
            name: The name of the device.
        """
        self.name = name

    def is_compatible(self, other: "Controller") -> bool:
        return self.name != other.name or self == other

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self.name)})"


class OpxPlus(Controller):
    """A class that represents an OPX+"""


class Opx1000(Controller):
    """A class that represents an OPX1000"""


class FemBase(ConfigObject, ABC):
    """
    A class that represents a single Front-End-Module
    """

    def __init__(self, controller: Opx1000 | OpxPlus, index: int) -> None:
        """
        Args:
            controller: The controller that this fem is connected to
            index: 1-based index of the FEM
        """
        self.index = int(index)
        self.controller = controller

    @property
    def controller_name(self) -> str:
        return self.controller.name

    @property
    def index_1_based(self) -> int:
        return self.index

    def is_compatible(self, other: "FemBase") -> bool:
        if not self.controller.is_compatible(other.controller):
            return False
        if self.index != other.index:
            return True
        return self == other


class Fem(FemBase, ABC):
    def __init__(self, controller: Opx1000, index: int) -> None:
        super().__init__(controller=controller, index=index)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self.controller)}, index={repr(self.index)})"


class LfFem(Fem):
    """Represents a low-frequency FEM"""


class MwFem(Fem):
    """Represents a microwave FEM"""


class OpxPlusMockFem(FemBase):
    """A mock for OPX+, to make it look like a FEM"""

    def __init__(self, controller: OpxPlus) -> None:
        super().__init__(controller=controller, index=OPX_FEM_IDX)


class Port(ConfigObject, ABC):
    """A base class for a port, that holds the common features of the ports"""

    def __init__(self, fem: FemBase, index: int, shareable: ConfigOptional[bool]):
        """
        Args:
            fem: The fem of the port
            index: 1-based index of the port
            shareable: Whether the port is shareable or not
        """
        self.fem = fem
        self.index = int(index)
        self.shareable = create_value(shareable, False)

    @property
    def controller_name(self) -> str:
        return self.fem.controller.name

    @property
    def fem_1_based(self) -> int:
        return self.fem.index_1_based

    @property
    def index_1_based(self) -> int:
        return self.index

    @property
    @abstractmethod
    def signal_type(self) -> SignalType:
        pass

    @property
    @abstractmethod
    def direction(self) -> Direction:
        pass

    def is_compatible(self, other: "Port") -> bool:
        if not self.fem.is_compatible(other.fem):
            return False
        if self.index != other.index or self.signal_type != other.signal_type or self.direction != other.direction:
            return True
        return self == other


class PortReference(ConfigObject):
    """
    Duck typing for the transition between dict and model.
    When running update mode and the used didn't state the port, we need to create them by ourselves
    """

    def __init__(self, controller: str, fem: int, index: int):
        self.controller = controller
        self.fem = fem
        self.index = index

    @property
    def controller_name(self) -> str:
        return self.controller

    @property
    def fem_1_based(self) -> int:
        return self.fem

    @property
    def index_1_based(self) -> int:
        return self.index
