from dataclasses import dataclass
from collections.abc import Mapping, Collection

from qm.exceptions import ConfigValidationException
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm.config._waveforms._analog import AnalogWaveform
from qm.api.models.capabilities import ServerCapabilities
from qm.config._pulses._pulse import Pulse, DualPulse, SinglePulse, DigitalPulse
from qm._config_converters._model_to_pb_converter.base_converter import BaseModelToPbConverter
from qm._config_converters._model_to_pb_converter.converters.integration_weights_converter import (
    IntegrationWeightsConverter,
)
from qm._config_converters._model_to_pb_converter.converters.waveform_converter import (
    WaveformConverter,
    DigitalWaveformConverter,
)


@dataclass
class PulsesData:
    pulses: Mapping[str, QuaConfig.PulseDec]
    waveforms: Mapping[str, QuaConfig.WaveformDec]
    digital_waveforms: Mapping[str, QuaConfig.DigitalWaveformDec]
    integration_weights: Mapping[str, QuaConfig.IntegrationWeightDec]


class PulseConverter(BaseModelToPbConverter[Collection[Pulse], PulsesData]):
    def __init__(self, capabilities: ServerCapabilities, init_mode: bool) -> None:
        super().__init__(capabilities, init_mode)
        self._integration_weights_converter = IntegrationWeightsConverter(capabilities, init_mode)
        self._waveform_converter = WaveformConverter(capabilities, init_mode)
        self._digital_waveform_converter = DigitalWaveformConverter(capabilities, init_mode)

    def convert(self, input_data: Collection[Pulse]) -> PulsesData:
        # todo - validate uniqueness of pulses
        integration_weights: dict[str, QuaConfig.IntegrationWeightDec] = {}
        waveforms: dict[str, QuaConfig.WaveformDec] = {}
        digital_waveforms: dict[str, QuaConfig.DigitalWaveformDec] = {}
        pulses: dict[str, QuaConfig.PulseDec] = {}
        for pulse in input_data:
            temp = QuaConfig.PulseDec(length=pulse.length)
            if not isinstance(pulse, DigitalPulse):
                curr_wf_ref_dict, wf_data = self._convert_waveform(pulse)
                waveforms.update(wf_data)
                temp.waveforms.update(curr_wf_ref_dict)
            if pulse.digital_waveform is not None:
                temp.digitalMarker.value = pulse.digital_waveform.name
                curr_digital_waveforms = self._digital_waveform_converter.convert([pulse.digital_waveform])
                digital_waveforms.update(curr_digital_waveforms)  # todo - make sure update is fine (no bad overlap)

            temp.integrationWeights.update({k: v.name for k, v in pulse.integration_weights.items()})
            curr_integration_weights = self._integration_weights_converter.convert(pulse.integration_weights.values())
            integration_weights.update(curr_integration_weights)  # todo - make sure update is fine (no bad overlap)
            if pulse.integration_weights:
                temp.operation = QuaConfig.PulseDec.Operation.MEASUREMENT
            else:
                temp.operation = QuaConfig.PulseDec.Operation.CONTROL
            pulses[pulse.name] = temp
        return PulsesData(
            integration_weights=integration_weights,
            waveforms=waveforms,
            digital_waveforms=digital_waveforms,
            pulses=pulses,
        )

    def deconvert(self, output_data: PulsesData) -> Collection[Pulse]:
        # todo - understand why originally the where was "if "length" in data..."
        analog_waveforms = {wf.name: wf for wf in self._waveform_converter.deconvert(output_data.waveforms)}
        digital_waveforms = {
            dwf.name: dwf for dwf in self._digital_waveform_converter.deconvert(output_data.digital_waveforms)
        }
        all_integration_weights = {
            iw.name: iw for iw in self._integration_weights_converter.deconvert(output_data.integration_weights)
        }

        pulses: tuple[Pulse, ...] = tuple()

        for name, data in output_data.pulses.items():
            length = data.length
            waveforms = self._deconvert_waveform(data.waveforms, analog_waveforms)
            digital_waveform = digital_waveforms[data.digitalMarker.value] if data.digitalMarker.value else None
            iw_dict = data.integrationWeights
            integration_weights = {iw_name: all_integration_weights[iw_ref] for iw_name, iw_ref in iw_dict.items()}
            if isinstance(waveforms, AnalogWaveform):
                pulses += (
                    SinglePulse(
                        name=name,
                        length=length,
                        waveform=waveforms,
                        digital_waveform=digital_waveform,
                        integration_weights=integration_weights,
                    ),
                )
            elif isinstance(waveforms, tuple):
                pulses += (
                    DualPulse(
                        name=name,
                        length=length,
                        waveform_i=waveforms[0],
                        waveform_q=waveforms[1],
                        digital_waveform=digital_waveform,
                        integration_weights=integration_weights,
                    ),
                )
            elif waveforms is None and digital_waveform is not None:
                pulses += (
                    DigitalPulse(
                        name=name,
                        length=length,
                        digital_waveform=digital_waveform,
                    ),
                )
            else:
                raise ConfigValidationException(f"Invalid operation {data.operation}")
        return pulses

    @staticmethod
    def _deconvert_waveform(
        data_dict: Mapping[str, str],
        analog_waveforms: Mapping[str, AnalogWaveform],
    ) -> AnalogWaveform | tuple[AnalogWaveform, AnalogWaveform] | None:
        if "single" in data_dict:
            return analog_waveforms[data_dict["single"]]
        elif "I" in data_dict and "Q" in data_dict:
            return analog_waveforms[data_dict["I"]], analog_waveforms[data_dict["Q"]]
        elif not data_dict:
            return None
        else:
            raise ConfigValidationException("Invalid waveform type")

    def _convert_waveform(self, output_data: Pulse) -> tuple[dict[str, str], Mapping[str, QuaConfig.WaveformDec]]:
        if isinstance(output_data, SinglePulse):
            wf_data = self._waveform_converter.convert([output_data.waveform])
            return self._convert_single_wf(output_data), wf_data
        elif isinstance(output_data, DualPulse):
            wf_data = self._waveform_converter.convert([output_data.waveform_i, output_data.waveform_q])
            return self._convert_dual_wf(output_data), wf_data
        else:
            raise ConfigValidationException(f"Invalid waveform type - {type(output_data)}")

    @staticmethod
    def _convert_single_wf(output_data: SinglePulse) -> dict[str, str]:
        return {"single": output_data.waveform.name}

    @staticmethod
    def _convert_dual_wf(output_data: DualPulse) -> dict[str, str]:
        return {"I": output_data.waveform_i.name, "Q": output_data.waveform_q.name}
