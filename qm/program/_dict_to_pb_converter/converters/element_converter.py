import warnings
from typing import Union, Literal, Mapping, Optional, cast

import betterproto
from betterproto.lib.std.google.protobuf import Empty

from qm.utils import deprecation_message
from qm.exceptions import ConfigValidationException
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter
from qm.program._dict_to_pb_converter.converters.octave_converter import (
    dac_port_ref_to_pb,
    _get_port_reference_with_fem,
)
from qm.program._validate_config_schema import (
    validate_oscillator,
    validate_output_tof,
    validate_used_inputs,
    validate_output_smearing,
    validate_sticky_duration,
)
from qm.type_hinting.config_types import (
    Upconverter,
    StickyConfigType,
    ElementConfigType,
    MwInputConfigType,
    PortReferenceType,
    MixInputConfigType,
    MwOutputConfigType,
    HoldOffsetConfigType,
    SingleInputConfigType,
    DigitalInputConfigType,
    InputCollectionConfigType,
    MwFemAnalogInputPortConfigType,
    TimeTaggingParametersConfigType,
)
from qm.grpc.qua_config import (
    QuaConfigSticky,
    QuaConfigMixInputs,
    QuaConfigElementDec,
    QuaConfigHoldOffset,
    QuaConfigSingleInput,
    QuaConfigElementThread,
    QuaConfigPortReference,
    QuaConfigMultipleInputs,
    QuaConfigMultipleOutputs,
    QuaConfigAdcPortReference,
    QuaConfigDacPortReference,
    QuaConfigGeneralPortReference,
    QuaConfigOutputPulseParameters,
    QuaConfigSingleInputCollection,
    QuaConfigDigitalInputPortReference,
    QuaConfigDigitalOutputPortReference,
    QuaConfigMicrowaveAnalogInputPortDec,
    QuaConfigMicrowaveInputPortReference,
    QuaConfigMicrowaveOutputPortReference,
    QuaConfigOutputPulseParametersPolarity,
)

DEFAULT_DUC_IDX = 1


class StickyElementIsNotSupported(ConfigValidationException):
    pass


class ElementConverter(BaseDictToPbConverter[ElementConfigType, QuaConfigElementDec]):
    def convert(self, input_data: ElementConfigType) -> QuaConfigElementDec:
        return self.element_to_pb(input_data)

    def element_to_pb(
        self,
        data: ElementConfigType,
    ) -> QuaConfigElementDec:
        validate_oscillator(data)
        validate_output_smearing(data)
        validate_output_tof(data)
        validate_used_inputs(data)

        element = QuaConfigElementDec()

        if "time_of_flight" in data:
            element.time_of_flight = int(data["time_of_flight"])

        if "smearing" in data:
            element.smearing = int(data["smearing"])

        if "intermediate_frequency" in data:
            element.intermediate_frequency = abs(int(data["intermediate_frequency"]))
            element.intermediate_frequency_oscillator = int(data["intermediate_frequency"])
            if self._capabilities.supports_double_frequency:
                element.intermediate_frequency_double = abs(float(data["intermediate_frequency"]))
                element.intermediate_frequency_oscillator_double = float(data["intermediate_frequency"])

            element.intermediate_frequency_negative = data["intermediate_frequency"] < 0

        if "thread" in data:
            warnings.warn(
                deprecation_message("thread", "1.2.0", "1.3.0", "Use 'core' instead"),
                DeprecationWarning,
            )
            element.thread = element_thread_to_pb(data["thread"])
        if "core" in data:
            element.thread = element_thread_to_pb(data["core"])

        if "outputs" in data:
            for k, v in data["outputs"].items():
                element.outputs[k] = adc_port_ref_to_pb(*_get_port_reference_with_fem(v))
            element.multiple_outputs = QuaConfigMultipleOutputs(port_references=element.outputs)

        if "digitalInputs" in data:
            for digital_input_k, digital_input_v in data["digitalInputs"].items():
                element.digital_inputs[digital_input_k] = digital_input_port_ref_to_pb(digital_input_v)

        if "digitalOutputs" in data:
            for digital_output_k, digital_output_v in data["digitalOutputs"].items():
                element.digital_outputs[digital_output_k] = digital_output_port_ref_to_pb(digital_output_v)

        if "operations" in data:
            for op_name, op_value in data["operations"].items():
                element.operations[op_name] = op_value

        if "singleInput" in data:
            port_ref = _get_port_reference_with_fem(data["singleInput"]["port"])
            element.single_input = single_input_to_pb(*port_ref)

        if "mixInputs" in data:
            mix_inputs = data["mixInputs"]
            element.mix_inputs = QuaConfigMixInputs(
                i=dac_port_ref_to_pb(*_get_port_reference_with_fem(mix_inputs["I"])),
                q=dac_port_ref_to_pb(*_get_port_reference_with_fem(mix_inputs["Q"])),
                mixer=mix_inputs.get("mixer", ""),
            )

            lo_frequency = mix_inputs.get("lo_frequency", 0)
            element.mix_inputs.lo_frequency = int(lo_frequency)
            if self._capabilities.supports_double_frequency:
                element.mix_inputs.lo_frequency_double = float(lo_frequency)

        if "singleInputCollection" in data:
            element.single_input_collection = QuaConfigSingleInputCollection(
                inputs={
                    k: dac_port_ref_to_pb(*_get_port_reference_with_fem(v))
                    for k, v in data["singleInputCollection"]["inputs"].items()
                }
            )

        if "multipleInputs" in data:
            element.multiple_inputs = QuaConfigMultipleInputs(
                inputs={
                    k: dac_port_ref_to_pb(*_get_port_reference_with_fem(v))
                    for k, v in data["multipleInputs"]["inputs"].items()
                }
            )

        if "MWInput" in data:
            element.microwave_input = QuaConfigMicrowaveInputPortReference(
                port=dac_port_ref_to_pb(*_get_port_reference_with_fem(data["MWInput"]["port"])),
                upconverter=data["MWInput"].get("upconverter", DEFAULT_DUC_IDX),
            )
        if "MWOutput" in data:
            mw_output = data["MWOutput"]
            element.microwave_output = QuaConfigMicrowaveOutputPortReference(
                port=adc_port_ref_to_pb(*_get_port_reference_with_fem(mw_output["port"])),
            )

        if "oscillator" in data:
            element.named_oscillator = data["oscillator"]
        elif "intermediate_frequency" not in data:
            element.no_oscillator = Empty()

        if "sticky" in data:
            if "duration" in data["sticky"]:
                validate_sticky_duration(data["sticky"]["duration"])
            if self._capabilities.supports_sticky_elements:
                element.sticky = QuaConfigSticky(
                    analog=data["sticky"].get("analog", True),
                    digital=data["sticky"].get("digital", False),
                    duration=int(data["sticky"].get("duration", 4) / 4),
                )
            else:
                if "digital" in data["sticky"] and data["sticky"]["digital"]:
                    raise StickyElementIsNotSupported("Not supported")
                element.hold_offset = QuaConfigHoldOffset(duration=int(data["sticky"].get("duration", 4) / 4))

        elif "hold_offset" in data:
            if self._capabilities.supports_sticky_elements:
                element.sticky = QuaConfigSticky(
                    analog=True,
                    digital=False,
                    duration=data["hold_offset"].get("duration", 1),
                )
            else:
                element.hold_offset = QuaConfigHoldOffset(duration=data["hold_offset"]["duration"])

        if "outputPulseParameters" in data:
            warnings.warn(
                deprecation_message("outputPulseParameters", "1.2.0", "1.3.0", "Use timeTaggingParameters instead"),
                DeprecationWarning,
            )
            element.output_pulse_parameters = self.create_time_tagging_parameters(data["outputPulseParameters"])
        if "timeTaggingParameters" in data:
            element.output_pulse_parameters = self.create_time_tagging_parameters(data["timeTaggingParameters"])

        rf_inputs = data.get("RF_inputs", {})
        for k, (device, port) in rf_inputs.items():
            element.rf_inputs[k] = QuaConfigGeneralPortReference(device_name=device, port=port)

        rf_outputs = data.get("RF_outputs", {})
        for k, (device, port) in rf_outputs.items():
            element.rf_outputs[k] = QuaConfigGeneralPortReference(device_name=device, port=port)
        return element

    @staticmethod
    def create_time_tagging_parameters(data: TimeTaggingParametersConfigType) -> QuaConfigOutputPulseParameters:
        return QuaConfigOutputPulseParameters(
            signal_threshold=data["signalThreshold"],
            signal_polarity=ElementConverter._create_signal_polarity(data["signalPolarity"]),
            derivative_threshold=data["derivativeThreshold"],
            derivative_polarity=ElementConverter._create_signal_polarity(data["derivativePolarity"]),
        )

    @staticmethod
    def _create_signal_polarity(polarity: str) -> QuaConfigOutputPulseParametersPolarity:
        polarity = polarity.upper()
        if polarity in {"ABOVE", "ASCENDING"}:
            if polarity == "ASCENDING":
                warnings.warn(
                    deprecation_message("ASCENDING", "1.2.2", "1.3.0", "Use 'ABOVE' instead"), DeprecationWarning
                )
            return QuaConfigOutputPulseParametersPolarity.ASCENDING  # type: ignore[return-value]
        elif polarity in {"BELOW", "DESCENDING"}:
            if polarity == "DESCENDING":
                warnings.warn(
                    deprecation_message("DESCENDING", "1.2.2", "1.3.0", "Use 'BELOW' instead"), DeprecationWarning
                )
            return QuaConfigOutputPulseParametersPolarity.DESCENDING  # type: ignore[return-value]
        else:
            raise ConfigValidationException(f"Invalid signal polarity: {polarity}")

    def deconvert(self, output_data: QuaConfigElementDec) -> ElementConfigType:
        element_output = betterproto.which_one_of(output_data, "element_outputs_one_of")[1]
        assert (
            isinstance(element_output, (QuaConfigMultipleOutputs, QuaConfigMicrowaveOutputPortReference))
            or element_output is None
        )
        element_config_data: ElementConfigType = {
            "digitalInputs": _deconvert_inputs(output_data.digital_inputs),
            "digitalOutputs": _deconvert_digital_output(output_data.digital_outputs),
            "outputs": _deconvert_element_output(output_data.outputs, element_output),
            "operations": output_data.operations,
            "hold_offset": _deconvert_hold_offset(output_data.hold_offset),
            "sticky": _deconvert_sticky(output_data.sticky),
        }
        if betterproto.serialized_on_wire(output_data.thread):
            element_config_data["core"] = _deconvert_element_thread(output_data.thread)
        if betterproto.serialized_on_wire(output_data.output_pulse_parameters):
            element_config_data["timeTaggingParameters"] = _deconvert_time_tagging_params(
                output_data.output_pulse_parameters
            )
        input_value = betterproto.which_one_of(output_data, "element_inputs_one_of")[1]
        if isinstance(input_value, QuaConfigSingleInput):
            element_config_data["singleInput"] = _deconvert_single_inputs(input_value)
        elif isinstance(input_value, QuaConfigMixInputs):
            element_config_data["mixInputs"] = _deconvert_mix_inputs(input_value)
        elif isinstance(input_value, QuaConfigSingleInputCollection):
            element_config_data["singleInputCollection"] = _deconvert_single_input_collection(input_value)
        elif isinstance(input_value, QuaConfigMultipleInputs):
            element_config_data["multipleInputs"] = _deconvert_multiple_inputs(input_value)
        elif isinstance(input_value, QuaConfigMicrowaveInputPortReference):
            element_config_data["MWInput"] = _deconvert_element_mw_input(input_value)

        output_value = betterproto.which_one_of(output_data, "element_outputs_one_of")[1]
        if isinstance(output_value, QuaConfigMicrowaveOutputPortReference):
            element_config_data["MWOutput"] = _deconvert_element_mw_output(output_value)

        if output_data.smearing is not None:
            element_config_data["smearing"] = output_data.smearing
        if output_data.time_of_flight is not None:
            element_config_data["time_of_flight"] = output_data.time_of_flight
        if output_data.measurement_qe:
            element_config_data["measurement_qe"] = output_data.measurement_qe

        oscillator_key, oscillator = betterproto.which_one_of(output_data, "oscillator_one_of")
        if oscillator_key == "named_oscillator":
            assert isinstance(oscillator, str)
            element_config_data["oscillator"] = oscillator
        else:
            sign = (-1) ** output_data.intermediate_frequency_negative
            if output_data.intermediate_frequency_double:
                element_config_data["intermediate_frequency"] = abs(output_data.intermediate_frequency_double) * sign
            elif output_data.intermediate_frequency is not None:
                element_config_data["intermediate_frequency"] = abs(output_data.intermediate_frequency) * sign

        return element_config_data


def element_thread_to_pb(name: str) -> QuaConfigElementThread:
    return QuaConfigElementThread(thread_name=name)


def single_input_to_pb(controller: str, fem: int, number: int) -> QuaConfigSingleInput:
    return QuaConfigSingleInput(port=dac_port_ref_to_pb(controller, fem, number))


def adc_port_ref_to_pb(controller: str, fem: int, number: int) -> QuaConfigAdcPortReference:
    return QuaConfigAdcPortReference(controller=controller, fem=fem, number=number)


def port_ref_to_pb(controller: str, fem: int, number: int) -> QuaConfigPortReference:
    return QuaConfigPortReference(controller=controller, fem=fem, number=number)


def digital_input_port_ref_to_pb(data: DigitalInputConfigType) -> QuaConfigDigitalInputPortReference:
    digital_input = QuaConfigDigitalInputPortReference(
        delay=int(data["delay"]),
        buffer=int(data["buffer"]),
    )
    if "port" in data:
        digital_input.port = port_ref_to_pb(*_get_port_reference_with_fem(data["port"]))

    return digital_input


def digital_output_port_ref_to_pb(data: PortReferenceType) -> QuaConfigDigitalOutputPortReference:
    return QuaConfigDigitalOutputPortReference(port=port_ref_to_pb(*_get_port_reference_with_fem(data)))


def _deconvert_polarity(polarity: QuaConfigOutputPulseParametersPolarity) -> Literal["ABOVE", "BELOW"]:
    if polarity == QuaConfigOutputPulseParametersPolarity.ASCENDING:
        return "ABOVE"
    if polarity == QuaConfigOutputPulseParametersPolarity.DESCENDING:
        return "BELOW"
    raise ValueError(f"Unknown polarity - {polarity}")


def _deconvert_time_tagging_params(data: QuaConfigOutputPulseParameters) -> TimeTaggingParametersConfigType:
    to_return: TimeTaggingParametersConfigType = {
        "signalThreshold": data.signal_threshold,
        "signalPolarity": _deconvert_polarity(data.signal_polarity),
        "derivativeThreshold": data.derivative_threshold,
        "derivativePolarity": _deconvert_polarity(data.derivative_polarity),
    }
    return to_return


def _deconvert_mix_inputs(mix_inputs: QuaConfigMixInputs) -> MixInputConfigType:
    res: MixInputConfigType = {
        "I": _deconvert_port_reference(mix_inputs.i),
        "Q": _deconvert_port_reference(mix_inputs.q),
    }

    mixer = mix_inputs.mixer
    if mixer is not None:
        res["mixer"] = mixer

    if mix_inputs.lo_frequency_double:
        res["lo_frequency"] = mix_inputs.lo_frequency_double
    else:
        res["lo_frequency"] = float(mix_inputs.lo_frequency)

    return res


def _deconvert_single_inputs(single: QuaConfigSingleInput) -> SingleInputConfigType:
    return {"port": _deconvert_port_reference(single.port)}


def _deconvert_hold_offset(hold_offset: QuaConfigHoldOffset) -> HoldOffsetConfigType:
    return {"duration": hold_offset.duration}


def _deconvert_sticky(sticky: QuaConfigSticky) -> StickyConfigType:
    res: StickyConfigType = {
        "analog": sticky.analog,
        "digital": sticky.digital,
        "duration": max(sticky.duration, 1) * 4,
    }
    return res


def _deconvert_element_mw_input(data: QuaConfigMicrowaveInputPortReference) -> MwInputConfigType:
    return {
        "port": _deconvert_port_reference(data.port),
        "upconverter": cast(Upconverter, data.upconverter),
    }


def _deconvert_element_mw_output(data: QuaConfigMicrowaveOutputPortReference) -> MwOutputConfigType:
    return {
        "port": _deconvert_port_reference(data.port),
    }


def _deconvert_element_thread(element_thread: QuaConfigElementThread) -> str:
    return element_thread.thread_name


def _deconvert_port_reference(
    data: Union[QuaConfigAdcPortReference, QuaConfigDacPortReference, QuaConfigPortReference]
) -> PortReferenceType:
    if data.fem:
        return data.controller, data.fem, data.number
    else:
        return data.controller, data.number


def _deconvert_mw_analog_inputs(
    inputs: dict[int, QuaConfigMicrowaveAnalogInputPortDec]
) -> Mapping[Union[int, str], MwFemAnalogInputPortConfigType]:
    return {idx: _deconvert_single_mw_analog_input(_input) for idx, _input in inputs.items()}


def _deconvert_inputs(inputs: dict[str, QuaConfigDigitalInputPortReference]) -> dict[str, DigitalInputConfigType]:
    ret: dict[str, DigitalInputConfigType] = {}
    for name, data in inputs.items():
        ret[name] = {"delay": data.delay, "buffer": data.buffer, "port": _deconvert_port_reference(data.port)}
    return ret


def _deconvert_digital_output(outputs: dict[str, QuaConfigDigitalOutputPortReference]) -> dict[str, PortReferenceType]:
    ret = {}
    for name, data in outputs.items():
        ret[name] = _deconvert_port_reference(data.port)

    return ret


def _deconvert_single_input_collection(data: QuaConfigSingleInputCollection) -> InputCollectionConfigType:
    temp = {}
    for name, input_info in data.inputs.items():
        temp[name] = _deconvert_port_reference(input_info)

    res: InputCollectionConfigType = {"inputs": temp}
    return res


def _deconvert_multiple_inputs(data: QuaConfigMultipleInputs) -> InputCollectionConfigType:
    temp = {}
    for name, input_info in data.inputs.items():
        temp[name] = _deconvert_port_reference(input_info)

    res: InputCollectionConfigType = {"inputs": temp}
    return res


def _deconvert_single_mw_analog_input(data: QuaConfigMicrowaveAnalogInputPortDec) -> MwFemAnalogInputPortConfigType:
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


def _deconvert_element_output(
    outputs: dict[str, QuaConfigAdcPortReference],
    multiple_outputs: Optional[Union[QuaConfigMultipleOutputs, QuaConfigMicrowaveOutputPortReference]],
) -> dict[str, PortReferenceType]:
    if isinstance(multiple_outputs, QuaConfigMultipleOutputs):
        return {name: _deconvert_port_reference(data) for name, data in multiple_outputs.port_references.items()}
    return {name: _deconvert_port_reference(data) for name, data in outputs.items()}
