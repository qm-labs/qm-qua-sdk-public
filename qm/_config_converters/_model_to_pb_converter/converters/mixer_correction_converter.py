from collections.abc import Mapping, Collection

from qm.exceptions import ConfigValidationException
from qm.config._elements._analog_inputs import Mixer
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm._config_converters._model_to_pb_converter.base_converter import BaseModelToPbConverter


class MixerCorrectionConverter(BaseModelToPbConverter[Collection[Mixer], Mapping[str, QuaConfig.MixerDec]]):
    def convert(self, input_data: Collection[Mixer]) -> Mapping[str, QuaConfig.MixerDec]:
        # todo assert uniqueness of the mixers
        return {data.name: self._convert_single(data) for data in input_data}

    def _convert_single(self, input_data: Mixer) -> QuaConfig.MixerDec:
        entries = []
        if (not self._init_mode) and input_data.data_has_nones:
            raise ConfigValidationException("Missing keys for some of the data")

        lo_if_to_correction = input_data.lo_if_to_correction_no_none
        for (lo_freq, if_freq), correction in lo_if_to_correction.items():
            correction_mat = QuaConfig.Matrix(
                v00=correction[0],
                v01=correction[1],
                v10=correction[2],
                v11=correction[3],
            )
            entry = QuaConfig.CorrectionEntry(
                frequency=abs(int(if_freq)),
                frequencyNegative=if_freq < 0,
            )
            entry.correction.CopyFrom(correction_mat)
            entry.loFrequency = int(lo_freq)
            if self._capabilities.supports_double_frequency:
                entry.frequencyDouble = abs(float(if_freq))
                entry.loFrequencyDouble = float(lo_freq)
            entries.append(entry)
        to_return = QuaConfig.MixerDec(correction=entries)
        return to_return

    def deconvert(self, output_data: Mapping[str, QuaConfig.MixerDec]) -> Collection[Mixer]:
        return tuple(self._deconvert_single(data, name) for name, data in output_data.items())

    def _deconvert_single(self, output_data: QuaConfig.MixerDec, name: str) -> Mixer:
        correction_mapping: dict[tuple[float | None, float | None], tuple[float, float, float, float]] = {}
        for entry in output_data.correction:
            if entry.frequencyDouble:
                frequency = entry.frequencyDouble
            else:
                frequency = entry.frequency

            if entry.frequencyNegative is True:
                assert (
                    frequency is not None
                )  # Mypy thinks it can be None, but it can't really (frequency has a default value)
                frequency = -frequency

            if entry.frequencyDouble:
                lo_frequency = entry.loFrequencyDouble
            else:
                lo_frequency = entry.loFrequency
            correction_mapping[lo_frequency, frequency] = self._convert_matrix(entry.correction)

        return Mixer(
            name=name,
            lo_if_to_correction=correction_mapping,
        )

    @staticmethod
    def _convert_matrix(matrix: QuaConfig.Matrix) -> tuple[float, float, float, float]:
        return matrix.v00, matrix.v01, matrix.v10, matrix.v11
