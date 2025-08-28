from typing import Union

import betterproto

from qm.api.models.capabilities import QopCaps
from qm.program._validate_config_schema import validate_arbitrary_waveform
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter
from qm.type_hinting.config_types import (
    WaveformArrayConfigType,
    ConstantWaveformConfigType,
    ArbitraryWaveformConfigType,
)
from qm.grpc.qua_config import (
    QuaConfigWaveformDec,
    QuaConfigWaveformSamples,
    QuaConfigWaveformArrayDec,
    QuaConfigConstantWaveformDec,
    QuaConfigArbitraryWaveformDec,
)

WaveformDictConfigTypes = Union[ConstantWaveformConfigType, ArbitraryWaveformConfigType, WaveformArrayConfigType]


class WaveformConverter(BaseDictToPbConverter[WaveformDictConfigTypes, QuaConfigWaveformDec]):
    def convert(self, input_data: WaveformDictConfigTypes) -> QuaConfigWaveformDec:
        if input_data["type"] == "constant":
            return self.constant_waveform_to_protobuf(input_data)
        elif input_data["type"] == "arbitrary":
            return self.arbitrary_waveform_to_protobuf(input_data)
        elif input_data["type"] == "array":
            return self.waveform_array_to_protobuf(input_data)
        else:
            raise ValueError("Unknown waveform type")

    @staticmethod
    def constant_waveform_to_protobuf(data: ConstantWaveformConfigType) -> QuaConfigWaveformDec:
        return QuaConfigWaveformDec(constant=QuaConfigConstantWaveformDec(sample=data["sample"]))

    @staticmethod
    def arbitrary_waveform_to_protobuf(data: ArbitraryWaveformConfigType) -> QuaConfigWaveformDec:
        wf = QuaConfigWaveformDec()

        is_overridable = data.get("is_overridable", False)
        has_max_allowed_error = "max_allowed_error" in data
        has_sampling_rate = "sampling_rate" in data
        validate_arbitrary_waveform(is_overridable, has_max_allowed_error, has_sampling_rate)

        wf.arbitrary = QuaConfigArbitraryWaveformDec(samples=data["samples"], is_overridable=is_overridable)

        if has_max_allowed_error:
            wf.arbitrary.max_allowed_error = data["max_allowed_error"]
        elif has_sampling_rate:
            wf.arbitrary.sampling_rate = data["sampling_rate"]
        elif not is_overridable:
            wf.arbitrary.max_allowed_error = 1e-4
        return wf

    def waveform_array_to_protobuf(
        self,
        data: WaveformArrayConfigType,
    ) -> QuaConfigWaveformDec:
        self._capabilities.validate({QopCaps.waveform_array})

        return QuaConfigWaveformDec(
            array=QuaConfigWaveformArrayDec(
                samples_array=[QuaConfigWaveformSamples(list(samples)) for samples in data["samples_array"]]
            )
        )

    def deconvert(self, output_data: QuaConfigWaveformDec) -> WaveformDictConfigTypes:
        _, curr_waveform = betterproto.which_one_of(output_data, "waveform_oneof")
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
            return arbitrary_waveform_dict

        elif isinstance(curr_waveform, QuaConfigConstantWaveformDec):
            constant_waveform_dict: ConstantWaveformConfigType = {
                "type": "constant",
                "sample": curr_waveform.sample,
            }
            return constant_waveform_dict

        elif isinstance(curr_waveform, QuaConfigWaveformArrayDec):
            waveform_array_dict: WaveformArrayConfigType = {
                "type": "array",
                "samples_array": [waveform_samples.samples for waveform_samples in curr_waveform.samples_array],
            }
            return waveform_array_dict

        else:
            raise Exception(f"Unknown waveform type - {type(curr_waveform)}")
