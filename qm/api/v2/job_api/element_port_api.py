from qm.grpc.qm.grpc.v2 import job_api_pb2
from qm.api.models.server_details import ConnectionDetails
from qm.api.v2.job_api.generic_apis import ElementGenericApi


class ElementPortApi(ElementGenericApi):
    def __init__(self, connection_details: ConnectionDetails, job_id: str, element_id: str, port_name: str) -> None:
        super().__init__(connection_details, job_id, element_id)
        self._port = port_name


class AnalogOutputApi(ElementPortApi):
    def set_dc_offset(self, value: float) -> None:
        request = job_api_pb2.SetInputDcOffsetRequest(
            job_id=self._id, qe=self._element_id, port=self._port, offset=value
        )
        self._run(self._stub.SetInputDcOffset, request, timeout=self._timeout)

    def get_dc_offset(self) -> float:
        request = job_api_pb2.GetInputDcOffsetRequest(job_id=self._id, qe=self._element_id, port=self._port)
        response: job_api_pb2.GetInputDcOffsetResponse.GetInputDcOffsetResponseSuccess = self._run(
            self._stub.GetInputDcOffset, request, timeout=self._timeout
        )
        return response.offset


class MwOutputApi(ElementGenericApi):
    def set_oscillator_frequency(self, frequency: float) -> None:
        request = job_api_pb2.SetOscillatorFrequencyRequest(
            job_id=self._id,
            qe=self._element_id,
            new_frequency_hz=frequency,
            update_component=job_api_pb2.SetOscillatorFrequencyRequest.UpdateComponentSelection.downconverter,
        )
        self._run(self._stub.SetOscillatorFrequency, request, timeout=self._timeout)


class DigitalInputApi(ElementPortApi):
    def set_delay(self, value: int) -> None:
        request = job_api_pb2.SetDigitalDelayRequest(job_id=self._id, qe=self._element_id, port=self._port, delay=value)
        self._run(self._stub.SetDigitalDelay, request, timeout=self._timeout)

    def get_delay(self) -> int:
        request = job_api_pb2.GetDigitalDelayRequest(job_id=self._id, qe=self._element_id, port=self._port)
        response: job_api_pb2.GetDigitalDelayResponse.GetDigitalDelayResponseSuccess = self._run(
            self._stub.GetDigitalDelay, request, timeout=self._timeout
        )
        return response.delay

    def set_buffer(self, value: int) -> None:
        request = job_api_pb2.SetDigitalBufferRequest(
            job_id=self._id, qe=self._element_id, port=self._port, buffer=value
        )
        self._run(self._stub.SetDigitalBuffer, request, timeout=self._timeout)

    def get_buffer(self) -> int:
        request = job_api_pb2.GetDigitalBufferRequest(job_id=self._id, qe=self._element_id, port=self._port)
        response: job_api_pb2.GetDigitalBufferResponse.GetDigitalBufferResponseSuccess = self._run(
            self._stub.GetDigitalBuffer, request, timeout=self._timeout
        )
        return response.buffer
