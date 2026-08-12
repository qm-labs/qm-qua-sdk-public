from typing import TypeVar
from collections.abc import Collection

from qm.type_hinting.config_types import StandardPort
from qm.config._ports._port_base import Port, PortReference
from qm.config._ports._digital_input import DigitalInputPort
from qm.config._ports._digital_output import DigitalOutputPort
from qm.config._ports._analog_input import AnalogInputPortLf, AnalogInputPortMicrowave
from qm.config._ports._analog_output import AnalogOutputPortLf, AnalogOutputPortMicrowave

T = TypeVar("T")


class PortDict(dict[StandardPort, T]):
    def __missing__(self, port: StandardPort) -> PortReference:
        return PortReference(*port)


class PortLookup:
    def __init__(self, ports: Collection[Port], raise_if_missing: bool = True) -> None:
        if raise_if_missing:
            self.analog_outputs_lf: dict[StandardPort, AnalogOutputPortLf] = {}
            self.analog_outputs_mw: dict[StandardPort, AnalogOutputPortMicrowave] = {}
            self.analog_inputs_lf: dict[StandardPort, AnalogInputPortLf] = {}
            self.analog_inputs_mw: dict[StandardPort, AnalogInputPortMicrowave] = {}
            self.digital_outputs: dict[StandardPort, DigitalOutputPort] = {}
            self.digital_inputs: dict[StandardPort, DigitalInputPort] = {}
        else:
            self.analog_outputs_lf = PortDict()
            self.analog_outputs_mw = PortDict()
            self.analog_inputs_lf = PortDict()
            self.analog_inputs_mw = PortDict()
            self.digital_outputs = PortDict()
            self.digital_inputs = PortDict()

        for port in ports:
            key = (port.controller_name, port.fem_1_based, port.index_1_based)
            if isinstance(port, AnalogOutputPortLf):
                self.analog_outputs_lf[key] = port
            elif isinstance(port, AnalogOutputPortMicrowave):
                self.analog_outputs_mw[key] = port
            elif isinstance(port, AnalogInputPortLf):
                self.analog_inputs_lf[key] = port
            elif isinstance(port, AnalogInputPortMicrowave):
                self.analog_inputs_mw[key] = port
            elif isinstance(port, DigitalOutputPort):
                self.digital_outputs[key] = port
            elif isinstance(port, DigitalInputPort):
                self.digital_inputs[key] = port
