from typing import Literal, cast
from dataclasses import dataclass
from collections.abc import Mapping, Collection

from qm.config._ports._port_base import Port, LfFem, MwFem, OpxPlusMockFem
from qm.config._ports._analog_input import (
    AnalogInputPort,
    AnalogInputPortOpx,
    AnalogInputPortOctoDac,
    AnalogInputPortMicrowave,
)
from qm.config._ports._analog_output import (
    AnalogOutputPort,
    AnalogOutputPortOpx,
    AnalogOutputPortOctoDac,
    AnalogOutputPortMicrowave,
)
from qm.config._ports._digital_input import (
    DigitalInputPort,
    DigitalInputPortOpx,
    DigitalInputPortOctoDac,
    DigitalInputPortMicrowave,
)
from qm.config._ports._digital_output import (
    DigitalOutputPort,
    DigitalOutputPortOpx,
    DigitalOutputPortOctoDac,
    DigitalOutputPortMicrowave,
)

FemType = Literal["OPX", "LF", "MW"]


@dataclass
class _OutputType:
    analog_outputs: list[AnalogOutputPort]
    analog_inputs: list[AnalogInputPort]
    digital_outputs: list[DigitalOutputPort]
    digital_inputs: list[DigitalInputPort]


@dataclass(frozen=True)
class FemDataOpx:
    analog_outputs: tuple[AnalogOutputPortOpx, ...]
    analog_inputs: tuple[AnalogInputPortOpx, ...]
    digital_outputs: tuple[DigitalOutputPortOpx, ...]
    digital_inputs: tuple[DigitalInputPortOpx, ...]


@dataclass(frozen=True)
class FemDataOctoDac:
    analog_outputs: tuple[AnalogOutputPortOctoDac, ...]
    analog_inputs: tuple[AnalogInputPortOctoDac, ...]
    digital_outputs: tuple[DigitalOutputPortOctoDac, ...]
    digital_inputs: tuple[DigitalInputPortOctoDac, ...]


@dataclass(frozen=True)
class FemDataMicrowave:
    analog_outputs: tuple[AnalogOutputPortMicrowave, ...]
    analog_inputs: tuple[AnalogInputPortMicrowave, ...]
    digital_outputs: tuple[DigitalOutputPortMicrowave, ...]
    digital_inputs: tuple[DigitalInputPortMicrowave, ...]


AllFems = FemDataOpx | FemDataOctoDac | FemDataMicrowave


def split_to_fems(output_data: Collection[Port]) -> Mapping[str, Mapping[int, AllFems]]:
    tmp: dict[str, dict[int, _OutputType]] = {}
    for p in output_data:
        if p.controller_name not in tmp:
            tmp[p.controller_name] = {}
        if p.fem_1_based not in tmp[p.controller_name]:
            tmp[p.controller_name][p.fem_1_based] = _OutputType([], [], [], [])
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
    raise TypeError(f"Unknown analog output or multiple types - {[type(p.fem) for p in ports]}")


def _get_fem_data(data: _OutputType) -> AllFems:
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
            analog_outputs=tuple(cast(list[AnalogOutputPortOctoDac], data.analog_outputs)),
            analog_inputs=tuple(cast(list[AnalogInputPortOctoDac], data.analog_inputs)),
            digital_outputs=tuple(cast(list[DigitalOutputPortOctoDac], data.digital_outputs)),
            digital_inputs=tuple(cast(list[DigitalInputPortOctoDac], data.digital_inputs)),
        )
    elif fem_type == "MW":
        return FemDataMicrowave(
            analog_outputs=tuple(cast(list[AnalogOutputPortMicrowave], data.analog_outputs)),
            analog_inputs=tuple(cast(list[AnalogInputPortMicrowave], data.analog_inputs)),
            digital_outputs=tuple(cast(list[DigitalOutputPortMicrowave], data.digital_outputs)),
            digital_inputs=tuple(cast(list[DigitalInputPortMicrowave], data.digital_inputs)),
        )
    else:
        raise TypeError(f"Unknown fem type - {fem_type}")
