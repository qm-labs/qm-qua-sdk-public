from typing import Any, Generic, TypeVar

from qm.config._primitives import NamedObject
from qm.config._ports._analog_input import standardize_lf_input_port
from qm.config._ports import StandardPort, AnalogInputPort, AnalogInputPortLf, AnalogInputPortMicrowave

PortT = TypeVar("PortT", bound=AnalogInputPort)


class ElementOutput(Generic[PortT], NamedObject):
    """An output of an element, connected to a controller analog input port."""

    def __init__(self, port: PortT, name: str = "") -> None:
        """
        Args:
            port: The controller's analog input port that receives this element's
                output.
            name: Output name (used as the key in the element's ``outputs`` mapping).
                Auto-generated if empty.
        """
        super().__init__(name)
        self.port = port


class ElementOutputLf(ElementOutput[AnalogInputPortLf]):
    """An element output backed by a low-frequency analog input port."""


class ElementOutputMw(ElementOutput[AnalogInputPortMicrowave]):
    """The MW output of an element, backed by an MW-FEM analog input port."""


OutputOptions = AnalogInputPortLf | AnalogInputPortMicrowave | ElementOutput[Any] | StandardPort | tuple[str, int]


def standardize_output(output: OutputOptions) -> ElementOutput[Any]:
    if isinstance(output, (ElementOutputLf, ElementOutputMw)):
        return output
    if isinstance(output, (tuple, AnalogInputPortLf)):
        port = standardize_lf_input_port(output)
        # We add the name so if someone uses the same port more than once, it will not be added
        return ElementOutputLf(port, name=f"{port.controller_name}_{port.fem_1_based}_{port.index_1_based}")
    if isinstance(output, AnalogInputPortMicrowave):
        return ElementOutputMw(output)
    raise TypeError(f"Unsupported output type {type(output)}")
