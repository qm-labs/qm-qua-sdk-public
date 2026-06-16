from collections.abc import Mapping, Collection

from qm.config._pulses import IntegrationWeights
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm._config_converters._model_to_pb_converter.base_converter import BaseModelToPbConverter


class IntegrationWeightsConverter(
    BaseModelToPbConverter[Collection[IntegrationWeights], Mapping[str, QuaConfig.IntegrationWeightDec]]
):
    def convert(self, input_data: Collection[IntegrationWeights]) -> Mapping[str, QuaConfig.IntegrationWeightDec]:
        return {data.name: self._convert_single(data) for data in input_data}

    @staticmethod
    def _convert_single(data: IntegrationWeights) -> QuaConfig.IntegrationWeightDec:
        return QuaConfig.IntegrationWeightDec(
            cosine=_build_iw_sample(data.cosine),
            sine=_build_iw_sample(data.sine),
        )

    def deconvert(self, output_data: Mapping[str, QuaConfig.IntegrationWeightDec]) -> Collection[IntegrationWeights]:
        return tuple(self._deconvert_single(data, name) for name, data in output_data.items())

    @staticmethod
    def _deconvert_single(output_data: QuaConfig.IntegrationWeightDec, name: str) -> IntegrationWeights:
        return IntegrationWeights(
            cosine=[(s.value, s.length) for s in output_data.cosine],
            sine=[(s.value, s.length) for s in output_data.sine],
            name=name,
        )


def _build_iw_sample(data: list[tuple[float, int]]) -> list[QuaConfig.IntegrationWeightSample]:
    return [QuaConfig.IntegrationWeightSample(value=s[0], length=int(s[1])) for s in data]
