from dataclasses import dataclass
from typing import Dict, List, Type, Tuple, AsyncIterator

import betterproto

from qm.api.v2.base_api_v2 import BaseApiV2
from qm.exceptions import DataFetchingError
from qm.api.models.jobs import JobNamedResult
from qm.api.models.server_details import ConnectionDetails
from qm.StreamMetadata import StreamMetadata, StreamMetadataError, _get_stream_metadata_dict_from_proto_resp
from qm.grpc.v2 import (
    JobServiceStub,
    JobExecutionStatus,
    GetNamedResultRequest,
    GetJobResultStateRequest,
    GetJobResultSchemaRequest,
    GetProgramMetadataRequest,
    JobServiceGetJobStatusRequest,
    GetJobNamedResultHeaderRequest,
    GetNamedResultResponseGetNamedResultResponseError,
    GetNamedResultResponseGetNamedResultResponseSuccess,
    GetJobResultStateResponseGetJobResultStateResponseSuccess,
    GetJobResultSchemaResponseGetJobResultSchemaResponseSuccess,
    GetNamedResultResponseGetNamedResultResponseSuccessDataChunk,
    GetNamedResultResponseGetNamedResultResponseSuccessDataSummary,
    GetJobResultSchemaResponseGetJobResultSchemaResponseSuccessItem,
    GetJobNamedResultHeaderResponseGetJobNamedResultHeaderResponseSuccess,
)


@dataclass
class SchemaResponseItem:
    name: str
    simple_d_type: str
    is_single: bool
    expected_count: int
    shape: List[int]

    @classmethod
    def from_grpc(cls, data: GetJobResultSchemaResponseGetJobResultSchemaResponseSuccessItem) -> "SchemaResponseItem":
        return cls(
            name=data.name,
            simple_d_type=data.simple_dtype,
            is_single=data.is_single,
            expected_count=data.expected_count,
            shape=data.shape,
        )


@dataclass
class SchemaResponse:
    items: List[SchemaResponseItem]

    @classmethod
    def from_grpc(cls, data: GetJobResultSchemaResponseGetJobResultSchemaResponseSuccess) -> "SchemaResponse":
        return cls(items=[SchemaResponseItem.from_grpc(item) for item in data.items])


@dataclass
class NamedResultHeader:
    is_single: bool
    count_so_far: int
    simple_d_type: str
    has_dataloss: bool
    shape: List[int]
    has_execution_errors: bool = False

    @classmethod
    def from_grpc(
        cls, data: GetJobNamedResultHeaderResponseGetJobNamedResultHeaderResponseSuccess
    ) -> "NamedResultHeader":
        return cls(
            is_single=data.is_single,
            count_so_far=data.count_so_far,
            simple_d_type=data.simple_dtype,
            has_dataloss=data.has_data_loss,
            shape=data.shape,
        )


class JobResultApi(BaseApiV2[JobServiceStub]):
    def __init__(self, connection_details: ConnectionDetails, job_id: str, supports_chunk_streaming: bool):
        super().__init__(connection_details)
        self._id = job_id
        self._supports_chunk_streaming = supports_chunk_streaming

    @property
    def _stub_class(self) -> Type[JobServiceStub]:
        return JobServiceStub

    @property
    def id(self) -> str:
        return self._id

    async def get_job_named_result(
        self, output_name: str, long_offset: int, limit: int
    ) -> AsyncIterator[JobNamedResult]:
        request = GetNamedResultRequest(job_id=self._id, output_name=output_name, long_offset=long_offset, limit=limit)
        if self._supports_chunk_streaming:
            accumulated_bytes = b""
            async for response in self._run_async_iterator(self._stub.get_named_result, request, timeout=self._timeout):
                _, response_val = betterproto.which_one_of(response, "response_oneof")
                if isinstance(response_val, GetNamedResultResponseGetNamedResultResponseError):
                    raise DataFetchingError(f"{response_val.details}")
                if not isinstance(response_val, GetNamedResultResponseGetNamedResultResponseSuccess):
                    raise ValueError(f"Unexpected response: {response}")
                _, data_one_of = betterproto.which_one_of(response_val, "data_oneof")
                if isinstance(data_one_of, GetNamedResultResponseGetNamedResultResponseSuccessDataChunk):
                    accumulated_bytes += data_one_of.data
                elif isinstance(data_one_of, GetNamedResultResponseGetNamedResultResponseSuccessDataSummary):
                    result = JobNamedResult(data=accumulated_bytes, count_of_items=data_one_of.count)
                    yield result
                    accumulated_bytes = b""
                else:
                    raise ValueError(f"Unexpected response: {response}")
        else:
            async for response in self._stub.get_named_result(request, timeout=self._timeout):
                yield JobNamedResult(data=response.success.data, count_of_items=response.success.count_of_items)

    def get_named_header(self, output_name: str, flat_struct: bool) -> NamedResultHeader:
        request = GetJobNamedResultHeaderRequest(job_id=self._id, output_name=output_name, flat_format=flat_struct)
        response = self._run(self._stub.get_job_named_result_header(request, timeout=self._timeout))
        return NamedResultHeader.from_grpc(response)

    def get_program_metadata(self) -> Tuple[List[StreamMetadataError], Dict[str, StreamMetadata]]:
        request = GetProgramMetadataRequest(job_id=self._id)

        response = self._run(self._stub.get_program_metadata(request, timeout=self._timeout))
        metadata_errors = [
            StreamMetadataError(error.error, error.location)
            for error in response.program_stream_metadata.stream_metadata_extraction_error
        ]

        metadata_dict = _get_stream_metadata_dict_from_proto_resp(response.program_stream_metadata)
        return metadata_errors, metadata_dict

    def get_job_result_schema(self) -> SchemaResponse:
        request = GetJobResultSchemaRequest(job_id=self._id)
        response = self._run(self._stub.get_job_result_schema(request, timeout=self._timeout))
        return SchemaResponse.from_grpc(response)

    def get_job_state(self) -> GetJobResultStateResponseGetJobResultStateResponseSuccess:
        request = GetJobResultStateRequest(job_id=self._id)
        response = self._run(self._stub.get_job_result_state(request, timeout=self._timeout))
        return response

    def get_job_execution_status(self) -> JobExecutionStatus:
        request = JobServiceGetJobStatusRequest(job_id=self._id)
        response = self._run(self._stub.get_job_status(request, timeout=self._timeout))
        return response.status
