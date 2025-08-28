import uuid
import warnings
from typing import Dict, Union, Optional

import betterproto

from qm.utils import deprecation_message
from qm.api.models.capabilities import OPX_FEM_IDX, QopCaps, ServerCapabilities
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter
from qm.program._dict_to_pb_converter.converters.pulse_converter import PulseConverter
from qm.program._dict_to_pb_converter.converters.octave_converter import OctaveConverter
from qm.program._dict_to_pb_converter.converters.waveform_converter import WaveformConverter
from qm.program._dict_to_pb_converter.converters.oscillator_converter import OscillatorConverter
from qm.utils.config_utils import get_logical_pb_config, get_fem_config_instance, get_controller_pb_config
from qm.program._dict_to_pb_converter.converters.mixer_correction_converter import MixerCorrectionConverter
from qm.program._dict_to_pb_converter.converters.integration_weights_converter import IntegrationWeightsConverter
from qm.program._dict_to_pb_converter.converters.element_converter import ElementConverter, StickyElementIsNotSupported
from qm.type_hinting.config_types import FullQuaConfig, LogicalQuaConfig, ControllerQuaConfig, DigitalWaveformConfigType
from qm.program._dict_to_pb_converter.converters.control_device_converter.control_device_converter import (
    ControlDeviceConverter,
)
from qm.exceptions import (
    ConfigValidationException,
    OctaveUnsupportedOnUpdate,
    ConfigurationLockedByOctave,
    CapabilitiesNotInitializedError,
    ElementInputConnectionAmbiguity,
    ElementOutputConnectionAmbiguity,
)
from qm.grpc.qua_config import (
    QuaConfig,
    QuaConfigMatrix,
    QuaConfigMixerDec,
    QuaConfigDeviceDec,
    QuaConfigMixInputs,
    QuaConfigElementDec,
    QuaConfigQuaConfigV1,
    QuaConfigQuaConfigV2,
    QuaConfigOctaveConfig,
    QuaConfigControllerDec,
    QuaConfigLogicalConfig,
    QuaConfigCorrectionEntry,
    QuaConfigMultipleOutputs,
    QuaConfigControllerConfig,
    QuaConfigDigitalWaveformDec,
    QuaConfigOctaveRfOutputConfig,
    QuaConfigDigitalWaveformSample,
    QuaConfigMicrowaveOutputPortReference,
)


class DictToQuaConfigConverter(
    BaseDictToPbConverter[Union[FullQuaConfig, ControllerQuaConfig, LogicalQuaConfig], QuaConfig]
):
    def __init__(
        self, capabilities: ServerCapabilities, init_mode: bool = True, octave_already_configured: bool = False
    ):
        super().__init__(capabilities, init_mode)
        self.control_device_converter = ControlDeviceConverter(capabilities, init_mode)
        self.octave_converter = OctaveConverter(capabilities, init_mode)
        self.element_converter = ElementConverter(capabilities, init_mode)
        self.pulse_converter = PulseConverter(capabilities, init_mode)
        self.waveform_converter = WaveformConverter(capabilities, init_mode)
        self.iw_converter = IntegrationWeightsConverter(capabilities, init_mode)
        self.mixer_correction_converter = MixerCorrectionConverter(capabilities, init_mode)
        self.oscillator_converter = OscillatorConverter(capabilities, init_mode)

        self.octave_already_configured = octave_already_configured

    def convert(
        self,
        input_data: Union[FullQuaConfig, ControllerQuaConfig, LogicalQuaConfig],
    ) -> QuaConfig:
        self.run_preload_validations(input_data, self.octave_already_configured)

        pb_config = self.set_config_wrapper()
        controller_config = get_controller_pb_config(pb_config)
        logical_config = get_logical_pb_config(pb_config)

        def set_controllers() -> None:
            for k, v in input_data["controllers"].items():  # type: ignore[typeddict-item]
                controller_config.control_devices[k] = self.control_device_converter.convert(v)
            # Controllers attribute is supported only in config v1
            if self.all_controllers_are_opx(controller_config.control_devices) and isinstance(
                controller_config, QuaConfigQuaConfigV1
            ):
                for _k, _v in controller_config.control_devices.items():
                    controller_inst = get_fem_config_instance(_v.fems[OPX_FEM_IDX])
                    if not isinstance(controller_inst, QuaConfigControllerDec):
                        raise ValueError("This should not happen")
                    controller_config.controllers[_k] = controller_inst

        def set_octaves() -> None:
            for k, v in input_data.get("octaves", {}).items():  # type: ignore[attr-defined]
                controller_config.octaves[k] = self.octave_converter.convert(v)

        def set_elements() -> None:
            for k, v in input_data["elements"].items():  # type: ignore[typeddict-item]
                try:
                    logical_config.elements[k] = self.element_converter.convert(v)
                except StickyElementIsNotSupported:
                    raise ConfigValidationException(f"Server does not support digital sticky used in element " f"'{k}'")

        def set_pulses() -> None:
            for k, v in input_data["pulses"].items():  # type: ignore[typeddict-item]
                logical_config.pulses[k] = self.pulse_converter.convert(v)

        def set_waveforms() -> None:
            for k, v in input_data["waveforms"].items():  # type: ignore[typeddict-item]
                logical_config.waveforms[k] = self.waveform_converter.convert(v)

        def set_digital_waveforms() -> None:
            for k, v in input_data["digital_waveforms"].items():  # type: ignore[typeddict-item]
                logical_config.digital_waveforms[k] = QuaConfigDigitalWaveformDec(
                    samples=[QuaConfigDigitalWaveformSample(value=bool(s[0]), length=s[1]) for s in v["samples"]]
                )

        def set_integration_weights() -> None:
            for k, v in input_data["integration_weights"].items():  # type: ignore[typeddict-item]
                logical_config.integration_weights[k] = self.iw_converter.convert(v)

        def set_mixers() -> None:
            for k, v in input_data["mixers"].items():  # type: ignore[typeddict-item]
                controller_config.mixers[k] = QuaConfigMixerDec(
                    correction=[self.mixer_correction_converter.convert(u) for u in v]
                )

        def set_oscillators() -> None:
            for k, v in input_data["oscillators"].items():  # type: ignore[typeddict-item]
                logical_config.oscillators[k] = self.oscillator_converter.convert(v)

        key_to_action = {
            "version": lambda: None,
            "controllers": set_controllers,
            "elements": set_elements,
            "pulses": set_pulses,
            "waveforms": set_waveforms,
            "digital_waveforms": set_digital_waveforms,
            "integration_weights": set_integration_weights,
            "mixers": set_mixers,
            "oscillators": set_oscillators,
            "octaves": set_octaves,
        }

        if "version" in input_data:
            warnings.warn(
                deprecation_message("version", "1.2.2", "1.3.0", "Please remove it from the QUA config."),
                DeprecationWarning,
            )

        for key in input_data:
            key_to_action[key]()

        self.apply_post_load_setters(pb_config)

        return pb_config

    def run_preload_validations(
        self,
        config: Union[FullQuaConfig, ControllerQuaConfig, LogicalQuaConfig],
        octave_already_configured: bool = False,
    ) -> None:
        # When the capabilities aren't initialized, the capabilities argument is of type 'Provide' instead of 'ServerCapabilities'.
        # This is only relevant for qua_config_schema.py, where the capabilities are provided by the container.
        if not isinstance(self._capabilities, ServerCapabilities):
            raise CapabilitiesNotInitializedError

        if not self._init_mode:
            # With these two validations, we ensure any configuration that relates to Octave is done in init mode.
            # Or in other words, Octave doesn't support 'send program with config'.

            if "octaves" in config:
                raise OctaveUnsupportedOnUpdate("Octaves are not supported in non-init mode")

            logical_config_present = any(key in config for key in LogicalQuaConfig.__annotations__)
            if octave_already_configured and logical_config_present:
                # If Octaves were already configured, we cannot change the logical configuration anymore, because it may override
                # automatic configurations that were done for Octave, like the ones in "apply_post_load_setters()".
                raise ConfigurationLockedByOctave(
                    "Since Octaves were used in the initial configuration, no modifications to the logical configuration are allowed — whether related to Octaves or not. "
                    "To resolve this, either avoid using Octaves, or ensure all logical configuration is completed when opening the QM."
                )

    def set_config_wrapper(self) -> QuaConfig:
        pb_config = QuaConfig()

        if self._capabilities.supports(QopCaps.config_v2):
            pb_config.v2 = QuaConfigQuaConfigV2(
                controller_config=QuaConfigControllerConfig(), logical_config=QuaConfigLogicalConfig()
            )
        else:
            pb_config.v1_beta = QuaConfigQuaConfigV1()

        return pb_config

    @staticmethod
    def all_controllers_are_opx(control_devices: Dict[str, QuaConfigDeviceDec]) -> bool:
        for device_config in control_devices.values():
            for fem_config in device_config.fems.values():
                _, controller_inst = betterproto.which_one_of(fem_config, "fem_type_one_of")
                if not isinstance(controller_inst, QuaConfigControllerDec):
                    return False
        return True

    def apply_post_load_setters(self, pb_config: QuaConfig) -> None:
        # In config_v2, elements can be defined independently of mixers.
        # This breaks the existing logic, which automatically assigns default mixers and octave values based on the elements.
        # As a result, users of config_v2 that rely on these autocompleted values need to manually add them, or use the old flow (sending full config in init mode).
        # The long-term goal is to move autocompletion logic into the gateway. For more details, see: https://quantum-machines.atlassian.net/browse/OPXK-25086
        if self._init_mode:
            self.set_octave_upconverter_connection_to_elements(pb_config)
            self.set_lo_frequency_to_mix_input_elements_that_are_connected_to_octave(pb_config)
            self.set_octave_downconverter_connection_to_elements(pb_config)
            self.set_non_existing_mixers_in_mix_input_elements(pb_config)

    @staticmethod
    def set_octave_upconverter_connection_to_elements(pb_config: QuaConfig) -> None:
        octaves_config = get_controller_pb_config(pb_config).octaves
        elements_config = get_logical_pb_config(pb_config).elements

        for element in elements_config.values():
            for rf_input in element.rf_inputs.values():
                if rf_input.device_name in octaves_config:
                    if rf_input.port in octaves_config[rf_input.device_name].rf_outputs:
                        _, element_input = betterproto.which_one_of(element, "element_inputs_one_of")
                        if element_input is not None:
                            raise ElementInputConnectionAmbiguity("Ambiguous definition of element input")

                        upconverter_config = octaves_config[rf_input.device_name].rf_outputs[rf_input.port]
                        element.mix_inputs = QuaConfigMixInputs(
                            i=upconverter_config.i_connection, q=upconverter_config.q_connection
                        )

    def set_lo_frequency_to_mix_input_elements_that_are_connected_to_octave(self, pb_config: QuaConfig) -> None:
        octaves_config = get_controller_pb_config(pb_config).octaves
        elements_config = get_logical_pb_config(pb_config).elements

        for element in elements_config.values():
            _, element_input = betterproto.which_one_of(element, "element_inputs_one_of")
            if isinstance(element_input, QuaConfigMixInputs):
                rf_output = self._get_rf_output_for_octave(element, octaves_config)
                if rf_output is None:
                    continue

                if element_input.lo_frequency not in {0, int(rf_output.lo_frequency)}:
                    raise ConfigValidationException(
                        "LO frequency mismatch. The frequency stated in the element is different from "
                        "the one stated in the Octave, remove the one in the element."
                    )
                element_input.lo_frequency = int(rf_output.lo_frequency)
                if self._capabilities.supports_double_frequency:
                    element_input.lo_frequency_double = rf_output.lo_frequency

    @staticmethod
    def _get_rf_output_for_octave(
        element: QuaConfigElementDec, octaves: Dict[str, QuaConfigOctaveConfig]
    ) -> Optional[QuaConfigOctaveRfOutputConfig]:
        if element.rf_inputs:
            element_rf_input = list(element.rf_inputs.values())[0]
            octave_config = octaves[element_rf_input.device_name]
            return octave_config.rf_outputs[element_rf_input.port]

        # This part is for users that do not use the rf_inputs  for connecting the octave
        element_input = element.mix_inputs
        for octave in octaves.values():
            for rf_output in octave.rf_outputs.values():
                if all(
                    [
                        (rf_output.i_connection.controller == element_input.i.controller),
                        (rf_output.i_connection.fem == element_input.i.fem),
                        (rf_output.i_connection.number == element_input.i.number),
                        (rf_output.q_connection.controller == element_input.q.controller),
                        (rf_output.q_connection.fem == element_input.q.fem),
                        (rf_output.q_connection.number == element_input.q.number),
                    ]
                ):
                    return rf_output
        return None

    @staticmethod
    def set_octave_downconverter_connection_to_elements(pb_config: QuaConfig) -> None:
        octaves_config = get_controller_pb_config(pb_config).octaves
        elements_config = get_logical_pb_config(pb_config).elements

        for element in elements_config.values():
            for _, rf_output in element.rf_outputs.items():
                if rf_output.device_name in octaves_config:
                    if rf_output.port in octaves_config[rf_output.device_name].rf_inputs:
                        downconverter_config = octaves_config[rf_output.device_name].if_outputs
                        outputs_form_octave = {
                            downconverter_config.if_out1.name: downconverter_config.if_out1.port,
                            downconverter_config.if_out2.name: downconverter_config.if_out2.port,
                        }
                        for k, v in outputs_form_octave.items():
                            if k in element.outputs:
                                if v != element.outputs[k]:
                                    raise ElementOutputConnectionAmbiguity(
                                        f"Output {k} is connected to {element.outputs[k]} but the octave "
                                        f"downconverter is connected to {v}"
                                    )
                            else:
                                element.outputs[k] = v
                                _, element_outputs = betterproto.which_one_of(element, "element_outputs_one_of")
                                if isinstance(element_outputs, QuaConfigMicrowaveOutputPortReference):
                                    raise ConfigValidationException("Cannot connect octave to microwave output")
                                elif isinstance(element_outputs, QuaConfigMultipleOutputs):
                                    element_outputs.port_references[k] = v
                                else:
                                    element.multiple_outputs = QuaConfigMultipleOutputs(port_references={k: v})

    @staticmethod
    def set_non_existing_mixers_in_mix_input_elements(pb_config: QuaConfig) -> None:
        mixers_config = get_controller_pb_config(pb_config).mixers
        elements_config = get_logical_pb_config(pb_config).elements

        for element_name, element in elements_config.items():
            _, element_input = betterproto.which_one_of(element, "element_inputs_one_of")
            if isinstance(element_input, QuaConfigMixInputs):
                if (
                    element.intermediate_frequency
                ):  # This is here because in validation I saw that we can set an element without IF
                    if not element_input.mixer:
                        element_input.mixer = f"{element_name}_mixer_{uuid.uuid4().hex[:3]}"
                        # The uuid is just to make sure the mixer doesn't exist
                    if element_input.mixer not in mixers_config:
                        mixers_config[element_input.mixer] = QuaConfigMixerDec(
                            correction=[
                                QuaConfigCorrectionEntry(
                                    frequency=element.intermediate_frequency,
                                    frequency_negative=element.intermediate_frequency_negative,
                                    frequency_double=element.intermediate_frequency_double,
                                    lo_frequency=element_input.lo_frequency,
                                    lo_frequency_double=element_input.lo_frequency_double,
                                    correction=QuaConfigMatrix(v00=1, v01=0, v10=0, v11=1),
                                )
                            ]
                        )

    def deconvert(self, output_data: QuaConfig) -> FullQuaConfig:
        controller_config = get_controller_pb_config(output_data)
        logical_config = get_logical_pb_config(output_data)

        if controller_config.control_devices:
            controllers = {
                name: self.control_device_converter.deconvert(value)
                for name, value in controller_config.control_devices.items()
            }
        elif isinstance(controller_config, QuaConfigQuaConfigV1) and controller_config.controllers:
            controllers = {
                name: self.control_device_converter._deconvert_controller(value)
                for name, value in controller_config.controllers.items()
            }
        else:
            controllers = {}

        result: FullQuaConfig = {
            "controllers": controllers,
            "oscillators": {
                name: self.oscillator_converter.deconvert(oscillator)
                for name, oscillator in logical_config.oscillators.items()
            },
            "elements": {
                name: self.element_converter.deconvert(elem) for name, elem in logical_config.elements.items()
            },
            "pulses": {name: self.pulse_converter.deconvert(pulse) for name, pulse in logical_config.pulses.items()},
            "waveforms": {name: self.waveform_converter.deconvert(wf) for name, wf in logical_config.waveforms.items()},
            "digital_waveforms": {
                name: self._deconvert_digital_waveforms(wf) for name, wf in logical_config.digital_waveforms.items()
            },
            "integration_weights": {
                name: self.iw_converter.deconvert(iw) for name, iw in logical_config.integration_weights.items()
            },
            "mixers": {
                name: [self.mixer_correction_converter.deconvert(u) for u in value.correction]
                for name, value in controller_config.mixers.items()
            },
        }

        return result

    @staticmethod
    def _deconvert_digital_waveforms(digital_wave_form: QuaConfigDigitalWaveformDec) -> DigitalWaveformConfigType:
        temp_list: list[tuple[int, int]] = []
        for sample in digital_wave_form.samples:
            value = int(bool(sample.value))
            temp_list.append((value, sample.length))

        return {"samples": temp_list}
