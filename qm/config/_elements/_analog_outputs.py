from abc import ABC, abstractmethod
from collections.abc import Mapping, Collection

from qm.config._primitives import ConfigObject
from qm.config._ports._analog_input import standardize_lf_input_port
from qm.config._ports import StandardPort, AnalogInputPort, AnalogInputPortMw, AnalogInputPortLfBase

LfPortOptions = AnalogInputPortLfBase | StandardPort | tuple[str, int]

DEFAULT_OUT1 = "out1"
DEFAULT_OUT2 = "out2"


class ElementOutput(ConfigObject, ABC):
    """Base type for the output of an element."""

    @property
    @abstractmethod
    def ports(self) -> Collection[AnalogInputPort]:
        pass

    @property
    @abstractmethod
    def name_to_port(self) -> Mapping[str, AnalogInputPort]:
        pass


class SingleLfOutput(ElementOutput):
    def __init__(self, port: LfPortOptions, name: str = DEFAULT_OUT1) -> None:
        self.out = standardize_lf_input_port(port)
        self.name = name

    @property
    def ports(self) -> Collection[AnalogInputPortLfBase]:
        return (self.out,)

    @property
    def name_to_port(self) -> Mapping[str, AnalogInputPortLfBase]:
        return {self.name: self.out}


class ComplexOutput(ElementOutput, ABC):
    """Represents all the outputs that are measured with I and Q"""

    @property
    @abstractmethod
    def out1_name(self) -> str:
        pass

    @property
    @abstractmethod
    def out2_name(self) -> str:
        pass


class MixedLfOutput(ComplexOutput):
    def __init__(
        self, port1: LfPortOptions, port2: LfPortOptions, name1: str = DEFAULT_OUT1, name2: str = DEFAULT_OUT2
    ) -> None:
        self.out1 = standardize_lf_input_port(port1)
        self.out2 = standardize_lf_input_port(port2)
        self._out1_name = name1
        self._out2_name = name2

    @property
    def ports(self) -> Collection[AnalogInputPortLfBase]:
        return self.out1, self.out2

    @property
    def out1_name(self) -> str:
        return self._out1_name

    @property
    def out2_name(self) -> str:
        return self._out2_name

    @property
    def name_to_port(self) -> Mapping[str, AnalogInputPortLfBase]:
        return {self.out1_name: self.out1, self.out2_name: self.out2}


class MwOutput(ComplexOutput):
    def __init__(self, port: AnalogInputPortMw) -> None:
        self.out = port

    @property
    def name_to_port(self) -> Mapping[str, AnalogInputPortMw]:
        # This method is for the config creation, and there, no name is needed
        return {}

    @property
    def out1_name(self) -> str:
        # This is just for the case where only one port is wanted to be measured
        return DEFAULT_OUT1

    @property
    def out2_name(self) -> str:
        # This is just for the case where only one port is wanted to be measured
        return DEFAULT_OUT2

    @property
    def ports(self) -> Collection[AnalogInputPortMw]:
        return (self.out,)
