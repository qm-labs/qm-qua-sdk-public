from typing import Union, Literal, cast

from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.utils.protobuf_utils import assign_map
from qm.exceptions import ConfigValidationException
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter
from qm.type_hinting.config_types import PulseConfigType, MixWaveformConfigType, SingleWaveformConfigType


class PulseConverter(BaseDictToPbConverter[PulseConfigType, inc_qua_config_pb2.QuaConfig.PulseDec]):
    def convert(self, input_data: PulseConfigType) -> inc_qua_config_pb2.QuaConfig.PulseDec:
        return self.pulse_to_pb(input_data)

    @staticmethod
    def pulse_to_pb(data: PulseConfigType) -> inc_qua_config_pb2.QuaConfig.PulseDec:
        pulse = inc_qua_config_pb2.QuaConfig.PulseDec()

        if "length" in data:
            pulse.length = int(data["length"])

        if data["operation"] == "control":
            pulse.operation = inc_qua_config_pb2.QuaConfig.PulseDec.Operation.CONTROL
        elif data["operation"] == "measurement":
            pulse.operation = inc_qua_config_pb2.QuaConfig.PulseDec.Operation.MEASUREMENT
        else:
            raise ConfigValidationException(f"Invalid operation {data['operation']}")

        if "digital_marker" in data:
            pulse.digitalMarker.value = data["digital_marker"]

        if "integration_weights" in data:
            for k, v in data["integration_weights"].items():
                pulse.integrationWeights[k] = v

        if "waveforms" in data:
            assign_map(pulse.waveforms, {k_: str(v_) for k_, v_ in data["waveforms"].items()})
        return pulse

    def deconvert(self, output_data: inc_qua_config_pb2.QuaConfig.PulseDec) -> PulseConfigType:
        operation = cast(inc_qua_config_pb2.QuaConfig.PulseDec.Operation, output_data.operation)
        temp_dict: PulseConfigType = {
            "length": output_data.length,
            "waveforms": cast(Union[SingleWaveformConfigType, MixWaveformConfigType], output_data.waveforms),
            "integration_weights": output_data.integrationWeights,
            "operation": cast(
                Literal["measurement", "control"],
                inc_qua_config_pb2.QuaConfig.PulseDec.Operation.Name(operation).lower(),
            ),
        }
        if isinstance(output_data.digitalMarker, str):
            temp_dict["digital_marker"] = output_data.digitalMarker
        return temp_dict
