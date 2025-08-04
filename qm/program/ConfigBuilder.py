from typing import Dict, List, Tuple, Union, Literal, Mapping, Optional, cast

import betterproto
from dependency_injector.wiring import Provide, inject

from qm.type_hinting import Number
from qm.api.models.capabilities import QopCaps, ServerCapabilities
from qm.containers.capabilities_container import CapabilitiesContainer
from qm.utils.config_utils import get_logical_pb_config, get_controller_pb_config
from qm.type_hinting.config_types import (
    FEM_IDX,
    Band,
    Upconverter,
    FullQuaConfig,
    LfFemConfigType,
    MixerConfigType,
    MwFemConfigType,
    PulseConfigType,
    StickyConfigType,
    ElementConfigType,
    MwInputConfigType,
    PortReferenceType,
    MixInputConfigType,
    MwOutputConfigType,
    ControllerConfigType,
    HoldOffsetConfigType,
    OscillatorConfigType,
    MixWaveformConfigType,
    SingleInputConfigType,
    DigitalInputConfigType,
    WaveformArrayConfigType,
    SingleWaveformConfigType,
    AnalogInputPortConfigType,
    DigitalWaveformConfigType,
    InputCollectionConfigType,
    AnalogOutputPortConfigType,
    ConstantWaveformConfigType,
    DigitalInputPortConfigType,
    ArbitraryWaveformConfigType,
    DigitalOutputPortConfigType,
    IntegrationWeightConfigType,
    OPX1000ControllerConfigType,
    AnalogOutputFilterConfigType,
    MwFemAnalogInputPortConfigType,
    MwFemAnalogOutputPortConfigType,
    TimeTaggingParametersConfigType,
    AnalogOutputFilterConfigTypeQop33,
    AnalogOutputFilterConfigTypeQop35,
    AnalogOutputPortConfigTypeOctoDac,
)
from qm.grpc.qua_config import (
    QuaConfig,
    QuaConfigMatrix,
    QuaConfigSticky,
    QuaConfigFemTypes,
    QuaConfigMixerDec,
    QuaConfigPulseDec,
    QuaConfigDeviceDec,
    QuaConfigMixInputs,
    QuaConfigElementDec,
    QuaConfigHoldOffset,
    QuaConfigOscillator,
    QuaConfigQuaConfigV1,
    QuaConfigSingleInput,
    QuaConfigWaveformDec,
    QuaConfigControllerDec,
    QuaConfigElementThread,
    QuaConfigOctoDacFemDec,
    QuaConfigPortReference,
    QuaConfigMultipleInputs,
    QuaConfigCorrectionEntry,
    QuaConfigMicrowaveFemDec,
    QuaConfigMultipleOutputs,
    QuaConfigAdcPortReference,
    QuaConfigDacPortReference,
    QuaConfigWaveformArrayDec,
    QuaConfigPulseDecOperation,
    QuaConfigAnalogInputPortDec,
    QuaConfigDigitalWaveformDec,
    QuaConfigAnalogOutputPortDec,
    QuaConfigConstantWaveformDec,
    QuaConfigDigitalInputPortDec,
    QuaConfigArbitraryWaveformDec,
    QuaConfigDigitalOutputPortDec,
    QuaConfigIntegrationWeightDec,
    QuaConfigOutputPulseParameters,
    QuaConfigSingleInputCollection,
    QuaConfigAnalogOutputPortFilter,
    QuaConfigDigitalInputPortReference,
    QuaConfigDigitalOutputPortReference,
    QuaConfigOctoDacAnalogOutputPortDec,
    QuaConfigDigitalInputPortDecPolarity,
    QuaConfigMicrowaveAnalogInputPortDec,
    QuaConfigMicrowaveInputPortReference,
    QuaConfigMicrowaveAnalogOutputPortDec,
    QuaConfigMicrowaveOutputPortReference,
    QuaConfigOutputPulseParametersPolarity,
    QuaConfigOctoDacAnalogOutputPortDecOutputMode,
    QuaConfigOctoDacAnalogOutputPortDecSamplingRateMode,
)


def convert_msg_to_config(config: QuaConfig) -> FullQuaConfig:
    controller_config = get_controller_pb_config(config)
    logical_config = get_logical_pb_config(config)

    if controller_config.control_devices:
        controllers = _convert_controller_types(controller_config.control_devices)
    elif isinstance(controller_config, QuaConfigQuaConfigV1) and controller_config.controllers:
        controllers = {
            name: _convert_controller(controller) for name, controller in controller_config.controllers.items()
        }
    else:
        controllers = {}

    result: FullQuaConfig = {
        "controllers": controllers,
        "oscillators": _convert_oscillators(logical_config.oscillators),
        "elements": _convert_elements(logical_config.elements),
        "pulses": _convert_pulses(logical_config.pulses),
        "waveforms": _convert_wave_forms(logical_config.waveforms),
        "digital_waveforms": _convert_digital_wave_forms(logical_config.digital_waveforms),
        "integration_weights": _convert_integration_weights(logical_config.integration_weights),
        "mixers": _convert_mixers(controller_config.mixers),
    }

    return result


def _convert_single_correction_entry(correction: QuaConfigCorrectionEntry) -> MixerConfigType:
    frequency: Optional[Union[int, float]]
    lo_frequency: Optional[Union[int, float]]

    if correction.frequency_double:
        frequency = correction.frequency_double
    else:
        frequency = correction.frequency

    if correction.frequency_negative is True:
        assert frequency is not None  # Mypy thinks it can be None, but it can't really (frequency has a default value)
        frequency = -frequency

    if correction.lo_frequency_double:
        lo_frequency = correction.lo_frequency_double
    else:
        lo_frequency = correction.lo_frequency

    correction_as_dict = cast(
        MixerConfigType,
        {
            "intermediate_frequency": frequency,
            "lo_frequency": lo_frequency,
            "correction": _convert_matrix(correction.correction),
        },
    )
    return correction_as_dict


def _convert_mixers(mixers: Dict[str, QuaConfigMixerDec]) -> Dict[str, List[MixerConfigType]]:
    ret: Dict[str, List[MixerConfigType]] = {}
    for name, data in mixers.items():
        temp_list: List[MixerConfigType] = []
        for correction in data.correction:
            correction_as_dict = _convert_single_correction_entry(correction)
            temp_list.append(correction_as_dict)

        ret[name] = temp_list
    return ret


def _convert_matrix(matrix: QuaConfigMatrix) -> Tuple[Number, Number, Number, Number]:
    return matrix.v00, matrix.v01, matrix.v10, matrix.v11


def _convert_integration_weights(
    integration_weights: Dict[str, QuaConfigIntegrationWeightDec]
) -> Dict[str, IntegrationWeightConfigType]:
    ret: Dict[str, IntegrationWeightConfigType] = {}
    for name, data in integration_weights.items():
        tmp: IntegrationWeightConfigType = {
            "cosine": [(s.value, s.length) for s in data.cosine],
            "sine": [(s.value, s.length) for s in data.sine],
        }
        ret[name] = tmp
    return ret


def _convert_digital_wave_forms(
    digital_wave_forms: Dict[str, QuaConfigDigitalWaveformDec]
) -> Dict[str, DigitalWaveformConfigType]:
    ret: Dict[str, DigitalWaveformConfigType] = {}
    for name, data in digital_wave_forms.items():
        temp_list: List[Tuple[int, int]] = []
        for sample in data.samples:
            value = int(bool(sample.value))
            temp_list.append((value, sample.length))

        ret[name] = {"samples": temp_list}
    return ret


def _convert_wave_forms(
    wave_forms: Dict[str, QuaConfigWaveformDec]
) -> Dict[str, Union[ArbitraryWaveformConfigType, ConstantWaveformConfigType, WaveformArrayConfigType]]:

    ret: Dict[str, Union[ArbitraryWaveformConfigType, ConstantWaveformConfigType, WaveformArrayConfigType]] = {}
    for name, data in wave_forms.items():
        key_name, curr_waveform = betterproto.which_one_of(data, "waveform_oneof")
        if isinstance(curr_waveform, QuaConfigArbitraryWaveformDec):
            arbitrary_waveform_dict: ArbitraryWaveformConfigType = {
                "type": "arbitrary",
                "samples": curr_waveform.samples,
                "is_overridable": curr_waveform.is_overridable,
            }
            if isinstance(curr_waveform.max_allowed_error, float):
                arbitrary_waveform_dict["max_allowed_error"] = curr_waveform.max_allowed_error
            if isinstance(curr_waveform.sampling_rate, float):
                arbitrary_waveform_dict["sampling_rate"] = curr_waveform.sampling_rate
            ret[name] = arbitrary_waveform_dict

        elif isinstance(curr_waveform, QuaConfigConstantWaveformDec):
            constant_waveform_dict: ConstantWaveformConfigType = {
                "type": "constant",
                "sample": curr_waveform.sample,
            }
            ret[name] = constant_waveform_dict

        elif isinstance(curr_waveform, QuaConfigWaveformArrayDec):
            waveform_array_dict: WaveformArrayConfigType = {
                "type": "array",
                "samples_array": [waveform_samples.samples for waveform_samples in curr_waveform.samples_array],
            }
            ret[name] = waveform_array_dict

        else:
            raise Exception(f"Unknown waveform type - {key_name}")

    return ret


def _convert_pulses(pulses: Dict[str, QuaConfigPulseDec]) -> Dict[str, PulseConfigType]:
    ret = {}
    for name, data in pulses.items():
        temp_dict: PulseConfigType = {
            "length": data.length,
            "waveforms": cast(Union[SingleWaveformConfigType, MixWaveformConfigType], data.waveforms),
            "integration_weights": data.integration_weights,
            "operation": cast(
                Literal["measurement", "control"],
                QuaConfigPulseDecOperation(data.operation).name.lower(),  # type: ignore[union-attr]
            ),
        }
        if isinstance(data.digital_marker, str):
            temp_dict["digital_marker"] = data.digital_marker
        ret[name] = temp_dict
    return ret


def _convert_controller(data: QuaConfigControllerDec) -> ControllerConfigType:
    return {
        "type": cast(Literal["opx", "opx1"], data.type),
        "analog_outputs": _convert_controller_analog_outputs(data.analog_outputs),
        "analog_inputs": _convert_controller_analog_inputs(data.analog_inputs),
        "digital_outputs": _convert_controller_digital_outputs(data.digital_outputs),
        "digital_inputs": _convert_controller_digital_inputs(data.digital_inputs),
    }


def _convert_controller_types(
    controllers: Dict[str, QuaConfigDeviceDec]
) -> Dict[str, Union[ControllerConfigType, OPX1000ControllerConfigType]]:
    ret: Dict[str, Union[ControllerConfigType, OPX1000ControllerConfigType]] = {}
    for name, data in controllers.items():
        if len(data.fems) == 1 and 1 in data.fems:
            _, opx = betterproto.which_one_of(data.fems[1], "fem_type_one_of")
            if isinstance(opx, QuaConfigControllerDec):
                ret[name] = _convert_controller(opx)
                continue

        to_attach: OPX1000ControllerConfigType = {
            "type": "opx1000",
            "fems": {cast(FEM_IDX, fem_idx): _convert_fem(fem) for fem_idx, fem in data.fems.items()},
        }
        ret[name] = to_attach

    return ret


def _convert_fem(data: QuaConfigFemTypes) -> Union[LfFemConfigType, MwFemConfigType]:
    _, fem_config = betterproto.which_one_of(data, "fem_type_one_of")
    if isinstance(fem_config, QuaConfigOctoDacFemDec):
        return _convert_octo_dac(fem_config)
    elif isinstance(fem_config, QuaConfigMicrowaveFemDec):
        return _convert_mw_fem(fem_config)
    else:
        raise ValueError(f"Unknown FEM type - {fem_config}")


def _convert_mw_fem(data: QuaConfigMicrowaveFemDec) -> MwFemConfigType:
    ret: MwFemConfigType = {"type": "MW"}
    if data.analog_outputs:
        ret["analog_outputs"] = _convert_mw_analog_outputs(data.analog_outputs)
    if data.analog_inputs:
        ret["analog_inputs"] = _convert_mw_analog_inputs(data.analog_inputs)
    if data.digital_outputs:
        ret["digital_outputs"] = _convert_controller_digital_outputs(data.digital_outputs)
    if data.digital_inputs:
        ret["digital_inputs"] = _convert_controller_digital_inputs(data.digital_inputs)
    return ret


def _convert_single_mw_analog_output(
    data: QuaConfigMicrowaveAnalogOutputPortDec, capabilities: ServerCapabilities
) -> MwFemAnalogOutputPortConfigType:
    upconverters = data.upconverters_v2.value if capabilities.supports(QopCaps.config_v2) else data.upconverters

    ret = cast(
        MwFemAnalogOutputPortConfigType,
        {
            "sampling_rate": data.sampling_rate,
            "full_scale_power_dbm": data.full_scale_power_dbm,
            "band": cast(Band, data.band),
            "delay": data.delay,
            "shareable": data.shareable,
            "upconverters": {cast(Upconverter, k): {"frequency": v.frequency} for k, v in upconverters.items()},
        },
    )
    return ret


@inject
def _convert_mw_analog_outputs(
    outputs: Dict[int, QuaConfigMicrowaveAnalogOutputPortDec],
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> Mapping[Union[int, str], MwFemAnalogOutputPortConfigType]:
    return {idx: _convert_single_mw_analog_output(output, capabilities) for idx, output in outputs.items()}


def _convert_single_mw_analog_input(data: QuaConfigMicrowaveAnalogInputPortDec) -> MwFemAnalogInputPortConfigType:
    return cast(
        MwFemAnalogInputPortConfigType,
        {
            "band": cast(Literal[1, 3, 3], data.band),
            "shareable": data.shareable,
            "gain_db": data.gain_db,
            "sampling_rate": data.sampling_rate,
            "downconverter_frequency": data.downconverter.frequency,
        },
    )


def _convert_mw_analog_inputs(
    inputs: Dict[int, QuaConfigMicrowaveAnalogInputPortDec]
) -> Mapping[Union[int, str], MwFemAnalogInputPortConfigType]:
    return {idx: _convert_single_mw_analog_input(_input) for idx, _input in inputs.items()}


def _convert_octo_dac(data: QuaConfigOctoDacFemDec) -> LfFemConfigType:
    ret: LfFemConfigType = {"type": "LF"}
    if data.analog_outputs:
        ret["analog_outputs"] = _convert_octo_dac_fem_analog_outputs(data.analog_outputs)
    if data.analog_inputs:
        ret["analog_inputs"] = _convert_controller_analog_inputs(data.analog_inputs)
    if data.digital_outputs:
        ret["digital_outputs"] = _convert_controller_digital_outputs(data.digital_outputs)
    if data.digital_inputs:
        ret["digital_inputs"] = _convert_controller_digital_inputs(data.digital_inputs)
    return ret


def _convert_inputs(inputs: Dict[str, QuaConfigDigitalInputPortReference]) -> Dict[str, DigitalInputConfigType]:
    ret: Dict[str, DigitalInputConfigType] = {}
    for name, data in inputs.items():
        ret[name] = {"delay": data.delay, "buffer": data.buffer, "port": _port_reference(data.port)}
    return ret


def _convert_digital_output(outputs: Dict[str, QuaConfigDigitalOutputPortReference]) -> Dict[str, PortReferenceType]:
    ret = {}
    for name, data in outputs.items():
        ret[name] = _port_reference(data.port)

    return ret


def _convert_single_input_collection(data: QuaConfigSingleInputCollection) -> InputCollectionConfigType:
    temp = {}
    for name, input_info in data.inputs.items():
        temp[name] = _port_reference(input_info)

    res: InputCollectionConfigType = {"inputs": temp}
    return res


def _convert_multiple_inputs(data: QuaConfigMultipleInputs) -> InputCollectionConfigType:
    temp = {}
    for name, input_info in data.inputs.items():
        temp[name] = _port_reference(input_info)

    res: InputCollectionConfigType = {"inputs": temp}
    return res


def _convert_oscillators(oscillator: Dict[str, QuaConfigOscillator]) -> Dict[str, OscillatorConfigType]:
    ret: Dict[str, OscillatorConfigType] = {}
    for name, data in oscillator.items():
        oscillator_config_data: OscillatorConfigType = {}
        if data.intermediate_frequency_double:
            freq = data.intermediate_frequency_double
            oscillator_config_data["intermediate_frequency"] = freq
        elif data.intermediate_frequency:
            freq = int(data.intermediate_frequency)
            oscillator_config_data["intermediate_frequency"] = freq
        if betterproto.serialized_on_wire(data.mixer):
            if data.mixer.mixer:
                oscillator_config_data["mixer"] = data.mixer.mixer
            if data.mixer.lo_frequency_double:
                lo_freq = data.mixer.lo_frequency_double
                oscillator_config_data["lo_frequency"] = float(lo_freq)
            elif data.mixer.lo_frequency:
                lo_freq = data.mixer.lo_frequency
                oscillator_config_data["lo_frequency"] = int(lo_freq)
        ret[name] = oscillator_config_data
    return ret


def _convert_elements(elements: Dict[str, QuaConfigElementDec]) -> Dict[str, ElementConfigType]:
    ret: Dict[str, ElementConfigType] = {}
    for name, data in elements.items():
        element_output = betterproto.which_one_of(data, "element_outputs_one_of")[1]
        assert (
            isinstance(element_output, (QuaConfigMultipleOutputs, QuaConfigMicrowaveOutputPortReference))
            or element_output is None
        )
        element_config_data: ElementConfigType = {
            "digitalInputs": _convert_inputs(data.digital_inputs),
            "digitalOutputs": _convert_digital_output(data.digital_outputs),
            "outputs": _convert_element_output(data.outputs, element_output),
            "operations": data.operations,
            "hold_offset": _convert_hold_offset(data.hold_offset),
            "sticky": _convert_sticky(data.sticky),
        }
        if betterproto.serialized_on_wire(data.thread):
            element_config_data["core"] = _convert_element_thread(data.thread)
        if betterproto.serialized_on_wire(data.output_pulse_parameters):
            element_config_data["timeTaggingParameters"] = _convert_time_tagging_params(data.output_pulse_parameters)
        input_value = betterproto.which_one_of(data, "element_inputs_one_of")[1]
        if isinstance(input_value, QuaConfigSingleInput):
            element_config_data["singleInput"] = _convert_single_inputs(input_value)
        elif isinstance(input_value, QuaConfigMixInputs):
            element_config_data["mixInputs"] = _convert_mix_inputs(input_value)
        elif isinstance(input_value, QuaConfigSingleInputCollection):
            element_config_data["singleInputCollection"] = _convert_single_input_collection(input_value)
        elif isinstance(input_value, QuaConfigMultipleInputs):
            element_config_data["multipleInputs"] = _convert_multiple_inputs(input_value)
        elif isinstance(input_value, QuaConfigMicrowaveInputPortReference):
            element_config_data["MWInput"] = _convert_element_mw_input(input_value)

        output_value = betterproto.which_one_of(data, "element_outputs_one_of")[1]
        if isinstance(output_value, QuaConfigMicrowaveOutputPortReference):
            element_config_data["MWOutput"] = _convert_element_mw_output(output_value)

        if data.smearing is not None:
            element_config_data["smearing"] = data.smearing
        if data.time_of_flight is not None:
            element_config_data["time_of_flight"] = data.time_of_flight
        if data.measurement_qe:
            element_config_data["measurement_qe"] = data.measurement_qe

        oscillator_key, oscillator = betterproto.which_one_of(data, "oscillator_one_of")
        if oscillator_key == "named_oscillator":
            assert isinstance(oscillator, str)
            element_config_data["oscillator"] = oscillator
        else:
            sign = (-1) ** data.intermediate_frequency_negative
            if data.intermediate_frequency_double:
                element_config_data["intermediate_frequency"] = abs(data.intermediate_frequency_double) * sign
            elif data.intermediate_frequency is not None:
                element_config_data["intermediate_frequency"] = abs(data.intermediate_frequency) * sign

        ret[name] = element_config_data

    return ret


def _convert_polarity(polarity: QuaConfigOutputPulseParametersPolarity) -> Literal["ABOVE", "BELOW"]:
    if polarity == QuaConfigOutputPulseParametersPolarity.ASCENDING:
        return "ABOVE"
    if polarity == QuaConfigOutputPulseParametersPolarity.DESCENDING:
        return "BELOW"
    raise ValueError(f"Unknown polarity - {polarity}")


def _convert_time_tagging_params(data: QuaConfigOutputPulseParameters) -> TimeTaggingParametersConfigType:
    to_return: TimeTaggingParametersConfigType = {
        "signalThreshold": data.signal_threshold,
        "signalPolarity": _convert_polarity(data.signal_polarity),
        "derivativeThreshold": data.derivative_threshold,
        "derivativePolarity": _convert_polarity(data.derivative_polarity),
    }
    return to_return


def _convert_mix_inputs(mix_inputs: QuaConfigMixInputs) -> MixInputConfigType:
    res: MixInputConfigType = {"I": _port_reference(mix_inputs.i), "Q": _port_reference(mix_inputs.q)}

    mixer = mix_inputs.mixer
    if mixer is not None:
        res["mixer"] = mixer

    if mix_inputs.lo_frequency_double:
        res["lo_frequency"] = mix_inputs.lo_frequency_double
    else:
        res["lo_frequency"] = float(mix_inputs.lo_frequency)

    return res


def _convert_single_inputs(single: QuaConfigSingleInput) -> SingleInputConfigType:
    return {"port": _port_reference(single.port)}


def _convert_hold_offset(hold_offset: QuaConfigHoldOffset) -> HoldOffsetConfigType:
    return {"duration": hold_offset.duration}


def _convert_sticky(sticky: QuaConfigSticky) -> StickyConfigType:
    res: StickyConfigType = {
        "analog": sticky.analog,
        "digital": sticky.digital,
        "duration": max(sticky.duration, 1) * 4,
    }
    return res


def _convert_element_mw_input(data: QuaConfigMicrowaveInputPortReference) -> MwInputConfigType:
    return {
        "port": _port_reference(data.port),
        "upconverter": cast(Upconverter, data.upconverter),
    }


def _convert_element_mw_output(data: QuaConfigMicrowaveOutputPortReference) -> MwOutputConfigType:
    return {
        "port": _port_reference(data.port),
    }


def _convert_element_thread(element_thread: QuaConfigElementThread) -> str:
    return element_thread.thread_name


@inject
def _convert_analog_output_filters(
    data: QuaConfigAnalogOutputPortFilter,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> Union[AnalogOutputFilterConfigTypeQop35, AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigType]:
    if capabilities.supports(QopCaps.exponential_iir_filter):
        raw_exponential = (
            data.iir.exponential_v2.value if capabilities.supports(QopCaps.config_v2) else data.iir.exponential
        )
        exponential = [(exp_params.amplitude, exp_params.time_constant) for exp_params in raw_exponential]
        feedforward = data.feedforward_v2.value if capabilities.supports(QopCaps.config_v2) else data.feedforward

        ret33: AnalogOutputFilterConfigTypeQop33 = {"feedforward": feedforward, "exponential": exponential}

        if capabilities.supports(QopCaps.config_v2):
            # We handle both cases: the container being None (as likely returned by the Gateway),
            # and an initialized container with value=None.
            ret33["high_pass"] = data.iir.high_pass_v2.value if data.iir.high_pass_v2 else None
        else:
            ret33["high_pass"] = data.iir.high_pass

        if capabilities.supports(QopCaps.exponential_dc_gain_filter):
            exponential_dc_gain = data.iir.exponential_dc_gain.value if data.iir.exponential_dc_gain else None
            ret35 = cast(AnalogOutputFilterConfigTypeQop35, {**ret33, "exponential_dc_gain": exponential_dc_gain})
            return ret35

        return ret33
    else:
        ret: AnalogOutputFilterConfigType = {"feedforward": data.feedforward, "feedback": data.feedback}
        return ret


def _convert_single_analog_output(data: QuaConfigAnalogOutputPortDec) -> AnalogOutputPortConfigType:
    ret = cast(
        AnalogOutputPortConfigType,
        {
            "offset": data.offset,
            "delay": data.delay,
            "shareable": data.shareable,
            "filter": _convert_analog_output_filters(data.filter),
            "crosstalk": data.crosstalk,
        },
    )
    return ret


def _convert_controller_analog_outputs(
    outputs: Dict[int, QuaConfigAnalogOutputPortDec]
) -> Mapping[Union[int, str], AnalogOutputPortConfigType]:
    ret: Mapping[Union[int, str], AnalogOutputPortConfigType] = {
        int(name): _convert_single_analog_output(data) for name, data in outputs.items()
    }
    return ret


def _convert_single_octo_dac_fem_analog_output(
    data: QuaConfigOctoDacAnalogOutputPortDec,
    capabilities: ServerCapabilities,
) -> AnalogOutputPortConfigTypeOctoDac:
    ret = cast(
        AnalogOutputPortConfigTypeOctoDac,
        {
            "offset": data.offset,
            "delay": data.delay,
            "shareable": data.shareable,
            "filter": _convert_analog_output_filters(data.filter),
            "crosstalk": data.crosstalk_v2.value if capabilities.supports(QopCaps.config_v2) else data.crosstalk,
        },
    )
    if data.sampling_rate:
        ret["sampling_rate"] = {1: 1e9, 2: 2e9}[data.sampling_rate]
    if data.upsampling_mode:
        ret["upsampling_mode"] = cast(
            Literal["mw", "pulse"], QuaConfigOctoDacAnalogOutputPortDecSamplingRateMode(data.upsampling_mode).name
        )
    if data.output_mode is not None:  # We check for "is not None" because the 0 value is valid
        ret["output_mode"] = cast(
            Literal["direct", "amplified"], QuaConfigOctoDacAnalogOutputPortDecOutputMode(data.output_mode).name
        )
    return ret


@inject
def _convert_octo_dac_fem_analog_outputs(
    outputs: Dict[int, QuaConfigOctoDacAnalogOutputPortDec],
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> Mapping[Union[int, str], AnalogOutputPortConfigTypeOctoDac]:
    ret: Mapping[Union[int, str], AnalogOutputPortConfigTypeOctoDac] = {
        int(name): _convert_single_octo_dac_fem_analog_output(data, capabilities) for name, data in outputs.items()
    }
    return ret


def _convert_controller_analog_input(data: QuaConfigAnalogInputPortDec) -> AnalogInputPortConfigType:
    ret = cast(
        AnalogInputPortConfigType,
        {
            "offset": data.offset,
            "gain_db": data.gain_db if data.gain_db is not None else 0,
            "shareable": data.shareable,
            "sampling_rate": 1e9,  # The only allowed value (the get_config always returns 0, but we know it is 1e9)
        },
    )
    return ret


def _convert_controller_analog_inputs(
    inputs: Mapping[int, QuaConfigAnalogInputPortDec]
) -> Mapping[Union[int, str], AnalogInputPortConfigType]:
    ret: Mapping[Union[int, str], AnalogInputPortConfigType] = {
        idx: _convert_controller_analog_input(data) for idx, data in inputs.items()
    }
    return ret


def _convert_controller_digital_outputs(
    outputs: Dict[int, QuaConfigDigitalOutputPortDec]
) -> Mapping[Union[int, str], DigitalOutputPortConfigType]:
    return {idx: _convert_controller_digital_output(data) for idx, data in outputs.items()}


def _convert_controller_digital_output(data: QuaConfigDigitalOutputPortDec) -> DigitalOutputPortConfigType:
    to_return = cast(
        DigitalOutputPortConfigType,
        {
            "shareable": data.shareable,
            "inverted": data.inverted,
        },
    )
    return to_return


def _convert_digital_input(data: QuaConfigDigitalInputPortDec) -> DigitalInputPortConfigType:
    to_return = cast(
        DigitalInputPortConfigType,
        {
            "deadtime": data.deadtime,
            "threshold": data.threshold,
            "shareable": data.shareable,
        },
    )
    if data.polarity is not None:
        to_return["polarity"] = cast(
            Literal["RISING", "FALLING"], QuaConfigDigitalInputPortDecPolarity(data.polarity).name
        )

    return to_return


def _convert_controller_digital_inputs(
    inputs: Dict[int, QuaConfigDigitalInputPortDec]
) -> Mapping[Union[int, str], DigitalInputPortConfigType]:
    return {idx: _convert_digital_input(data) for idx, data in inputs.items()}


def _convert_element_output(
    outputs: Dict[str, QuaConfigAdcPortReference],
    multiple_outputs: Optional[Union[QuaConfigMultipleOutputs, QuaConfigMicrowaveOutputPortReference]],
) -> Dict[str, PortReferenceType]:
    if isinstance(multiple_outputs, QuaConfigMultipleOutputs):
        return {name: _port_reference(data) for name, data in multiple_outputs.port_references.items()}
    return {name: _port_reference(data) for name, data in outputs.items()}


def _port_reference(
    data: Union[QuaConfigAdcPortReference, QuaConfigDacPortReference, QuaConfigPortReference]
) -> PortReferenceType:
    if data.fem:
        return data.controller, data.fem, data.number
    else:
        return data.controller, data.number
