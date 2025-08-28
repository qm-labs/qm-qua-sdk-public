from typing import Union, Literal, cast

from qm.exceptions import ConfigValidationException
from qm.grpc.qua_config import QuaConfigPulseDec, QuaConfigPulseDecOperation
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter
from qm.type_hinting.config_types import PulseConfigType, MixWaveformConfigType, SingleWaveformConfigType


class PulseConverter(BaseDictToPbConverter[PulseConfigType, QuaConfigPulseDec]):
    def convert(self, input_data: PulseConfigType) -> QuaConfigPulseDec:
        return self.pulse_to_pb(input_data)

    @staticmethod
    def pulse_to_pb(data: PulseConfigType) -> QuaConfigPulseDec:
        pulse = QuaConfigPulseDec()

        if "length" in data:
            pulse.length = int(data["length"])

        if data["operation"] == "control":
            pulse.operation = QuaConfigPulseDecOperation.CONTROL
        elif data["operation"] == "measurement":
            pulse.operation = QuaConfigPulseDecOperation.MEASUREMENT
        else:
            raise ConfigValidationException(f"Invalid operation {data['operation']}")

        if "digital_marker" in data:
            pulse.digital_marker = data["digital_marker"]

        if "integration_weights" in data:
            for k, v in data["integration_weights"].items():
                pulse.integration_weights[k] = v

        if "waveforms" in data:
            pulse.waveforms = {k_: str(v_) for k_, v_ in data["waveforms"].items()}
        return pulse

    def deconvert(self, output_data: QuaConfigPulseDec) -> PulseConfigType:
        temp_dict: PulseConfigType = {
            "length": output_data.length,
            "waveforms": cast(Union[SingleWaveformConfigType, MixWaveformConfigType], output_data.waveforms),
            "integration_weights": output_data.integration_weights,
            "operation": cast(
                Literal["measurement", "control"],
                QuaConfigPulseDecOperation(output_data.operation).name.lower(),  # type: ignore[union-attr]
            ),
        }
        if isinstance(output_data.digital_marker, str):
            temp_dict["digital_marker"] = output_data.digital_marker
        return temp_dict
