import betterproto

from qm.type_hinting.config_types import OscillatorConfigType
from qm.grpc.qua_config import QuaConfigMixerRef, QuaConfigOscillator
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter


class OscillatorConverter(BaseDictToPbConverter[OscillatorConfigType, QuaConfigOscillator]):
    def convert(self, input_data: OscillatorConfigType) -> QuaConfigOscillator:
        return self.oscillator_to_pb(input_data)

    def oscillator_to_pb(self, data: OscillatorConfigType) -> QuaConfigOscillator:
        oscillator = QuaConfigOscillator()
        if "intermediate_frequency" in data:
            oscillator.intermediate_frequency = int(data["intermediate_frequency"])
            if self._capabilities.supports_double_frequency:
                oscillator.intermediate_frequency_double = float(data["intermediate_frequency"])

        if "mixer" in data:
            oscillator.mixer = QuaConfigMixerRef(mixer=data["mixer"])
            oscillator.mixer.lo_frequency = int(data.get("lo_frequency", 0))
            if self._capabilities.supports_double_frequency:
                oscillator.mixer.lo_frequency_double = float(data.get("lo_frequency", 0.0))

        return oscillator

    def deconvert(self, output_data: QuaConfigOscillator) -> OscillatorConfigType:
        oscillator_config_data: OscillatorConfigType = {}
        if output_data.intermediate_frequency_double:
            freq = output_data.intermediate_frequency_double
            oscillator_config_data["intermediate_frequency"] = freq
        elif output_data.intermediate_frequency:
            freq = int(output_data.intermediate_frequency)
            oscillator_config_data["intermediate_frequency"] = freq
        if betterproto.serialized_on_wire(output_data.mixer):
            if output_data.mixer.mixer:
                oscillator_config_data["mixer"] = output_data.mixer.mixer
            if output_data.mixer.lo_frequency_double:
                lo_freq = output_data.mixer.lo_frequency_double
                oscillator_config_data["lo_frequency"] = float(lo_freq)
            elif output_data.mixer.lo_frequency:
                lo_freq = output_data.mixer.lo_frequency
                oscillator_config_data["lo_frequency"] = int(lo_freq)
        return oscillator_config_data
