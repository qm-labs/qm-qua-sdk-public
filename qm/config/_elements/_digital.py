from qm.config._primitives import NamedObject
from qm.config._ports import DigitalInputPort, DigitalOutputPort


class ElementDigitalInput(NamedObject):
    """The specification of the digital input of an element."""

    def __init__(self, port: DigitalOutputPort, delay: int, buffer: int, name: str = ""):
        """
        Args:
            port: The controller's digital output port driving this input.
            delay: The delay to apply to the digital pulses, in ns. An intrinsic
                negative delay exists by default.
            buffer: Digital pulses played to this element will be convolved with a
                digital pulse of value ``1`` with this length [ns].
            name: Name used as the key in the element's ``digital_inputs`` mapping.
                Auto-generated if empty.
        """
        super().__init__(name)
        self.port = port
        self.delay = int(delay)
        self.buffer = int(buffer)


class ElementDigitalOutput(NamedObject):
    """The specification of the digital output of an element."""

    def __init__(self, port: DigitalInputPort, name: str = ""):
        """
        Args:
            port: The controller's digital input port that captures this output.
            name: Name used as the key in the element's ``digital_outputs`` mapping.
                Auto-generated if empty.
        """
        super().__init__(name)
        self.port = port
