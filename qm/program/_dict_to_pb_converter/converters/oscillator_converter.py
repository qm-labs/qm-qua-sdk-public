from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.utils.protobuf_utils import serialized_on_wire
from qm.type_hinting.config_types import OscillatorConfigType
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter


class OscillatorConverter(BaseDictToPbConverter[OscillatorConfigType, inc_qua_config_pb2.QuaConfig.Oscillator]):
    def convert(self, input_data: OscillatorConfigType) -> inc_qua_config_pb2.QuaConfig.Oscillator:
        return self.oscillator_to_pb(input_data)

    def oscillator_to_pb(self, data: OscillatorConfigType) -> inc_qua_config_pb2.QuaConfig.Oscillator:
        oscillator = inc_qua_config_pb2.QuaConfig.Oscillator()
        if "intermediate_frequency" in data:
            oscillator.intermediateFrequency.value = int(data["intermediate_frequency"])
            if self._capabilities.supports_double_frequency:
                oscillator.intermediateFrequencyDouble = float(data["intermediate_frequency"])

        if "mixer" in data:
            oscillator.mixer.CopyFrom(inc_qua_config_pb2.QuaConfig.MixerRef(mixer=data["mixer"]))
            oscillator.mixer.loFrequency = int(data.get("lo_frequency", 0))
            if self._capabilities.supports_double_frequency:
                oscillator.mixer.loFrequencyDouble = float(data.get("lo_frequency", 0.0))

        return oscillator

    def deconvert(self, output_data: inc_qua_config_pb2.QuaConfig.Oscillator) -> OscillatorConfigType:
        oscillator_config_data: OscillatorConfigType = {}
        if output_data.intermediateFrequencyDouble:
            freq = output_data.intermediateFrequencyDouble
            oscillator_config_data["intermediate_frequency"] = freq
        elif output_data.intermediateFrequency:
            freq = int(output_data.intermediateFrequency.value)
            oscillator_config_data["intermediate_frequency"] = freq
        if serialized_on_wire(output_data.mixer):
            if output_data.mixer.mixer:
                oscillator_config_data["mixer"] = output_data.mixer.mixer
            if output_data.mixer.loFrequencyDouble:
                lo_freq = output_data.mixer.loFrequencyDouble
                oscillator_config_data["lo_frequency"] = float(lo_freq)
            elif output_data.mixer.loFrequency:
                lo_freq = output_data.mixer.loFrequency
                oscillator_config_data["lo_frequency"] = int(lo_freq)
        return oscillator_config_data
