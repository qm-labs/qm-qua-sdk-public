from abc import ABC
from typing import Literal, cast
from dataclasses import dataclass
from itertools import combinations
from collections.abc import Mapping, Collection

from qm.exceptions import ContradictingPorts
from qm.config._ports._port_base import Port, LfFem, MwFem, LFLN08Fem, OpxPlusMockFem
from qm.config._ports._analog_input import (
    AnalogInputPort,
    AnalogInputPortLf,
    AnalogInputPortMw,
    AnalogInputPortOpx,
    AnalogInputPortLFLN08,
)
from qm.config._ports._analog_output import (
    AnalogOutputPort,
    AnalogOutputPortLf,
    AnalogOutputPortMw,
    AnalogOutputPortOpx,
    AnalogOutputPortLFLN08,
)
from qm.config._ports._digital_input import (
    DigitalInputPort,
    DigitalInputPortLf,
    DigitalInputPortMw,
    DigitalInputPortOpx,
    DigitalInputPortLFLN08,
)
from qm.config._ports._digital_output import (
    DigitalOutputPort,
    DigitalOutputPortLf,
    DigitalOutputPortMw,
    DigitalOutputPortOpx,
    DigitalOutputPortLFLN08,
)

FemType = Literal["OPX", "LF", "MW", "LF-LN08"]


@dataclass(frozen=True)
class _OutputType(ABC):
    analog_outputs: tuple[AnalogOutputPort, ...]
    analog_inputs: tuple[AnalogInputPort, ...]
    digital_outputs: tuple[DigitalOutputPort, ...]
    digital_inputs: tuple[DigitalInputPort, ...]

    @property
    def all_ports(self) -> tuple[Port, ...]:
        return self.analog_outputs + self.analog_inputs + self.digital_outputs + self.digital_inputs


@dataclass(frozen=True)
class FemDataOpx(_OutputType):
    analog_outputs: tuple[AnalogOutputPortOpx, ...]
    analog_inputs: tuple[AnalogInputPortOpx, ...]
    digital_outputs: tuple[DigitalOutputPortOpx, ...]
    digital_inputs: tuple[DigitalInputPortOpx, ...]


@dataclass(frozen=True)
class FemDataOctoDac(_OutputType):
    analog_outputs: tuple[AnalogOutputPortLf, ...]
    analog_inputs: tuple[AnalogInputPortLf, ...]
    digital_outputs: tuple[DigitalOutputPortLf, ...]
    digital_inputs: tuple[DigitalInputPortLf, ...]


@dataclass(frozen=True)
class FemDataMicrowave(_OutputType):
    analog_outputs: tuple[AnalogOutputPortMw, ...]
    analog_inputs: tuple[AnalogInputPortMw, ...]
    digital_outputs: tuple[DigitalOutputPortMw, ...]
    digital_inputs: tuple[DigitalInputPortMw, ...]


@dataclass(frozen=True)
class FemDataLFLN08(_OutputType):
    analog_outputs: tuple[AnalogOutputPortLFLN08, ...]
    analog_inputs: tuple[AnalogInputPortLFLN08, ...]
    digital_outputs: tuple[DigitalOutputPortLFLN08, ...]
    digital_inputs: tuple[DigitalInputPortLFLN08, ...]


AllFems = FemDataOpx | FemDataOctoDac | FemDataMicrowave | FemDataLFLN08


@dataclass
class _PortsContainerInternal:
    """
    This dataclass is just for arranging the ports, afterwords we find their type and return a frozen dataclass
    associated with a specific fem.
    """

    analog_outputs: list[AnalogOutputPort,]
    analog_inputs: list[AnalogInputPort]
    digital_outputs: list[DigitalOutputPort]
    digital_inputs: list[DigitalInputPort]


def split_to_fems(output_data: Collection[Port]) -> Mapping[str, Mapping[int, AllFems]]:
    tmp: dict[str, dict[int, _PortsContainerInternal]] = {}
    for p in output_data:
        if p.controller_name not in tmp:
            tmp[p.controller_name] = {}
        if p.fem_1_based not in tmp[p.controller_name]:
            tmp[p.controller_name][p.fem_1_based] = _PortsContainerInternal([], [], [], [])
    for p in output_data:
        if isinstance(p, AnalogOutputPort):
            tmp[p.controller_name][p.fem_1_based].analog_outputs.append(p)
        elif isinstance(p, AnalogInputPort):
            tmp[p.controller_name][p.fem_1_based].analog_inputs.append(p)
        elif isinstance(p, DigitalOutputPort):
            tmp[p.controller_name][p.fem_1_based].digital_outputs.append(p)
        elif isinstance(p, DigitalInputPort):
            tmp[p.controller_name][p.fem_1_based].digital_inputs.append(p)
        else:
            raise TypeError(f"Unsupported output type - {type(p)}")

    to_return: dict[str, dict[int, AllFems]] = {}
    for name, controller in tmp.items():
        to_return[name] = {}
        for fem_idx, fem_data in controller.items():
            to_return[name][fem_idx] = _get_fem_data(fem_data)
    return to_return


def _get_fem_type(ports: Collection[Port]) -> FemType | None:
    if not ports:
        return None
    if all(isinstance(p.fem, OpxPlusMockFem) for p in ports):
        return "OPX"
    if all(isinstance(p.fem, LfFem) for p in ports):
        return "LF"
    if all(isinstance(p.fem, MwFem) for p in ports):
        return "MW"
    if all(isinstance(p.fem, LFLN08Fem) for p in ports):
        return "LF-LN08"
    raise TypeError(f"Unknown analog output or multiple types - {[type(p.fem) for p in ports]}")


def _validate_ports_compatible(ports: Collection[Port]) -> None:
    # All ports here already share the same fem, signal type and direction, so this is
    # O(k^2) on the number of ports of that kind per fem (~a handful), not on the total port count.
    for port, other in combinations(ports, 2):
        if not port.is_compatible(other):
            raise ContradictingPorts(
                f"Conflicting declarations for controller '{port.controller_name}', FEM {port.fem_1_based}:\n"
                f"  {port.direction} {port.signal_type} port #{port.index_1_based}: {vars(port)}\n"
                f"  {other.direction} {other.signal_type} port #{other.index_1_based}: {vars(other)}"
            )


def _get_fem_data(data: _PortsContainerInternal) -> AllFems:
    for ports in (data.analog_outputs, data.analog_inputs, data.digital_outputs, data.digital_inputs):
        _validate_ports_compatible(ports)
    all_ports: Collection[Port] = (
        tuple(data.analog_outputs)
        + tuple(data.digital_outputs)
        + tuple(data.analog_inputs)
        + tuple(data.digital_inputs)
    )
    fem_type = _get_fem_type(all_ports)
    if fem_type == "OPX":
        return FemDataOpx(
            analog_outputs=tuple(cast(list[AnalogOutputPortOpx], data.analog_outputs)),
            analog_inputs=tuple(cast(list[AnalogInputPortOpx], data.analog_inputs)),
            digital_outputs=tuple(cast(list[DigitalOutputPortOpx], data.digital_outputs)),
            digital_inputs=tuple(cast(list[DigitalInputPortOpx], data.digital_inputs)),
        )
    elif fem_type == "LF":
        return FemDataOctoDac(
            analog_outputs=tuple(cast(list[AnalogOutputPortLf], data.analog_outputs)),
            analog_inputs=tuple(cast(list[AnalogInputPortLf], data.analog_inputs)),
            digital_outputs=tuple(cast(list[DigitalOutputPortLf], data.digital_outputs)),
            digital_inputs=tuple(cast(list[DigitalInputPortLf], data.digital_inputs)),
        )
    elif fem_type == "MW":
        return FemDataMicrowave(
            analog_outputs=tuple(cast(list[AnalogOutputPortMw], data.analog_outputs)),
            analog_inputs=tuple(cast(list[AnalogInputPortMw], data.analog_inputs)),
            digital_outputs=tuple(cast(list[DigitalOutputPortMw], data.digital_outputs)),
            digital_inputs=tuple(cast(list[DigitalInputPortMw], data.digital_inputs)),
        )
    elif fem_type == "LF-LN08":
        return FemDataLFLN08(
            analog_outputs=tuple(cast(list[AnalogOutputPortLFLN08], data.analog_outputs)),
            analog_inputs=tuple(cast(list[AnalogInputPortLFLN08], data.analog_inputs)),
            digital_outputs=tuple(cast(list[DigitalOutputPortLFLN08], data.digital_outputs)),
            digital_inputs=tuple(cast(list[DigitalInputPortLFLN08], data.digital_inputs)),
        )
    else:
        raise TypeError(f"Unknown fem type - {fem_type}")
