from typing import Dict, Union, Literal, Protocol, overload

import betterproto

from qm.exceptions import InvalidConfigError
from qm.grpc.qua_config import (
    QuaConfig,
    QuaConfigFemTypes,
    QuaConfigMixerDec,
    QuaConfigPulseDec,
    QuaConfigDeviceDec,
    QuaConfigMixInputs,
    QuaConfigElementDec,
    QuaConfigOscillator,
    QuaConfigQuaConfigV1,
    QuaConfigQuaConfigV2,
    QuaConfigWaveformDec,
    QuaConfigOctaveConfig,
    QuaConfigControllerDec,
    QuaConfigLogicalConfig,
    QuaConfigOctoDacFemDec,
    QuaConfigPortReference,
    QuaConfigMicrowaveFemDec,
    QuaConfigAdcPortReference,
    QuaConfigControllerConfig,
    QuaConfigDacPortReference,
    QuaConfigDigitalWaveformDec,
    QuaConfigIntegrationWeightDec,
)

FemTypes = Union[QuaConfigControllerDec, QuaConfigOctoDacFemDec, QuaConfigMicrowaveFemDec]


class ControllerConfigProtocol(Protocol):
    control_devices: Dict[str, QuaConfigDeviceDec]
    mixers: Dict[str, QuaConfigMixerDec]
    octaves: Dict[str, QuaConfigOctaveConfig]


class LogicalConfigProtocol(Protocol):
    elements: Dict[str, QuaConfigElementDec]
    oscillators: Dict[str, QuaConfigOscillator]
    pulses: Dict[str, QuaConfigPulseDec]
    waveforms: Dict[str, QuaConfigWaveformDec]
    digital_waveforms: Dict[str, QuaConfigDigitalWaveformDec]
    integration_weights: Dict[str, QuaConfigIntegrationWeightDec]


# TODO: See if the functions in this file can be moved to the config models when they are created.


@overload
def _get_correct_config_part(
    part: Literal["controller"], pb_config: QuaConfig
) -> Union[QuaConfigControllerConfig, QuaConfigQuaConfigV1]:
    pass


@overload
def _get_correct_config_part(
    part: Literal["logical"], pb_config: QuaConfig
) -> Union[QuaConfigLogicalConfig, QuaConfigQuaConfigV1]:
    pass


def _get_correct_config_part(
    part: Literal["controller", "logical"], pb_config: QuaConfig
) -> Union[QuaConfigControllerConfig, QuaConfigLogicalConfig, QuaConfigQuaConfigV1]:
    _, config_version_inst = betterproto.which_one_of(pb_config, "config_version")
    if isinstance(config_version_inst, QuaConfigQuaConfigV2):
        if part == "controller":
            return config_version_inst.controller_config
        elif part == "logical":
            return config_version_inst.logical_config
    elif isinstance(config_version_inst, QuaConfigQuaConfigV1):
        return config_version_inst
    else:
        raise ValueError("Received unknown config type: " + str(type(config_version_inst)))


def get_controller_pb_config(pb_config: QuaConfig) -> ControllerConfigProtocol:
    return _get_correct_config_part("controller", pb_config)


def get_logical_pb_config(pb_config: QuaConfig) -> LogicalConfigProtocol:
    return _get_correct_config_part("logical", pb_config)


def get_fem_config_instance(fem_ref: QuaConfigFemTypes) -> FemTypes:
    _, config = betterproto.which_one_of(fem_ref, "fem_type_one_of")
    if not isinstance(config, (QuaConfigControllerDec, QuaConfigOctoDacFemDec, QuaConfigMicrowaveFemDec)):
        raise InvalidConfigError(f"FEM type {type(config)} is not supported")
    return config


def get_fem_config(
    pb_config: QuaConfig, port: Union[QuaConfigDacPortReference, QuaConfigAdcPortReference, QuaConfigPortReference]
) -> FemTypes:
    controller_config = get_controller_pb_config(pb_config)
    if port.controller not in controller_config.control_devices:
        raise InvalidConfigError("Controller not found")
    controller = controller_config.control_devices[port.controller]
    if port.fem not in controller.fems:
        raise InvalidConfigError("FEM not found")

    fem_ref = controller.fems[port.fem]
    config = get_fem_config_instance(fem_ref)
    return config


def element_has_mix_inputs(element: QuaConfigElementDec) -> bool:
    _, inputs_inst = betterproto.which_one_of(element, "element_inputs_one_of")
    return isinstance(inputs_inst, QuaConfigMixInputs)
