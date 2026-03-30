from typing import Dict, Union, Literal, Protocol, cast, overload

from qm.exceptions import InvalidConfigError
from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.utils.protobuf_utils import which_one_of

FemTypes = Union[
    inc_qua_config_pb2.QuaConfig.ControllerDec,
    inc_qua_config_pb2.QuaConfig.OctoDacFemDec,
    inc_qua_config_pb2.QuaConfig.MicrowaveFemDec,
]


class ControllerConfigProtocol(Protocol):
    control_devices: Dict[str, inc_qua_config_pb2.QuaConfig.DeviceDec]
    mixers: Dict[str, inc_qua_config_pb2.QuaConfig.MixerDec]
    octaves: Dict[str, inc_qua_config_pb2.QuaConfig.Octave.Config]


class LogicalConfigProtocol(Protocol):
    elements: Dict[str, inc_qua_config_pb2.QuaConfig.ElementDec]
    oscillators: Dict[str, inc_qua_config_pb2.QuaConfig.Oscillator]
    pulses: Dict[str, inc_qua_config_pb2.QuaConfig.PulseDec]
    waveforms: Dict[str, inc_qua_config_pb2.QuaConfig.WaveformDec]
    digital_waveforms: Dict[str, inc_qua_config_pb2.QuaConfig.DigitalWaveformDec]
    integration_weights: Dict[str, inc_qua_config_pb2.QuaConfig.IntegrationWeightDec]


# TODO: See if the functions in this file can be moved to the config models when they are created.


@overload
def _get_correct_config_part(
    part: Literal["controller"], pb_config: inc_qua_config_pb2.QuaConfig
) -> Union[inc_qua_config_pb2.QuaConfig.ControllerConfig, inc_qua_config_pb2.QuaConfig.QuaConfigV1]:
    pass


@overload
def _get_correct_config_part(
    part: Literal["logical"], pb_config: inc_qua_config_pb2.QuaConfig
) -> Union[inc_qua_config_pb2.QuaConfig.LogicalConfig, inc_qua_config_pb2.QuaConfig.QuaConfigV1]:
    pass


def _get_correct_config_part(
    part: Literal["controller", "logical"], pb_config: inc_qua_config_pb2.QuaConfig
) -> Union[
    inc_qua_config_pb2.QuaConfig.ControllerConfig,
    inc_qua_config_pb2.QuaConfig.LogicalConfig,
    inc_qua_config_pb2.QuaConfig.QuaConfigV1,
]:
    _, config_version_inst = which_one_of(pb_config, "config_version")
    if isinstance(config_version_inst, inc_qua_config_pb2.QuaConfig.QuaConfigV2):
        if part == "controller":
            return config_version_inst.controller_config
        elif part == "logical":
            return config_version_inst.logical_config
    elif isinstance(config_version_inst, inc_qua_config_pb2.QuaConfig.QuaConfigV1):
        return config_version_inst
    else:
        raise ValueError("Received unknown config type: " + str(type(config_version_inst)))


def _unset_correct_config_part(part: Literal["controller", "logical"], pb_config: inc_qua_config_pb2.QuaConfig) -> None:
    _, config_version_inst = which_one_of(pb_config, "config_version")
    if isinstance(config_version_inst, inc_qua_config_pb2.QuaConfig.QuaConfigV2):
        if part == "controller":
            config_version_inst.ClearField("controller_config")
        elif part == "logical":
            config_version_inst.ClearField("logical_config")
    elif isinstance(config_version_inst, inc_qua_config_pb2.QuaConfig.QuaConfigV1):
        pass
    else:
        raise ValueError("Received unknown config type: " + str(type(config_version_inst)))


def get_controller_pb_config(pb_config: inc_qua_config_pb2.QuaConfig) -> inc_qua_config_pb2.QuaConfig.ControllerConfig:
    return cast(inc_qua_config_pb2.QuaConfig.ControllerConfig, _get_correct_config_part("controller", pb_config))


def get_logical_pb_config(pb_config: inc_qua_config_pb2.QuaConfig) -> inc_qua_config_pb2.QuaConfig.LogicalConfig:
    return cast(inc_qua_config_pb2.QuaConfig.LogicalConfig, _get_correct_config_part("logical", pb_config))


def unset_controller_pb_config(pb_config: inc_qua_config_pb2.QuaConfig) -> None:
    _unset_correct_config_part("controller", pb_config)


def unset_logical_pb_config(pb_config: inc_qua_config_pb2.QuaConfig) -> None:
    _unset_correct_config_part("logical", pb_config)


def get_fem_config_instance(fem_ref: inc_qua_config_pb2.QuaConfig.FEMTypes) -> FemTypes:
    _, config = which_one_of(fem_ref, "fem_type_one_of")
    if not isinstance(
        config,
        (
            inc_qua_config_pb2.QuaConfig.ControllerDec,
            inc_qua_config_pb2.QuaConfig.OctoDacFemDec,
            inc_qua_config_pb2.QuaConfig.MicrowaveFemDec,
        ),
    ):
        raise InvalidConfigError(f"FEM type {type(config)} is not supported")
    return config


def get_fem_config(
    pb_config: inc_qua_config_pb2.QuaConfig,
    port: Union[
        inc_qua_config_pb2.QuaConfig.DacPortReference,
        inc_qua_config_pb2.QuaConfig.AdcPortReference,
        inc_qua_config_pb2.QuaConfig.PortReference,
    ],
) -> FemTypes:
    controller_config = get_controller_pb_config(pb_config)
    if port.controller not in controller_config.controlDevices:
        raise InvalidConfigError("Controller not found")
    controller = controller_config.controlDevices[port.controller]
    if port.fem not in controller.fems:
        raise InvalidConfigError("FEM not found")

    fem_ref = controller.fems[port.fem]
    config = get_fem_config_instance(fem_ref)
    return config


def element_has_mix_inputs(element: inc_qua_config_pb2.QuaConfig.ElementDec) -> bool:
    _, inputs_inst = which_one_of(element, "element_inputs_one_of")
    return isinstance(inputs_inst, inc_qua_config_pb2.QuaConfig.MixInputs)
