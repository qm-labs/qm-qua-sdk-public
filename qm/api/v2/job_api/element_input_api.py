from typing import Type, Tuple, Union, Optional, overload

from qm.grpc.qm.grpc.v2 import job_api_pb2
from qm.api.v2.job_api.generic_apis import ElementGenericApi
from qm.grpc.qm.pb import inc_qm_api_pb2, inc_qua_config_pb2

InputConfigType = Union[
    inc_qua_config_pb2.QuaConfig.SingleInput,
    inc_qua_config_pb2.QuaConfig.MixInputs,
    inc_qua_config_pb2.QuaConfig.SingleInputCollection,
    inc_qua_config_pb2.QuaConfig.MultipleInputs,
    inc_qua_config_pb2.QuaConfig.MicrowaveInputPortReference,
    None,
]


class UnknownElementType(ValueError):
    pass


class ElementInputApi(ElementGenericApi):
    pass


class NoInputApi(ElementInputApi):
    pass


class MultipleInputsApi(ElementInputApi):
    pass


class SingleInputCollectionApi(ElementInputApi):
    pass


class MixInputsApi(ElementInputApi):
    def set_correction(self, correction: Tuple[float, float, float, float]) -> None:
        matrix = inc_qm_api_pb2.Matrix(v00=correction[0], v01=correction[1], v10=correction[2], v11=correction[3])
        request = job_api_pb2.SetMatrixCorrectionRequest(job_id=self._id, qe=self._element_id, correction=matrix)
        self._run(self._stub.SetMatrixCorrection, request, timeout=self._timeout)

    def get_correction(self) -> Tuple[float, float, float, float]:
        request = job_api_pb2.GetMatrixCorrectionRequest(job_id=self._id, qe=self._element_id)
        correction: inc_qm_api_pb2.Matrix = self._run(
            self._stub.GetMatrixCorrection, request, timeout=self._timeout
        ).correction
        return correction.v00, correction.v01, correction.v10, correction.v11

    def set_dc_offsets(self, i_offset: Optional[float] = None, q_offset: Optional[float] = None) -> None:
        request = job_api_pb2.SetOutputDcOffsetRequest(
            job_id=self._id, qe=self._element_id, mix_inputs=job_api_pb2.MixInputsDcOffset(I=i_offset, Q=q_offset)
        )
        self._run(self._stub.SetOutputDcOffset, request, timeout=self._timeout)

    def get_dc_offsets(self) -> Tuple[float, float]:
        request = job_api_pb2.GetOutputDcOffsetRequest(job_id=self._id, qe=self._element_id)
        response: job_api_pb2.GetOutputDcOffsetResponse.GetOutputDcOffsetResponseSuccess = self._run(
            self._stub.GetOutputDcOffset, request, timeout=self._timeout
        )
        i, q = response.mix_inputs.I, response.mix_inputs.Q
        if i is None or q is None:
            raise ValueError("Mixed DC offsets are not set")
        return i, q


class SingleInputApi(ElementInputApi):
    def set_dc_offset(self, offset: float) -> None:
        request = job_api_pb2.SetOutputDcOffsetRequest(
            job_id=self._id, qe=self._element_id, single_input=job_api_pb2.SingleInputDcOffset(offset=offset)
        )
        self._run(self._stub.SetOutputDcOffset, request, timeout=self._timeout)

    def get_dc_offset(self) -> float:
        request = job_api_pb2.GetOutputDcOffsetRequest(job_id=self._id, qe=self._element_id)
        response: job_api_pb2.GetOutputDcOffsetResponse.GetOutputDcOffsetResponseSuccess = self._run(
            self._stub.GetOutputDcOffset, request, timeout=self._timeout
        )
        return response.single_input.offset


class MwInputApi(ElementInputApi):
    def set_converter_frequency(self, frequency_hz: float, set_also_output: bool = True) -> None:
        request = job_api_pb2.SetOscillatorFrequencyRequest(
            job_id=self._id,
            qe=self._element_id,
            new_frequency_hz=frequency_hz,
            update_component=(
                job_api_pb2.SetOscillatorFrequencyRequest.UpdateComponentSelection.both
                if set_also_output
                else job_api_pb2.SetOscillatorFrequencyRequest.UpdateComponentSelection.upconverter
            ),
        )
        self._run(self._stub.SetOscillatorFrequency, request, timeout=self._timeout)


@overload
def create_element_input_class(input_config: inc_qua_config_pb2.QuaConfig.SingleInput) -> Type[SingleInputApi]:
    pass


@overload
def create_element_input_class(input_config: inc_qua_config_pb2.QuaConfig.MixInputs) -> Type[MixInputsApi]:
    pass


@overload
def create_element_input_class(
    input_config: inc_qua_config_pb2.QuaConfig.SingleInputCollection,
) -> Type[SingleInputCollectionApi]:
    pass


@overload
def create_element_input_class(input_config: inc_qua_config_pb2.QuaConfig.MultipleInputs) -> Type[MultipleInputsApi]:
    pass


@overload
def create_element_input_class(
    input_config: inc_qua_config_pb2.QuaConfig.MicrowaveInputPortReference,
) -> Type[MwInputApi]:
    pass


@overload
def create_element_input_class(input_config: None) -> Type[NoInputApi]:
    pass


def create_element_input_class(input_config: InputConfigType) -> Type[ElementInputApi]:
    if isinstance(input_config, inc_qua_config_pb2.QuaConfig.SingleInput):
        return SingleInputApi
    if isinstance(input_config, inc_qua_config_pb2.QuaConfig.MixInputs):
        return MixInputsApi
    if isinstance(input_config, inc_qua_config_pb2.QuaConfig.SingleInputCollection):
        return SingleInputCollectionApi
    if isinstance(input_config, inc_qua_config_pb2.QuaConfig.MultipleInputs):
        return MultipleInputsApi
    if isinstance(input_config, inc_qua_config_pb2.QuaConfig.MicrowaveInputPortReference):
        return MwInputApi
    if input_config is None:
        return NoInputApi
    raise UnknownElementType(f"Unknown input type {type(input_config)}")
