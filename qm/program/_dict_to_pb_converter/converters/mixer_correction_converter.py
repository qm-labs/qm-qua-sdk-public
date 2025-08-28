from typing import Union, Optional, cast

from qm.type_hinting import Number
from qm.type_hinting.config_types import MixerConfigType
from qm.grpc.qua_config import QuaConfigMatrix, QuaConfigCorrectionEntry
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter


class MixerCorrectionConverter(BaseDictToPbConverter[MixerConfigType, QuaConfigCorrectionEntry]):
    def convert(self, input_data: MixerConfigType) -> QuaConfigCorrectionEntry:
        # Correction entries are stored in a list (refer to the function call). Unlike other values in the controller config,
        # lists do not support the 'upsert' operation. When a list is updated, it fully replaces the one set during init mode.
        # Therefore, the fields of QuaConfigCorrectionEntry can not be optional, as 'upsert' is not supported, only full replacement.

        default_schema: MixerConfigType = {"intermediate_frequency": 0, "lo_frequency": 0}
        data_with_defaults = self._apply_defaults(input_data, default_schema=default_schema)

        # In "correction entry", all fields must be explicitly provided by the user in update mode. In init mode,
        # the correction field is mandatory, while the frequency parameters are assigned default values if not specified.
        # Therefore, after applying default values, all three fields should always be set.
        self._validate_required_fields(
            data_with_defaults, ["intermediate_frequency", "lo_frequency", "correction"], "mixer correction entry"
        )

        correction = QuaConfigCorrectionEntry()

        correction.correction = QuaConfigMatrix(
            v00=data_with_defaults["correction"][0],
            v01=data_with_defaults["correction"][1],
            v10=data_with_defaults["correction"][2],
            v11=data_with_defaults["correction"][3],
        )

        correction.frequency_negative = data_with_defaults["intermediate_frequency"] < 0
        correction.frequency = abs(int(data_with_defaults["intermediate_frequency"]))
        if self._capabilities.supports_double_frequency:
            correction.frequency_double = abs(float(data_with_defaults["intermediate_frequency"]))

        correction.lo_frequency = int(data_with_defaults["lo_frequency"])
        if self._capabilities.supports_double_frequency:
            correction.lo_frequency_double = float(data_with_defaults["lo_frequency"])

        return correction

    def deconvert(self, output_data: QuaConfigCorrectionEntry) -> MixerConfigType:
        frequency: Optional[Union[int, float]]
        lo_frequency: Optional[Union[int, float]]

        if output_data.frequency_double:
            frequency = output_data.frequency_double
        else:
            frequency = output_data.frequency

        if output_data.frequency_negative is True:
            assert (
                frequency is not None
            )  # Mypy thinks it can be None, but it can't really (frequency has a default value)
            frequency = -frequency

        if output_data.lo_frequency_double:
            lo_frequency = output_data.lo_frequency_double
        else:
            lo_frequency = output_data.lo_frequency

        correction_as_dict = cast(
            MixerConfigType,
            {
                "intermediate_frequency": frequency,
                "lo_frequency": lo_frequency,
                "correction": self._convert_matrix(output_data.correction),
            },
        )
        return correction_as_dict

    @staticmethod
    def _convert_matrix(matrix: QuaConfigMatrix) -> tuple[Number, Number, Number, Number]:
        return matrix.v00, matrix.v01, matrix.v10, matrix.v11
