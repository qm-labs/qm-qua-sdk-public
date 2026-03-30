from typing import Union

from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.api.models.capabilities import QopCaps
from qm.utils.protobuf_utils import which_one_of, proto_repeated_to_list
from qm.program._validate_config_schema import validate_arbitrary_waveform
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter
from qm.type_hinting.config_types import (
    WaveformArrayConfigType,
    ConstantWaveformConfigType,
    ArbitraryWaveformConfigType,
)

WaveformDictConfigTypes = Union[ConstantWaveformConfigType, ArbitraryWaveformConfigType, WaveformArrayConfigType]


class WaveformConverter(BaseDictToPbConverter[WaveformDictConfigTypes, inc_qua_config_pb2.QuaConfig.WaveformDec]):
    def convert(self, input_data: WaveformDictConfigTypes) -> inc_qua_config_pb2.QuaConfig.WaveformDec:
        if input_data["type"] == "constant":
            return self.constant_waveform_to_protobuf(input_data)
        elif input_data["type"] == "arbitrary":
            return self.arbitrary_waveform_to_protobuf(input_data)
        elif input_data["type"] == "array":
            return self.waveform_array_to_protobuf(input_data)
        else:
            raise ValueError("Unknown waveform type")

    @staticmethod
    def constant_waveform_to_protobuf(data: ConstantWaveformConfigType) -> inc_qua_config_pb2.QuaConfig.WaveformDec:
        return inc_qua_config_pb2.QuaConfig.WaveformDec(
            constant=inc_qua_config_pb2.QuaConfig.ConstantWaveformDec(sample=data["sample"])
        )

    @staticmethod
    def arbitrary_waveform_to_protobuf(data: ArbitraryWaveformConfigType) -> inc_qua_config_pb2.QuaConfig.WaveformDec:
        wf = inc_qua_config_pb2.QuaConfig.WaveformDec()

        is_overridable = data.get("is_overridable", False)
        has_max_allowed_error = "max_allowed_error" in data
        has_sampling_rate = "sampling_rate" in data
        validate_arbitrary_waveform(is_overridable, has_max_allowed_error, has_sampling_rate)

        wf.arbitrary.CopyFrom(
            inc_qua_config_pb2.QuaConfig.ArbitraryWaveformDec(samples=data["samples"], isOverridable=is_overridable)
        )

        if has_max_allowed_error:
            wf.arbitrary.maxAllowedError.value = data["max_allowed_error"]
        elif has_sampling_rate:
            wf.arbitrary.samplingRate.value = data["sampling_rate"]
        elif not is_overridable:
            wf.arbitrary.maxAllowedError.value = 1e-4
        return wf

    def waveform_array_to_protobuf(
        self,
        data: WaveformArrayConfigType,
    ) -> inc_qua_config_pb2.QuaConfig.WaveformDec:
        self._capabilities.validate({QopCaps.waveform_array})

        return inc_qua_config_pb2.QuaConfig.WaveformDec(
            array=inc_qua_config_pb2.QuaConfig.WaveformArrayDec(
                samples_array=[
                    inc_qua_config_pb2.QuaConfig.WaveformSamples(samples=list(samples))
                    for samples in data["samples_array"]
                ]
            )
        )

    def deconvert(self, output_data: inc_qua_config_pb2.QuaConfig.WaveformDec) -> WaveformDictConfigTypes:
        _, curr_waveform = which_one_of(output_data, "waveform_oneof")
        if isinstance(curr_waveform, inc_qua_config_pb2.QuaConfig.ArbitraryWaveformDec):
            arbitrary_waveform_dict: ArbitraryWaveformConfigType = {
                "type": "arbitrary",
                "samples": proto_repeated_to_list(curr_waveform.samples),
                "is_overridable": curr_waveform.isOverridable,
            }
            if curr_waveform.HasField("maxAllowedError"):
                arbitrary_waveform_dict["max_allowed_error"] = curr_waveform.maxAllowedError.value
            if curr_waveform.HasField("samplingRate"):
                arbitrary_waveform_dict["sampling_rate"] = curr_waveform.samplingRate.value
            return arbitrary_waveform_dict

        elif isinstance(curr_waveform, inc_qua_config_pb2.QuaConfig.ConstantWaveformDec):
            constant_waveform_dict: ConstantWaveformConfigType = {
                "type": "constant",
                "sample": curr_waveform.sample,
            }
            return constant_waveform_dict

        elif isinstance(curr_waveform, inc_qua_config_pb2.QuaConfig.WaveformArrayDec):
            waveform_array_dict: WaveformArrayConfigType = {
                "type": "array",
                "samples_array": [waveform_samples.samples for waveform_samples in curr_waveform.samples_array],
            }
            return waveform_array_dict

        else:
            raise Exception(f"Unknown waveform type - {type(curr_waveform)}")
