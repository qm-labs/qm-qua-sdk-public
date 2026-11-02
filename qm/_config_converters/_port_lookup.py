from typing import TypeVar
from collections.abc import Collection

from qm.config._ports._port_base import PortReference
from qm.type_hinting.config_types import StandardPort, PortReferenceType
from qm.config._ports import AnalogInputPortLfBase, AnalogOutputPortLfBase
from qm.config import (
    Port,
    DigitalInputPort,
    AnalogInputPortMw,
    DigitalOutputPort,
    AnalogOutputPortMw,
)

T = TypeVar("T")


def resolve_port_ref(ref: PortReferenceType) -> StandardPort:
    default_fem = 1  # only for opx+
    if len(ref) == 3:
        return str(ref[0]), int(ref[1]), int(ref[2])
    if len(ref) == 2:
        return str(ref[0]), default_fem, int(ref[1])
    raise ValueError(f"Invalid port reference: {ref}")


class PortDict(dict[StandardPort, T]):
    def __missing__(self, port: StandardPort) -> PortReference:
        return PortReference(*port)


class PortLookup:
    def __init__(self, ports: Collection[Port], raise_if_missing: bool = True) -> None:
        if raise_if_missing:
            self.analog_outputs_lf: dict[StandardPort, AnalogOutputPortLfBase] = {}
            self.analog_outputs_mw: dict[StandardPort, AnalogOutputPortMw] = {}
            self.analog_inputs_lf: dict[StandardPort, AnalogInputPortLfBase] = {}
            self.analog_inputs_mw: dict[StandardPort, AnalogInputPortMw] = {}
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
            if isinstance(port, AnalogOutputPortLfBase):
                self.analog_outputs_lf[key] = port
            elif isinstance(port, AnalogOutputPortMw):
                self.analog_outputs_mw[key] = port
            elif isinstance(port, AnalogInputPortLfBase):
                self.analog_inputs_lf[key] = port
            elif isinstance(port, AnalogInputPortMw):
                self.analog_inputs_mw[key] = port
            elif isinstance(port, DigitalOutputPort):
                self.digital_outputs[key] = port
            elif isinstance(port, DigitalInputPort):
                self.digital_inputs[key] = port
