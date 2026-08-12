from collections.abc import Mapping, Collection

from qm.api.models.capabilities import QopCaps
from qm.utils.protobuf_utils import which_one_of
from qm.exceptions import ConfigValidationException
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm.config._waveforms import AnalogWaveform, DigitalWaveform, ArbitraryWaveform
from qm._config_converters._model_to_pb_converter.base_converter import BaseModelToPbConverter
from qm.config._waveforms._analog import (
    WaveformArray,
    ConstantWaveform,
    OverridableArbitraryWaveform,
    ArbitraryWaveformWithMaxError,
    ArbitraryWaveformWithSamplingRate,
)


class WaveformConverter(BaseModelToPbConverter[Collection[AnalogWaveform], Mapping[str, QuaConfig.WaveformDec]]):
    def convert(self, input_data: Collection[AnalogWaveform]) -> Mapping[str, QuaConfig.WaveformDec]:
        return {waveform.name: self._convert_single(waveform) for waveform in input_data}

    def _convert_single(self, input_data: AnalogWaveform) -> QuaConfig.WaveformDec:
        if isinstance(input_data, ArbitraryWaveform):
            arbitrary = QuaConfig.ArbitraryWaveformDec(samples=input_data.samples)
            if isinstance(input_data, OverridableArbitraryWaveform):
                arbitrary.isOverridable = True
            elif isinstance(input_data, ArbitraryWaveformWithMaxError):
                arbitrary.maxAllowedError.value = input_data.max_allowed_error
            elif isinstance(input_data, ArbitraryWaveformWithSamplingRate):
                arbitrary.samplingRate.value = input_data.sampling_rate
            else:
                raise ConfigValidationException(f"Unknown waveform type - {type(input_data)}")
            return QuaConfig.WaveformDec(arbitrary=arbitrary)

        elif isinstance(input_data, WaveformArray):
            self._capabilities.validate([QopCaps.waveform_array])
            array = QuaConfig.WaveformArrayDec(
                samples_array=[QuaConfig.WaveformSamples(samples=samples) for samples in input_data.samples_array]
            )
            return QuaConfig.WaveformDec(array=array)

        elif isinstance(input_data, ConstantWaveform):
            constant = QuaConfig.ConstantWaveformDec(sample=input_data.sample)
            return QuaConfig.WaveformDec(constant=constant)

        else:
            raise Exception(f"Unknown waveform type - {type(input_data)}")

    def deconvert(self, output_data: Mapping[str, QuaConfig.WaveformDec]) -> Collection[AnalogWaveform]:
        return tuple(self._deconvert_single(value, name) for name, value in output_data.items())

    @staticmethod
    def _deconvert_single(output_data: QuaConfig.WaveformDec, name: str) -> AnalogWaveform:
        _, curr_waveform = which_one_of(output_data, "waveform_oneof")
        if isinstance(curr_waveform, QuaConfig.ArbitraryWaveformDec):
            samples = list(curr_waveform.samples)
            if curr_waveform.isOverridable:
                return OverridableArbitraryWaveform(samples=samples, name=name)
            if curr_waveform.HasField("maxAllowedError"):
                return ArbitraryWaveformWithMaxError(
                    samples=samples, name=name, max_allowed_error=curr_waveform.maxAllowedError.value
                )
            if curr_waveform.HasField("samplingRate"):
                return ArbitraryWaveformWithSamplingRate(
                    samples=samples, name=name, sampling_rate=curr_waveform.samplingRate.value
                )
            raise Exception(f"Unknown waveform type - {type(curr_waveform)}")

        elif isinstance(curr_waveform, QuaConfig.ConstantWaveformDec):
            return ConstantWaveform(sample=curr_waveform.sample, name=name)

        elif isinstance(curr_waveform, QuaConfig.WaveformArrayDec):
            return WaveformArray(
                samples_array=[list(samples.samples) for samples in curr_waveform.samples_array],
                name=name,
            )
        else:
            raise ConfigValidationException(f"Unknown waveform type - {type(curr_waveform)}")


class DigitalWaveformConverter(
    BaseModelToPbConverter[Collection[DigitalWaveform], Mapping[str, QuaConfig.DigitalWaveformDec]]
):
    def convert(self, input_data: Collection[DigitalWaveform]) -> Mapping[str, QuaConfig.DigitalWaveformDec]:
        return {waveform.name: self._convert_single(waveform) for waveform in input_data}

    @staticmethod
    def _convert_single(input_data: DigitalWaveform) -> QuaConfig.DigitalWaveformDec:
        return QuaConfig.DigitalWaveformDec(
            samples=[
                QuaConfig.DigitalWaveformSample(value=bool(value), length=length)
                for value, length in input_data.samples
            ]
        )

    def deconvert(self, output_data: Mapping[str, QuaConfig.DigitalWaveformDec]) -> Collection[DigitalWaveform]:
        return tuple(self._deconvert_single(value, name=name) for name, value in output_data.items())

    @staticmethod
    def _deconvert_single(output_data: QuaConfig.DigitalWaveformDec, name: str) -> DigitalWaveform:
        return DigitalWaveform(
            samples=[(bool(sample.value), sample.length) for sample in output_data.samples], name=name
        )
