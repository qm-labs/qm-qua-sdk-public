import logging
from typing import Literal, cast
from collections.abc import Mapping, Collection

from qm.exceptions import ConfigValidationException
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm._config_converters._port_lookup import PortLookup
from qm._config_converters._utils import natural_sort_key
from qm.utils.protobuf_utils import which_one_of, serialized_on_wire
from qm.api.models.capabilities import OPX_FEM_IDX, QopCaps, ServerCapabilities
from qm._config_converters._model_to_pb_converter.base_converter import BaseModelToPbConverter
from qm._config_converters._model_to_pb_converter.converters.octave_converter import OctaveConverter
from qm.type_hinting.config_types import Upconverter, StandardPort, MwInputConfigType, PortReferenceType
from qm._config_converters._model_to_pb_converter.converters.pulse_converter import PulsesData, PulseConverter
from qm._config_converters._model_to_pb_converter.converters.control_device_converter import ControlDeviceConverter
from qm._config_converters._model_to_pb_converter.converters.mixer_correction_converter import MixerCorrectionConverter
from qm.utils.config_utils import (
    get_logical_pb_config,
    get_fem_config_instance,
    unset_logical_pb_config,
    get_controller_pb_config,
)
from qm.config import (
    Port,
    Mixer,
    Pulse,
    Element,
    MwInput,
    NoInput,
    MwOutput,
    Polarity,
    AnyElement,
    MixedInput,
    Oscillator,
    SingleInput,
    ElementInput,
    StickyParams,
    ElementOutput,
    LogicalConfig,
    MixedLfOutput,
    MultipleInputs,
    SingleLfOutput,
    FullConfigModel,
    ControllerConfig,
    TimeTaggingParams,
    UpconvertedRfInput,
    ElementDigitalInput,
    ElementDigitalOutput,
    SingleInputCollection,
)

logger = logging.getLogger(__name__)


class StickyElementIsNotSupported(ConfigValidationException):
    pass


class PulseAmbiguityError(ConfigValidationException):
    pass


CYCLES_TO_NS = 4


def convert_elements(
    elements: Collection[AnyElement], capabilities: ServerCapabilities, init_mode: bool = True
) -> QuaConfig:
    return convert_config(FullConfigModel(logical_config=LogicalConfig(elements)), capabilities, init_mode)


def convert_config(config: FullConfigModel, capabilities: ServerCapabilities, init_mode: bool = True) -> QuaConfig:
    return ElementConverter(capabilities, init_mode).convert(config)


def convert_controller_config(
    config: ControllerConfig, capabilities: ServerCapabilities, init_mode: bool = True
) -> QuaConfig:
    return ControllerConfigConverter(init_mode=init_mode, capabilities=capabilities).convert(config)


class ControllerConfigConverter:
    def __init__(self, capabilities: ServerCapabilities, init_mode: bool):
        self._capabilities = capabilities
        self._init_mode = init_mode
        self.control_device_converter = ControlDeviceConverter(capabilities, init_mode)
        self._mixer_converter = MixerCorrectionConverter(capabilities, init_mode)
        self._octave_converter = OctaveConverter(capabilities, init_mode)

    def convert(self, input_data: ControllerConfig) -> QuaConfig:
        if not self._init_mode and input_data.octave_ports:
            logger.warning("Octaves are not changed in non-init mode, ignoring changes in octave configuration")
        controllers = self.control_device_converter.convert(input_data.ports)
        mixers = self._mixer_converter.convert(input_data.mixers)
        octaves = self._octave_converter.convert(input_data.octave_ports)

        pb_config = self.set_config_wrapper()
        controller_config = get_controller_pb_config(pb_config)

        for controller_name, controller_inst in controllers.items():
            controller_config.controlDevices[controller_name].CopyFrom(controller_inst)

        # Controllers attribute is supported only in config v1
        if self.all_controllers_are_opx(controller_config.controlDevices) and isinstance(
            controller_config, QuaConfig.QuaConfigV1
        ):
            for _k, _v in controller_config.controlDevices.items():
                controller_inst = get_fem_config_instance(_v.fems[OPX_FEM_IDX])
                if not isinstance(controller_inst, QuaConfig.ControllerDec):
                    raise ValueError("This should not happen")
                controller_config.controllers[_k].CopyFrom(controller_inst)

        for name, mixer in mixers.items():
            controller_config.mixers[name].CopyFrom(mixer)

        for octave_name, octave in octaves.items():
            controller_config.octaves[octave_name].CopyFrom(octave)

        return pb_config

    @staticmethod
    def all_controllers_are_opx(control_devices: Mapping[str, QuaConfig.DeviceDec]) -> bool:
        for device_config in control_devices.values():
            for fem_config in device_config.fems.values():
                _, controller_inst = which_one_of(fem_config, "fem_type_one_of")
                if not isinstance(controller_inst, QuaConfig.ControllerDec):
                    return False
        return True

    def set_config_wrapper(self) -> QuaConfig:
        pb_config = QuaConfig()

        if self._capabilities.supports(QopCaps.config_v2):
            pb_config.v2.CopyFrom(
                QuaConfig.QuaConfigV2(
                    controller_config=QuaConfig.ControllerConfig(), logical_config=QuaConfig.LogicalConfig()
                )
            )
        else:
            pb_config.v1beta.CopyFrom(QuaConfig.QuaConfigV1())

        return pb_config


class ElementConverter(BaseModelToPbConverter[FullConfigModel, QuaConfig]):
    def __init__(self, capabilities: ServerCapabilities, init_mode: bool):
        super().__init__(capabilities, init_mode)
        self._controller_config_converter = ControllerConfigConverter(capabilities, init_mode)
        self._pulse_converter = PulseConverter(capabilities, init_mode)

    def convert(self, input_data: FullConfigModel) -> QuaConfig:
        pb_config = self._controller_config_converter.convert(input_data.get_controller_config(self._init_mode))
        if not self._init_mode:
            # set_config_wrapper always populates v2.logical_config with an empty message; the server treats its
            # mere presence as "logical parts being modified" and rejects the request. Strip it when empty.
            logical_config = get_logical_pb_config(pb_config)
            if not serialized_on_wire(logical_config):
                unset_logical_pb_config(pb_config)
            return pb_config

        return self.convert_logical_config(input_data.logical_config, pb_config)

    def convert_logical_config(
        self, config: LogicalConfig, controller_config: QuaConfig | ControllerConfig | None = None
    ) -> QuaConfig:
        if isinstance(controller_config, QuaConfig):
            pb_config = controller_config
        else:
            # A raw (or absent) ControllerConfig is an explicit, ad-hoc port-property override at
            # execution time; always convert it in update mode so unset fields aren't reset to defaults.
            pb_config = convert_controller_config(
                controller_config if controller_config is not None else ControllerConfig(),
                capabilities=self._capabilities,
                init_mode=False,
            )

        pulses_data = self._convert_pulses(config.elements)
        elements = self._convert_elements(config.elements)
        oscillators = self._convert_oscillators(config.elements)

        logical_config = get_logical_pb_config(pb_config)
        for element_name, element in elements.items():
            logical_config.elements[element_name].CopyFrom(element)

        for pulse_name, pulse in pulses_data.pulses.items():
            logical_config.pulses[pulse_name].CopyFrom(pulse)

        for wf_name, wf in pulses_data.waveforms.items():
            logical_config.waveforms[wf_name].CopyFrom(wf)

        for digital_wf_name, digital_wf in pulses_data.digital_waveforms.items():
            logical_config.digitalWaveforms[digital_wf_name].CopyFrom(digital_wf)

        for iw_name, iw in pulses_data.integration_weights.items():
            logical_config.integrationWeights[iw_name].CopyFrom(iw)

        for oscillator_name, oscillator in oscillators.items():
            logical_config.oscillators[oscillator_name].CopyFrom(oscillator)

        return pb_config

    def _convert_pulses(self, elements: Collection[AnyElement]) -> PulsesData:
        pulses: list[Pulse] = []
        for element in elements:
            pulses.extend(element.pulses.values())
        return self._pulse_converter.convert(pulses)

    def _convert_oscillators(self, elements: Collection[AnyElement]) -> Mapping[str, QuaConfig.Oscillator]:
        ret: dict[str, QuaConfig.Oscillator] = {}
        for element in elements:
            if element.oscillator is not None:
                to_add = QuaConfig.Oscillator()
                to_add.intermediateFrequency.value = element.oscillator.intermediate_frequency.as_int
                if self._capabilities.supports_double_frequency:
                    to_add.intermediateFrequencyDouble = element.oscillator.intermediate_frequency.as_float
                if element.oscillator.mixer is not None:
                    to_add.mixer.CopyFrom(QuaConfig.MixerRef(mixer=element.oscillator.mixer.name))
                    to_add.mixer.loFrequency = element.oscillator.lo_frequency.as_int
                    if self._capabilities.supports_double_frequency:
                        to_add.mixer.loFrequencyDouble = element.oscillator.lo_frequency.as_float
                osc_name = element.oscillator.name
                if osc_name in ret and ret[osc_name] != to_add:
                    raise ConfigValidationException(
                        f"Two different oscillators are declared with the same name `{osc_name}`"
                    )
                ret[osc_name] = to_add
        return ret

    def _convert_elements(self, input_data: Collection[AnyElement]) -> Mapping[str, QuaConfig.ElementDec]:
        return {element.name: self._convert_single_element(element) for element in input_data}

    def _convert_single_element(self, data: AnyElement) -> QuaConfig.ElementDec:
        # `Element.__init__` already guarantees that an element with an output has a
        # `time_of_flight`, so there is nothing left to validate here.
        element = QuaConfig.ElementDec()

        # Emit time_of_flight / smearing whenever the source dict supplied them, mirroring
        # the dict-to-pb path. `Element.__init__` auto-defaults `smearing` to 0 for elements
        # with outputs (when not user-supplied), so the `is not None` check is sufficient.
        if data.time_of_flight is not None:
            element.timeOfFlight.value = data.time_of_flight

        if data.smearing is not None:
            element.smearing.value = data.smearing

        if data.intermediate_frequency is not None:
            # As in the legacy dict -> pb converter: the oscillator fields are signed, the others are unsigned.
            element.intermediateFrequency.value = data.intermediate_frequency.as_uint
            element.intermediateFrequencyOscillator.value = data.intermediate_frequency.as_int
            if self._capabilities.supports_double_frequency:
                element.intermediateFrequencyDouble = data.intermediate_frequency.as_ufloat
                element.intermediateFrequencyOscillatorDouble = data.intermediate_frequency.as_float

            element.intermediateFrequencyNegative = data.intermediate_frequency.is_negative
        elif data.oscillator is not None:
            element.namedOscillator.value = data.oscillator.name
        else:
            # Neither intermediate_frequency nor oscillator set → select the noOscillator oneof arm.
            element.noOscillator.SetInParent()

        if data.core:
            element.thread.CopyFrom(element_thread_to_pb(data.core))

        if data.output is not None:
            for port_alias, element_output_port in data.output.name_to_port.items():
                element.outputs[port_alias].CopyFrom(adc_port_ref_to_pb(element_output_port))
        element.multipleOutputs.CopyFrom(QuaConfig.MultipleOutputs(port_references=element.outputs))
        if isinstance(data.output, MwOutput):
            element.microwaveOutput.CopyFrom(
                QuaConfig.MicrowaveOutputPortReference(
                    port=adc_port_ref_to_pb(data.output.out),
                )
            )

        for digital_input in data.digital_inputs:
            element.digitalInputs[digital_input.name].CopyFrom(digital_input_port_ref_to_pb(digital_input))

        for digital_output in data.digital_outputs:
            element.digitalOutputs[digital_output.name].CopyFrom(digital_output_port_ref_to_pb(digital_output))

        for op_name, op_value in data.pulses.items():
            element.operations[op_name] = op_value.name

        if isinstance(data.input, SingleInput):
            element.singleInput.CopyFrom(single_input_to_pb(data.input))

        if isinstance(data.input, MixedInput):
            mix_input = data.input
            mix_inputs_pb = QuaConfig.MixInputs(
                I=dac_port_ref_to_pb(mix_input.i_port),
                Q=dac_port_ref_to_pb(mix_input.q_port),
            )
            if mix_input.mixer is not None:
                mix_inputs_pb.mixer = mix_input.mixer.name
            element.mixInputs.CopyFrom(mix_inputs_pb)
            if isinstance(data.input, UpconvertedRfInput):
                element.RFInputs[data.input.name].CopyFrom(
                    QuaConfig.GeneralPortReference(
                        device_name=data.input.octave_port.device.device_name, port=data.input.octave_port.index
                    )
                )

            element.mixInputs.loFrequency = mix_input.lo_frequency_int
            if self._capabilities.supports_double_frequency:
                element.mixInputs.loFrequencyDouble = mix_input.lo_frequency

        if isinstance(data.input, SingleInputCollection):
            element.singleInputCollection.CopyFrom(
                QuaConfig.SingleInputCollection(
                    inputs={k: dac_port_ref_to_pb(v) for k, v in data.input.name_to_port.items()}
                )
            )

        if isinstance(data.input, MultipleInputs):
            element.multipleInputs.CopyFrom(
                QuaConfig.MultipleInputs(inputs={k: dac_port_ref_to_pb(v) for k, v in data.input.name_to_port.items()})
            )

        if isinstance(data.input, MwInput):
            element.microwaveInput.CopyFrom(
                QuaConfig.MicrowaveInputPortReference(
                    port=dac_port_ref_to_pb(data.input.port), upconverter=data.input.upconverter_idx
                )
            )

        if data.sticky:
            if self._capabilities.supports_sticky_elements:
                element.sticky.CopyFrom(
                    QuaConfig.Sticky(
                        analog=data.sticky.analog, digital=data.sticky.digital, duration=data.sticky.duration_cycles
                    )
                )
            else:
                if data.sticky.digital:
                    raise StickyElementIsNotSupported("Not supported")
                element.holdOffset.CopyFrom(QuaConfig.HoldOffset(duration=data.sticky.duration_cycles))

        if data.persistent:
            if not self._capabilities.supports_persistent_elements:
                raise ConfigValidationException(QopCaps.persistent_elements.unsupported_exception_message)
            element.persistent = True

        if data.time_tagging_parameters:
            element.outputPulseParameters.CopyFrom(self.create_time_tagging_parameters(data.time_tagging_parameters))

        if data.output_connected_to_octave is not None:
            octave_port = data.output_connected_to_octave
            element.RFOutputs["out1"].CopyFrom(
                QuaConfig.GeneralPortReference(device_name=octave_port.device.device_name, port=octave_port.index)
            )

        return element

    @staticmethod
    def create_time_tagging_parameters(
        data: TimeTaggingParams,
    ) -> QuaConfig.OutputPulseParameters:
        return QuaConfig.OutputPulseParameters(
            signalThreshold=data.signal_threshold,
            signalPolarity=ElementConverter._create_signal_polarity(data.signal_polarity),
            derivativeThreshold=data.derivative_threshold,
            derivativePolarity=ElementConverter._create_signal_polarity(data.derivative_polarity),
        )

    @staticmethod
    def _create_signal_polarity(polarity: Polarity) -> QuaConfig.OutputPulseParameters.Polarity:
        if polarity == "ABOVE":
            return QuaConfig.OutputPulseParameters.Polarity.ASCENDING
        elif polarity == "BELOW":
            return QuaConfig.OutputPulseParameters.Polarity.DESCENDING
        else:
            raise ConfigValidationException(f"Invalid signal polarity: {polarity}")

    def deconvert(self, output_data: QuaConfig) -> FullConfigModel:
        controller_config = get_controller_pb_config(output_data)
        logical_config = get_logical_pb_config(output_data)

        pulses_data = PulsesData(
            digital_waveforms=logical_config.digitalWaveforms,
            waveforms=logical_config.waveforms,
            integration_weights=logical_config.integrationWeights,
            pulses=logical_config.pulses,
        )
        pulses_by_name = {p.name: p for p in self._pulse_converter.deconvert(pulses_data)}

        controllers = controller_config.controlDevices if controller_config.controlDevices else {}
        all_ports = self._controller_config_converter.control_device_converter.deconvert(controllers)
        port_lookup = PortLookup(all_ports)

        # Deconvert mixers
        mixer_map: dict[str, Mixer] = {}
        for mixer_name, mixer_dec in controller_config.mixers.items():
            if mixer_dec.correction:
                mixers = self._controller_config_converter._mixer_converter.deconvert({mixer_name: mixer_dec})
                for m in mixers:
                    mixer_map[m.name] = m

        oscillator_lookup: dict[str, Oscillator] = {}
        for oscillator_name, oscillator_dec in logical_config.oscillators.items():
            osc_mixer = None
            lo_freq = 0.0
            if oscillator_dec.intermediateFrequencyDouble:
                freq = oscillator_dec.intermediateFrequencyDouble
            else:
                freq = int(oscillator_dec.intermediateFrequency.value)
            if serialized_on_wire(oscillator_dec.mixer):
                if oscillator_dec.mixer.mixer:
                    osc_mixer = mixer_map[oscillator_dec.mixer.mixer]
                if oscillator_dec.mixer.loFrequencyDouble:
                    lo_freq = float(oscillator_dec.mixer.loFrequencyDouble)
                elif oscillator_dec.mixer.loFrequency:
                    lo_freq = int(oscillator_dec.mixer.loFrequency)
            oscillator_lookup[oscillator_name] = Oscillator(
                intermediate_frequency=freq, lo_frequency=lo_freq, mixer=osc_mixer, name=oscillator_name
            )

        elements: list[AnyElement] = []
        for name, element_pb in logical_config.elements.items():
            element = self._deconvert_single_element(
                name, element_pb, pulses_by_name, mixer_map, port_lookup, oscillator_lookup
            )
            elements.append(element)

        additional_controller_config = self._add_unconnected_controller_config_items(elements, mixer_map, port_lookup)
        return FullConfigModel(LogicalConfig(elements), additional_controller_config=additional_controller_config)

    @staticmethod
    def _add_unconnected_controller_config_items(
        elements: Collection[AnyElement], mixer_map: Mapping[str, Mixer], port_lookup: PortLookup
    ) -> ControllerConfig:
        """Add all the ports and the mixers that are not connected to elements"""
        used_port_ids: set[int] = set()
        used_mixer_names: set[str] = set()
        for element in elements:
            for port in element.all_ports:
                used_port_ids.add(id(port))
            if isinstance(element.input, MixedInput) and element.input.mixer is not None:
                used_mixer_names.add(element.input.mixer.name)

        unused_ports: list[Port] = []
        for port_dict in (
            port_lookup.analog_outputs_lf,
            port_lookup.analog_outputs_mw,
            port_lookup.analog_inputs_lf,
            port_lookup.analog_inputs_mw,
            port_lookup.digital_outputs,
            port_lookup.digital_inputs,
        ):
            for port in port_dict.values():
                if id(port) not in used_port_ids:
                    unused_ports.append(port)

        unused_mixers = [m for name, m in mixer_map.items() if name not in used_mixer_names]

        return ControllerConfig(ports=unused_ports, mixers=unused_mixers)

    def _deconvert_single_element(
        self,
        name: str,
        pb: QuaConfig.ElementDec,
        pulses_by_name: Mapping[str, Pulse],
        mixer_map: Mapping[str, Mixer],
        port_lookup: "PortLookup",
        oscillator_lookup: Mapping[str, Oscillator],
    ) -> AnyElement:
        if pb.namedOscillator.value:
            if_freq = None
            if pb.namedOscillator.value not in oscillator_lookup:
                raise ConfigValidationException(f"Oscillator `{pb.namedOscillator.value}` was not found")
            osc = oscillator_lookup[pb.namedOscillator.value]
        elif pb.WhichOneof("oscillator_one_of") in (None, "noOscillator"):
            osc = None
            if_freq = None
        else:
            osc = None
            # The oscillator fields are written signed, and the negative flag is set too, so take the magnitude
            # before applying the sign.
            sign = (-1) ** pb.intermediateFrequencyNegative
            if self._capabilities.supports_double_frequency and pb.intermediateFrequencyOscillatorDouble:
                if_freq = abs(pb.intermediateFrequencyOscillatorDouble) * sign
            else:
                if_freq = float(abs(pb.intermediateFrequencyOscillator.value) * sign)

        input_ = _deconvert_element_input(pb, mixer_map, port_lookup)
        output = _deconvert_element_output(pb, port_lookup)

        digital_inputs = _deconvert_digital_inputs(pb.digitalInputs, port_lookup)
        digital_outputs = _deconvert_digital_outputs(pb.digitalOutputs, port_lookup)

        # The server may report these on elements without outputs (e.g. octave calibration elements), but the
        # model only allows them on elements that have outputs.
        has_any_output = output is not None or bool(digital_outputs)
        time_of_flight = pb.timeOfFlight.value if has_any_output and serialized_on_wire(pb.timeOfFlight) else None
        smearing = pb.smearing.value if has_any_output and serialized_on_wire(pb.smearing) else None

        sticky = None
        if serialized_on_wire(pb.sticky):
            sticky = StickyParams(
                analog=pb.sticky.analog,
                digital=pb.sticky.digital,
                duration_ns=max(pb.sticky.duration, 1) * CYCLES_TO_NS,
            )
        elif serialized_on_wire(pb.holdOffset) and pb.holdOffset.duration:
            sticky = StickyParams(analog=True, digital=False, duration_ns=pb.holdOffset.duration * CYCLES_TO_NS)

        core = _deconvert_element_thread(pb.thread) if serialized_on_wire(pb.thread) else ""

        time_tagging_parameters = None
        if serialized_on_wire(pb.outputPulseParameters):
            opp = pb.outputPulseParameters
            time_tagging_parameters = TimeTaggingParams(
                threshold=opp.signalThreshold,
                signal_polarity=_deconvert_polarity(opp.signalPolarity),
                derivative_threshold=opp.derivativeThreshold,
                derivative_polarity=_deconvert_polarity(opp.derivativePolarity),
            )

        element: AnyElement = Element(
            name=name,
            input_=input_,
            oscillator=osc,
            intermediate_frequency=if_freq,
            time_of_flight=time_of_flight,
            smearing=smearing,
            output_=output,
            digital_inputs=tuple(digital_inputs),
            digital_outputs=tuple(digital_outputs),
            sticky=sticky,
            core=core,
            persistent=pb.persistent,
            time_tagging_parameters=time_tagging_parameters,
        )

        # Add pulses via operations mapping
        for op_name, pulse_name in pb.operations.items():
            if pulse_name not in pulses_by_name:
                raise ConfigValidationException(
                    f"Element `{name}` operation `{op_name}` references unknown pulse `{pulse_name}`"
                )
            element.add_pulse(pulses_by_name[pulse_name], name=op_name)

        return element


def element_thread_to_pb(name: str) -> QuaConfig.ElementThread:
    return QuaConfig.ElementThread(threadName=name)


def single_input_to_pb(data: SingleInput) -> QuaConfig.SingleInput:
    return QuaConfig.SingleInput(port=dac_port_ref_to_pb(port=data.port))


def adc_port_ref_to_pb(port: Port) -> QuaConfig.AdcPortReference:
    return QuaConfig.AdcPortReference(controller=port.controller_name, fem=port.fem_1_based, number=port.index_1_based)


def dac_port_ref_to_pb(port: Port) -> QuaConfig.DacPortReference:
    return QuaConfig.DacPortReference(controller=port.controller_name, fem=port.fem_1_based, number=port.index_1_based)


def port_ref_to_pb(port: Port) -> QuaConfig.PortReference:
    return QuaConfig.PortReference(controller=port.controller_name, fem=port.fem_1_based, number=port.index_1_based)


def digital_input_port_ref_to_pb(data: ElementDigitalInput) -> QuaConfig.DigitalInputPortReference:
    return QuaConfig.DigitalInputPortReference(
        port=port_ref_to_pb(port=data.port), delay=data.delay, buffer=data.buffer
    )


def digital_output_port_ref_to_pb(data: ElementDigitalOutput) -> QuaConfig.DigitalOutputPortReference:
    return QuaConfig.DigitalOutputPortReference(port=port_ref_to_pb(data.port))


def _deconvert_polarity(polarity: QuaConfig.OutputPulseParameters.Polarity) -> Literal["ABOVE", "BELOW"]:
    if polarity == QuaConfig.OutputPulseParameters.Polarity.ASCENDING:
        return "ABOVE"
    if polarity == QuaConfig.OutputPulseParameters.Polarity.DESCENDING:
        return "BELOW"
    raise ValueError(f"Unknown polarity - {polarity}")


def _deconvert_element_mw_input(data: QuaConfig.MicrowaveInputPortReference) -> MwInputConfigType:
    return {
        "port": _deconvert_port_reference(data.port),
        "upconverter": cast(Upconverter, data.upconverter),
    }


def _deconvert_element_thread(element_thread: QuaConfig.ElementThread) -> str:
    return element_thread.threadName


def _deconvert_port_reference(
    data: QuaConfig.AdcPortReference | QuaConfig.DacPortReference | QuaConfig.PortReference,
) -> PortReferenceType:
    if data.fem:
        return data.controller, data.fem, data.number
    else:
        return data.controller, data.number


def _ref_to_key(
    ref: QuaConfig.DacPortReference | QuaConfig.AdcPortReference | QuaConfig.PortReference,
) -> StandardPort:
    return (ref.controller, ref.fem or OPX_FEM_IDX, ref.number)


def _deconvert_element_input(
    pb: QuaConfig.ElementDec,
    mixer_map: Mapping[str, Mixer],
    port_lookup: PortLookup,
) -> ElementInput:
    _, input_value = which_one_of(pb, "element_inputs_one_of")

    if isinstance(input_value, QuaConfig.SingleInput):
        port = port_lookup.analog_outputs_lf[_ref_to_key(input_value.port)]
        return SingleInput(port=port)

    if isinstance(input_value, QuaConfig.MixInputs):
        i_port = port_lookup.analog_outputs_lf[_ref_to_key(input_value.I)]
        q_port = port_lookup.analog_outputs_lf[_ref_to_key(input_value.Q)]
        mixer: Mixer | None = None
        if input_value.mixer:
            # A mixer named but with no correction data (e.g. referenced by name without ever
            # being given entries under "mixers") is never collected into the pb `mixers` map
            # (see `FullConfigModel._collect_mixers`), so this is a legitimate dangling-by-design
            # reference - not a real error. Mirrors the same stub creation on the dict-to-model
            # side (`_compose_element_input` in main_config_converter.py).
            mixer = mixer_map.get(input_value.mixer) or Mixer({}, name=input_value.mixer)
        lo_freq = input_value.loFrequencyDouble if input_value.loFrequencyDouble else float(input_value.loFrequency)
        return MixedInput(i_port=i_port, q_port=q_port, mixer=mixer, lo_frequency=lo_freq)

    if isinstance(input_value, QuaConfig.SingleInputCollection):
        ports = {name: port_lookup.analog_outputs_lf[_ref_to_key(ref)] for name, ref in input_value.inputs.items()}
        return SingleInputCollection(ports=ports)

    if isinstance(input_value, QuaConfig.MultipleInputs):
        ports = {name: port_lookup.analog_outputs_lf[_ref_to_key(ref)] for name, ref in input_value.inputs.items()}
        return MultipleInputs(ports=ports)

    if isinstance(input_value, QuaConfig.MicrowaveInputPortReference):
        port_mw = port_lookup.analog_outputs_mw[_ref_to_key(input_value.port)]
        return MwInput(port=port_mw, upconverter_idx=input_value.upconverter)

    return NoInput()


def _deconvert_element_output(
    pb: QuaConfig.ElementDec,
    port_lookup: PortLookup,
) -> ElementOutput | None:
    _, output_value = which_one_of(pb, "element_outputs_one_of")
    if isinstance(output_value, QuaConfig.MultipleOutputs):
        if len(output_value.port_references) == 0:
            return None
        if len(output_value.port_references) == 1:
            name, ref = list(output_value.port_references.items())[0]
            port_lf = port_lookup.analog_inputs_lf[_ref_to_key(ref)]
            return SingleLfOutput(port=port_lf, name=name)
        if len(output_value.port_references) == 2:
            name1, name2 = sorted(output_value.port_references, key=natural_sort_key)
            key1 = _ref_to_key(output_value.port_references[name1])
            key2 = _ref_to_key(output_value.port_references[name2])
            return MixedLfOutput(
                port_lookup.analog_inputs_lf[key1], port_lookup.analog_inputs_lf[key2], name1=name1, name2=name2
            )
        raise ConfigValidationException("Non standard number of ports")

    if isinstance(output_value, QuaConfig.MicrowaveOutputPortReference):
        port_mw = port_lookup.analog_inputs_mw[_ref_to_key(output_value.port)]
        return MwOutput(port=port_mw)

    return None


def _deconvert_digital_inputs(
    inputs: Mapping[str, QuaConfig.DigitalInputPortReference],
    port_lookup: PortLookup,
) -> list[ElementDigitalInput]:
    result = []
    for name, data in inputs.items():
        port = port_lookup.digital_outputs[_ref_to_key(data.port)]
        result.append(ElementDigitalInput(port=port, delay=data.delay, buffer=data.buffer, name=name))
    return result


def _deconvert_digital_outputs(
    outputs: Mapping[str, QuaConfig.DigitalOutputPortReference],
    port_lookup: PortLookup,
) -> list[ElementDigitalOutput]:
    result = []
    for name, data in outputs.items():
        port = port_lookup.digital_inputs[_ref_to_key(data.port)]
        result.append(ElementDigitalOutput(port=port, name=name))
    return result
