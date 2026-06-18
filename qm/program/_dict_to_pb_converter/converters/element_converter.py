import warnings
from typing import Union, Literal, Mapping, Optional, MutableMapping, cast

from google.protobuf.empty_pb2 import Empty

from qm.utils import deprecation_message
from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.exceptions import ConfigValidationException
from qm.utils.protobuf_utils import which_one_of, serialized_on_wire
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

DEFAULT_DUC_IDX = 1


class StickyElementIsNotSupported(ConfigValidationException):
    pass


class ElementConverter(BaseDictToPbConverter[ElementConfigType, inc_qua_config_pb2.QuaConfig.ElementDec]):
    def convert(self, input_data: ElementConfigType) -> inc_qua_config_pb2.QuaConfig.ElementDec:
        return self.element_to_pb(input_data)

    def element_to_pb(
        self,
        data: ElementConfigType,
    ) -> inc_qua_config_pb2.QuaConfig.ElementDec:
        validate_oscillator(data)
        validate_output_smearing(data)
        validate_output_tof(data)
        validate_used_inputs(data)

        element = inc_qua_config_pb2.QuaConfig.ElementDec()

        if "time_of_flight" in data:
            element.timeOfFlight.value = int(data["time_of_flight"])

        if "smearing" in data:
            element.smearing.value = int(data["smearing"])

        if "intermediate_frequency" in data:
            element.intermediateFrequency.value = abs(int(data["intermediate_frequency"]))
            element.intermediateFrequencyOscillator.value = int(data["intermediate_frequency"])
            if self._capabilities.supports_double_frequency:
                element.intermediateFrequencyDouble = abs(float(data["intermediate_frequency"]))
                element.intermediateFrequencyOscillatorDouble = float(data["intermediate_frequency"])

            element.intermediateFrequencyNegative = data["intermediate_frequency"] < 0

        if "thread" in data:
            warnings.warn(
                deprecation_message("thread", "1.2.0", "2.0.0", "Use 'core' instead"),
                DeprecationWarning,
            )
            element.thread.CopyFrom(element_thread_to_pb(data["thread"]))
        if "core" in data:
            element.thread.CopyFrom(element_thread_to_pb(data["core"]))

        if "outputs" in data:
            for k, v in data["outputs"].items():
                element.outputs[k].CopyFrom(adc_port_ref_to_pb(*_get_port_reference_with_fem(v)))
            element.multipleOutputs.CopyFrom(
                inc_qua_config_pb2.QuaConfig.MultipleOutputs(port_references=element.outputs)
            )

        if "digitalInputs" in data:
            for digital_input_k, digital_input_v in data["digitalInputs"].items():
                element.digitalInputs[digital_input_k].CopyFrom(digital_input_port_ref_to_pb(digital_input_v))

        if "digitalOutputs" in data:
            for digital_output_k, digital_output_v in data["digitalOutputs"].items():
                element.digitalOutputs[digital_output_k].CopyFrom(digital_output_port_ref_to_pb(digital_output_v))

        if "operations" in data:
            for op_name, op_value in data["operations"].items():
                element.operations[op_name] = op_value

        if "singleInput" in data:
            port_ref = _get_port_reference_with_fem(data["singleInput"]["port"])
            element.singleInput.CopyFrom(single_input_to_pb(*port_ref))

        if "mixInputs" in data:
            mix_inputs = data["mixInputs"]
            element.mixInputs.CopyFrom(
                inc_qua_config_pb2.QuaConfig.MixInputs(
                    I=dac_port_ref_to_pb(*_get_port_reference_with_fem(mix_inputs["I"])),
                    Q=dac_port_ref_to_pb(*_get_port_reference_with_fem(mix_inputs["Q"])),
                    mixer=mix_inputs.get("mixer", ""),
                )
            )

            lo_frequency = mix_inputs.get("lo_frequency", 0)
            element.mixInputs.loFrequency = int(lo_frequency)
            if self._capabilities.supports_double_frequency:
                element.mixInputs.loFrequencyDouble = float(lo_frequency)

        if "singleInputCollection" in data:
            element.singleInputCollection.CopyFrom(
                inc_qua_config_pb2.QuaConfig.SingleInputCollection(
                    inputs={
                        k: dac_port_ref_to_pb(*_get_port_reference_with_fem(v))
                        for k, v in data["singleInputCollection"]["inputs"].items()
                    }
                )
            )

        if "multipleInputs" in data:
            element.multipleInputs.CopyFrom(
                inc_qua_config_pb2.QuaConfig.MultipleInputs(
                    inputs={
                        k: dac_port_ref_to_pb(*_get_port_reference_with_fem(v))
                        for k, v in data["multipleInputs"]["inputs"].items()
                    }
                )
            )

        if "MWInput" in data:
            element.microwaveInput.CopyFrom(
                inc_qua_config_pb2.QuaConfig.MicrowaveInputPortReference(
                    port=dac_port_ref_to_pb(*_get_port_reference_with_fem(data["MWInput"]["port"])),
                    upconverter=data["MWInput"].get("upconverter", DEFAULT_DUC_IDX),
                )
            )
        if "MWOutput" in data:
            mw_output = data["MWOutput"]
            element.microwaveOutput.CopyFrom(
                inc_qua_config_pb2.QuaConfig.MicrowaveOutputPortReference(
                    port=adc_port_ref_to_pb(*_get_port_reference_with_fem(mw_output["port"])),
                )
            )

        if "oscillator" in data:
            element.namedOscillator.value = data["oscillator"]
        elif "intermediate_frequency" not in data:
            element.noOscillator.CopyFrom(Empty())

        if "sticky" in data:
            if "duration" in data["sticky"]:
                validate_sticky_duration(data["sticky"]["duration"])
            if self._capabilities.supports_sticky_elements:
                element.sticky.CopyFrom(
                    inc_qua_config_pb2.QuaConfig.Sticky(
                        analog=data["sticky"].get("analog", True),
                        digital=data["sticky"].get("digital", False),
                        duration=int(data["sticky"].get("duration", 4) / 4),
                    )
                )
            else:
                if "digital" in data["sticky"] and data["sticky"]["digital"]:
                    raise StickyElementIsNotSupported("Not supported")
                element.holdOffset.CopyFrom(
                    inc_qua_config_pb2.QuaConfig.HoldOffset(duration=int(data["sticky"].get("duration", 4) / 4))
                )

        elif "hold_offset" in data:
            if self._capabilities.supports_sticky_elements:
                element.sticky.CopyFrom(
                    inc_qua_config_pb2.QuaConfig.Sticky(
                        analog=True,
                        digital=False,
                        duration=data["hold_offset"].get("duration", 1),
                    )
                )
            else:
                element.holdOffset.CopyFrom(
                    inc_qua_config_pb2.QuaConfig.HoldOffset(duration=data["hold_offset"]["duration"])
                )

        if "outputPulseParameters" in data:
            warnings.warn(
                deprecation_message("outputPulseParameters", "1.2.0", "2.0.0", "Use timeTaggingParameters instead"),
                DeprecationWarning,
            )
            element.outputPulseParameters.CopyFrom(self.create_time_tagging_parameters(data["outputPulseParameters"]))
        if "timeTaggingParameters" in data:
            element.outputPulseParameters.CopyFrom(self.create_time_tagging_parameters(data["timeTaggingParameters"]))

        rf_inputs = data.get("RF_inputs", {})
        for k, (device, port) in rf_inputs.items():
            element.RFInputs[k].CopyFrom(
                inc_qua_config_pb2.QuaConfig.GeneralPortReference(device_name=device, port=port)
            )

        rf_outputs = data.get("RF_outputs", {})
        for k, (device, port) in rf_outputs.items():
            element.RFOutputs[k].CopyFrom(
                inc_qua_config_pb2.QuaConfig.GeneralPortReference(device_name=device, port=port)
            )
        return element

    @staticmethod
    def create_time_tagging_parameters(
        data: TimeTaggingParametersConfigType,
    ) -> inc_qua_config_pb2.QuaConfig.OutputPulseParameters:
        return inc_qua_config_pb2.QuaConfig.OutputPulseParameters(
            signalThreshold=data["signalThreshold"],
            signalPolarity=ElementConverter._create_signal_polarity(data["signalPolarity"]),
            derivativeThreshold=data["derivativeThreshold"],
            derivativePolarity=ElementConverter._create_signal_polarity(data["derivativePolarity"]),
        )

    @staticmethod
    def _create_signal_polarity(polarity: str) -> inc_qua_config_pb2.QuaConfig.OutputPulseParameters.Polarity:
        polarity = polarity.upper()
        if polarity in {"ABOVE", "ASCENDING"}:
            if polarity == "ASCENDING":
                warnings.warn(
                    deprecation_message("ASCENDING", "1.2.2", "2.0.0", "Use 'ABOVE' instead"), DeprecationWarning
                )
            return inc_qua_config_pb2.QuaConfig.OutputPulseParameters.Polarity.ASCENDING
        elif polarity in {"BELOW", "DESCENDING"}:
            if polarity == "DESCENDING":
                warnings.warn(
                    deprecation_message("DESCENDING", "1.2.2", "2.0.0", "Use 'BELOW' instead"), DeprecationWarning
                )
            return inc_qua_config_pb2.QuaConfig.OutputPulseParameters.Polarity.DESCENDING
        else:
            raise ConfigValidationException(f"Invalid signal polarity: {polarity}")

    def deconvert(self, output_data: inc_qua_config_pb2.QuaConfig.ElementDec) -> ElementConfigType:
        element_output = which_one_of(output_data, "element_outputs_one_of")[1]
        assert (
            isinstance(
                element_output,
                (
                    inc_qua_config_pb2.QuaConfig.MultipleOutputs,
                    inc_qua_config_pb2.QuaConfig.MicrowaveOutputPortReference,
                ),
            )
            or element_output is None
        )
        element_config_data: ElementConfigType = {
            "digitalInputs": _deconvert_inputs(output_data.digitalInputs),
            "digitalOutputs": _deconvert_digital_output(output_data.digitalOutputs),
            "outputs": _deconvert_element_output(output_data.outputs, element_output),
            "operations": output_data.operations,
            "hold_offset": _deconvert_hold_offset(output_data.holdOffset),
            "sticky": _deconvert_sticky(output_data.sticky),
        }
        if serialized_on_wire(output_data.thread):
            element_config_data["core"] = _deconvert_element_thread(output_data.thread)
        if serialized_on_wire(output_data.outputPulseParameters):
            element_config_data["timeTaggingParameters"] = _deconvert_time_tagging_params(
                output_data.outputPulseParameters
            )
        input_value = which_one_of(output_data, "element_inputs_one_of")[1]
        if isinstance(input_value, inc_qua_config_pb2.QuaConfig.SingleInput):
            element_config_data["singleInput"] = _deconvert_single_inputs(input_value)
        elif isinstance(input_value, inc_qua_config_pb2.QuaConfig.MixInputs):
            element_config_data["mixInputs"] = _deconvert_mix_inputs(input_value)
        elif isinstance(input_value, inc_qua_config_pb2.QuaConfig.SingleInputCollection):
            element_config_data["singleInputCollection"] = _deconvert_single_input_collection(input_value)
        elif isinstance(input_value, inc_qua_config_pb2.QuaConfig.MultipleInputs):
            element_config_data["multipleInputs"] = _deconvert_multiple_inputs(input_value)
        elif isinstance(input_value, inc_qua_config_pb2.QuaConfig.MicrowaveInputPortReference):
            element_config_data["MWInput"] = _deconvert_element_mw_input(input_value)

        output_value = which_one_of(output_data, "element_outputs_one_of")[1]
        if isinstance(output_value, inc_qua_config_pb2.QuaConfig.MicrowaveOutputPortReference):
            element_config_data["MWOutput"] = _deconvert_element_mw_output(output_value)

        if output_data.HasField("smearing"):
            element_config_data["smearing"] = output_data.smearing.value
        if output_data.HasField("timeOfFlight"):
            element_config_data["time_of_flight"] = output_data.timeOfFlight.value
        if output_data.HasField("measurementQe"):
            element_config_data["measurement_qe"] = output_data.measurementQe.value

        oscillator_key, oscillator = which_one_of(output_data, "oscillator_one_of")
        if oscillator_key == "named_oscillator":
            assert isinstance(oscillator, str)
            element_config_data["oscillator"] = oscillator
        else:
            sign = (-1) ** output_data.intermediateFrequencyNegative
            if output_data.intermediateFrequencyDouble:
                element_config_data["intermediate_frequency"] = abs(output_data.intermediateFrequencyDouble) * sign
            elif output_data.intermediateFrequency is not None:
                element_config_data["intermediate_frequency"] = abs(output_data.intermediateFrequency.value) * sign

        return element_config_data


def element_thread_to_pb(name: str) -> inc_qua_config_pb2.QuaConfig.ElementThread:
    return inc_qua_config_pb2.QuaConfig.ElementThread(threadName=name)


def single_input_to_pb(controller: str, fem: int, number: int) -> inc_qua_config_pb2.QuaConfig.SingleInput:
    return inc_qua_config_pb2.QuaConfig.SingleInput(port=dac_port_ref_to_pb(controller, fem, number))


def adc_port_ref_to_pb(controller: str, fem: int, number: int) -> inc_qua_config_pb2.QuaConfig.AdcPortReference:
    return inc_qua_config_pb2.QuaConfig.AdcPortReference(controller=controller, fem=fem, number=number)


def port_ref_to_pb(controller: str, fem: int, number: int) -> inc_qua_config_pb2.QuaConfig.PortReference:
    return inc_qua_config_pb2.QuaConfig.PortReference(controller=controller, fem=fem, number=number)


def digital_input_port_ref_to_pb(
    data: DigitalInputConfigType,
) -> inc_qua_config_pb2.QuaConfig.DigitalInputPortReference:
    digital_input = inc_qua_config_pb2.QuaConfig.DigitalInputPortReference(
        delay=int(data["delay"]),
        buffer=int(data["buffer"]),
    )
    if "port" in data:
        digital_input.port.CopyFrom(port_ref_to_pb(*_get_port_reference_with_fem(data["port"])))

    return digital_input


def digital_output_port_ref_to_pb(data: PortReferenceType) -> inc_qua_config_pb2.QuaConfig.DigitalOutputPortReference:
    return inc_qua_config_pb2.QuaConfig.DigitalOutputPortReference(
        port=port_ref_to_pb(*_get_port_reference_with_fem(data))
    )


def _deconvert_polarity(
    polarity: inc_qua_config_pb2.QuaConfig.OutputPulseParameters.Polarity,
) -> Literal["ABOVE", "BELOW"]:
    if polarity == inc_qua_config_pb2.QuaConfig.OutputPulseParameters.Polarity.ASCENDING:
        return "ABOVE"
    if polarity == inc_qua_config_pb2.QuaConfig.OutputPulseParameters.Polarity.DESCENDING:
        return "BELOW"
    raise ValueError(f"Unknown polarity - {polarity}")


def _deconvert_time_tagging_params(
    data: inc_qua_config_pb2.QuaConfig.OutputPulseParameters,
) -> TimeTaggingParametersConfigType:
    to_return: TimeTaggingParametersConfigType = {
        "signalThreshold": data.signalThreshold,
        "signalPolarity": _deconvert_polarity(data.signalPolarity),
        "derivativeThreshold": data.derivativeThreshold,
        "derivativePolarity": _deconvert_polarity(data.derivativePolarity),
    }
    return to_return


def _deconvert_mix_inputs(mix_inputs: inc_qua_config_pb2.QuaConfig.MixInputs) -> MixInputConfigType:
    res: MixInputConfigType = {
        "I": _deconvert_port_reference(mix_inputs.I),
        "Q": _deconvert_port_reference(mix_inputs.Q),
    }

    mixer = mix_inputs.mixer
    if mixer is not None:
        res["mixer"] = mixer

    if mix_inputs.loFrequencyDouble:
        res["lo_frequency"] = mix_inputs.loFrequencyDouble
    else:
        res["lo_frequency"] = float(mix_inputs.loFrequency)

    return res


def _deconvert_single_inputs(single: inc_qua_config_pb2.QuaConfig.SingleInput) -> SingleInputConfigType:
    return {"port": _deconvert_port_reference(single.port)}


def _deconvert_hold_offset(hold_offset: inc_qua_config_pb2.QuaConfig.HoldOffset) -> HoldOffsetConfigType:
    return {"duration": hold_offset.duration}


def _deconvert_sticky(sticky: inc_qua_config_pb2.QuaConfig.Sticky) -> StickyConfigType:
    res: StickyConfigType = {
        "analog": sticky.analog,
        "digital": sticky.digital,
        "duration": max(sticky.duration, 1) * 4,
    }
    return res


def _deconvert_element_mw_input(data: inc_qua_config_pb2.QuaConfig.MicrowaveInputPortReference) -> MwInputConfigType:
    return {
        "port": _deconvert_port_reference(data.port),
        "upconverter": cast(Upconverter, data.upconverter),
    }


def _deconvert_element_mw_output(data: inc_qua_config_pb2.QuaConfig.MicrowaveOutputPortReference) -> MwOutputConfigType:
    return {
        "port": _deconvert_port_reference(data.port),
    }


def _deconvert_element_thread(element_thread: inc_qua_config_pb2.QuaConfig.ElementThread) -> str:
    return element_thread.threadName


def _deconvert_port_reference(
    data: Union[
        inc_qua_config_pb2.QuaConfig.AdcPortReference,
        inc_qua_config_pb2.QuaConfig.DacPortReference,
        inc_qua_config_pb2.QuaConfig.PortReference,
    ],
) -> PortReferenceType:
    if data.fem:
        return data.controller, data.fem, data.number
    else:
        return data.controller, data.number


def _deconvert_mw_analog_inputs(
    inputs: dict[int, inc_qua_config_pb2.QuaConfig.MicrowaveAnalogInputPortDec],
) -> Mapping[Union[int, str], MwFemAnalogInputPortConfigType]:
    return {idx: _deconvert_single_mw_analog_input(_input) for idx, _input in inputs.items()}


def _deconvert_inputs(
    inputs: MutableMapping[str, inc_qua_config_pb2.QuaConfig.DigitalInputPortReference]
) -> dict[str, DigitalInputConfigType]:
    ret: dict[str, DigitalInputConfigType] = {}
    for name, data in inputs.items():
        ret[name] = {"delay": data.delay, "buffer": data.buffer, "port": _deconvert_port_reference(data.port)}
    return ret


def _deconvert_digital_output(
    outputs: MutableMapping[str, inc_qua_config_pb2.QuaConfig.DigitalOutputPortReference]
) -> dict[str, PortReferenceType]:
    ret = {}
    for name, data in outputs.items():
        ret[name] = _deconvert_port_reference(data.port)

    return ret


def _deconvert_single_input_collection(
    data: inc_qua_config_pb2.QuaConfig.SingleInputCollection,
) -> InputCollectionConfigType:
    temp = {}
    for name, input_info in data.inputs.items():
        temp[name] = _deconvert_port_reference(input_info)

    res: InputCollectionConfigType = {"inputs": temp}
    return res


def _deconvert_multiple_inputs(data: inc_qua_config_pb2.QuaConfig.MultipleInputs) -> InputCollectionConfigType:
    temp = {}
    for name, input_info in data.inputs.items():
        temp[name] = _deconvert_port_reference(input_info)

    res: InputCollectionConfigType = {"inputs": temp}
    return res


def _deconvert_single_mw_analog_input(
    data: inc_qua_config_pb2.QuaConfig.MicrowaveAnalogInputPortDec,
) -> MwFemAnalogInputPortConfigType:
    return cast(
        MwFemAnalogInputPortConfigType,
        {
            "band": cast(Literal[1, 3, 3], data.band),
            "shareable": data.shareable,
            "gain_db": data.gain_db,
            "sampling_rate": data.samplingRate,
            "downconverter_frequency": data.downconverter.frequency,
        },
    )


def _deconvert_element_output(
    outputs: MutableMapping[str, inc_qua_config_pb2.QuaConfig.AdcPortReference],
    multiple_outputs: Optional[
        Union[inc_qua_config_pb2.QuaConfig.MultipleOutputs, inc_qua_config_pb2.QuaConfig.MicrowaveOutputPortReference]
    ],
) -> dict[str, PortReferenceType]:
    if isinstance(multiple_outputs, inc_qua_config_pb2.QuaConfig.MultipleOutputs):
        return {name: _deconvert_port_reference(data) for name, data in multiple_outputs.port_references.items()}
    return {name: _deconvert_port_reference(data) for name, data in outputs.items()}
