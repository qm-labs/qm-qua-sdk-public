import numbers
from typing import List, Tuple, Union, cast

from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.exceptions import ConfigValidationException
from qm.utils.list_compression_utils import split_list_to_chunks
from qm.type_hinting.config_types import IntegrationWeightConfigType
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter


class IntegrationWeightsConverter(
    BaseDictToPbConverter[IntegrationWeightConfigType, inc_qua_config_pb2.QuaConfig.IntegrationWeightDec]
):
    def convert(self, input_data: IntegrationWeightConfigType) -> inc_qua_config_pb2.QuaConfig.IntegrationWeightDec:
        return self.integration_weights_to_pb(input_data)

    @staticmethod
    def integration_weights_to_pb(
        data: IntegrationWeightConfigType,
    ) -> inc_qua_config_pb2.QuaConfig.IntegrationWeightDec:
        iw = inc_qua_config_pb2.QuaConfig.IntegrationWeightDec(
            cosine=build_iw_sample(data["cosine"]),
            sine=build_iw_sample(data["sine"]),
        )
        return iw

    def deconvert(self, output_data: inc_qua_config_pb2.QuaConfig.IntegrationWeightDec) -> IntegrationWeightConfigType:
        return {
            "cosine": [(s.value, s.length) for s in output_data.cosine],
            "sine": [(s.value, s.length) for s in output_data.sine],
        }


def build_iw_sample(
    data: Union[List[Tuple[float, int]], List[float]]
) -> List[inc_qua_config_pb2.QuaConfig.IntegrationWeightSample]:
    clean_data = _standardize_iw_data(data)
    return [inc_qua_config_pb2.QuaConfig.IntegrationWeightSample(value=s[0], length=int(s[1])) for s in clean_data]


def _standardize_iw_data(data: Union[List[Tuple[float, int]], List[float]]) -> List[Tuple[float, int]]:
    if len(data) == 0 or isinstance(data[0], (tuple, list)):
        to_return = []
        for x in data:
            x = cast(Tuple[float, int], x)
            to_return.append((x[0], x[1]))
        return to_return

    if isinstance(data[0], numbers.Number):
        if len(data) == 2:
            d0, d1 = cast(Tuple[float, int], data)
            return [(float(d0), int(d1))]

        data = cast(List[float], data)
        chunks = split_list_to_chunks([round(2**-15 * round(s * 2**15), 20) for s in data])
        new_data: List[Tuple[float, int]] = []
        for chunk in chunks:
            if chunk.accepts_different:
                new_data.extend([(float(u), 4) for u in chunk.data])
            else:
                new_data.append((chunk.first, 4 * len(chunk)))
        return new_data

    raise ConfigValidationException(f"Invalid IW data, data must be a list of numbers or 2-tuples, got {data}.")
