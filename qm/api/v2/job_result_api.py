from collections import defaultdict
from typing import Dict, List, Type, Tuple, Union, Mapping, Optional, Sequence, AsyncIterator

import betterproto

from qm.api.v2.base_api_v2 import BaseApiV2
from qm.exceptions import DataFetchingError
from qm.api.models.server_details import ConnectionDetails
from qm.api.models.jobs import JobNamedResult, JobStreamingState, JobResultItemSchema, JobNamedResultHeader
from qm.StreamMetadata import StreamMetadata, StreamMetadataError, _get_stream_metadata_dict_from_proto_resp
from qm.grpc.v2 import (
    Range,
    JobServiceStub,
    JobExecutionStatus,
    GetNamedResultRequest,
    GetNamedResultResponse,
    GetNamedResultsRequest,
    GetJobResultStateRequest,
    GetJobResultSchemaRequest,
    GetProgramMetadataRequest,
    GetNamedResultsRequestOutput,
    JobServiceGetJobStatusRequest,
    GetJobNamedResultHeaderRequest,
    GetJobNamedResultsHeadersRequest,
    GetJobNamedResultsHeadersRequestOutput,
    GetNamedResultResponseGetNamedResultResponseError,
    GetNamedResultResponseGetNamedResultResponseSuccess,
    GetNamedResultResponseGetNamedResultResponseSuccessDataChunk,
    GetNamedResultResponseGetNamedResultResponseSuccessDataSummary,
    GetJobNamedResultHeaderResponseGetJobNamedResultHeaderResponseSuccess,
    GetJobNamedResultsHeadersResponseGetJobNamedResultsHeadersResponseSuccessOutputHeader,
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
        self, output_name: str, long_offset: int, limit: int, timeout: Optional[float] = None
    ) -> AsyncIterator[JobNamedResult]:
        timeout = timeout if timeout is not None else self._timeout

        request = GetNamedResultRequest(job_id=self._id, output_name=output_name, long_offset=long_offset, limit=limit)
        if self._supports_chunk_streaming:
            results_iterator = self._run_async_iterator(self._stub.get_named_result, request, timeout=timeout)
            async for result in self._group_results(results_iterator):
                yield result
        else:
            async for response in self._stub.get_named_result(request, timeout=timeout):
                yield JobNamedResult(
                    data=response.success.data, count_of_items=response.success.count_of_items, output_name=output_name
                )

    async def get_job_named_results(
        self, data_to_fetch: Mapping[str, slice], timeout: Optional[float]
    ) -> AsyncIterator[JobNamedResult]:
        request = GetNamedResultsRequest(
            job_id=self._id,
            outputs=[
                GetNamedResultsRequestOutput(
                    output_name=output_name,
                    range=Range(from_=s.start, to=s.stop - 1),
                )
                for output_name, s in data_to_fetch.items()
            ],
        )
        timeout = timeout if timeout is not None else self._timeout
        results_iterator = self._run_async_iterator(self._stub.get_named_results, request, timeout=timeout)
        async for result in self._group_results(results_iterator):
            yield result

    async def _group_results(
        self, results_iterator: AsyncIterator[GetNamedResultResponse]
    ) -> AsyncIterator[JobNamedResult]:
        output_name_to_accumulated_bytes: Dict[str, bytes] = defaultdict(lambda: b"")
        # Note that the result name is a new attribute, so for old QOP we will receive just empty string.
        # But it is guaranteed that all the results belong to the same stream.
        async for response in results_iterator:
            _, response_val = betterproto.which_one_of(response, "response_oneof")
            if isinstance(response_val, GetNamedResultResponseGetNamedResultResponseError):
                raise DataFetchingError(f"{response_val.details}")
            if not isinstance(response_val, GetNamedResultResponseGetNamedResultResponseSuccess):
                raise ValueError(f"Unexpected response: {response}")
            name = response_val.output_name
            _, data_one_of = betterproto.which_one_of(response_val, "data_oneof")
            if isinstance(data_one_of, GetNamedResultResponseGetNamedResultResponseSuccessDataChunk):
                output_name_to_accumulated_bytes[name] += data_one_of.data
            elif isinstance(data_one_of, GetNamedResultResponseGetNamedResultResponseSuccessDataSummary):
                data = output_name_to_accumulated_bytes.pop(name)
                result = JobNamedResult(data=data, count_of_items=data_one_of.count, output_name=name)
                yield result
            else:
                raise ValueError(f"Unexpected response: {response}")

    def get_named_headers(self, name_to_flat_struct: Mapping[str, bool]) -> Mapping[str, JobNamedResultHeader]:
        request = GetJobNamedResultsHeadersRequest(
            job_id=self._id,
            outputs=[
                GetJobNamedResultsHeadersRequestOutput(output_name=name, flat_format=flat_struct)
                for name, flat_struct in name_to_flat_struct.items()
            ],
        )
        headers = self._fetch_headers(request)
        return {response.output_name: self._convert_header_response_to_model(response) for response in headers}

    def _fetch_headers(
        self, request: GetJobNamedResultsHeadersRequest
    ) -> Sequence[GetJobNamedResultsHeadersResponseGetJobNamedResultsHeadersResponseSuccessOutputHeader]:
        response = self._run(self._stub.get_job_named_results_headers(request, timeout=self._timeout))
        return response.headers

    def get_named_header(self, output_name: str, flat_struct: bool) -> JobNamedResultHeader:
        request = GetJobNamedResultHeaderRequest(job_id=self._id, output_name=output_name, flat_format=flat_struct)
        response = self._run(self._stub.get_job_named_result_header(request, timeout=self._timeout))
        return self._convert_header_response_to_model(response)

    @staticmethod
    def _convert_header_response_to_model(
        response: Union[
            GetJobNamedResultHeaderResponseGetJobNamedResultHeaderResponseSuccess,
            GetJobNamedResultsHeadersResponseGetJobNamedResultsHeadersResponseSuccessOutputHeader,
        ]
    ) -> JobNamedResultHeader:
        return JobNamedResultHeader(
            count_so_far=response.count_so_far,
            bare_dtype=response.simple_dtype,
            shape=tuple(response.shape),
            has_dataloss=response.has_data_loss,
            has_execution_errors=False,
        )

    def get_program_metadata(self) -> Tuple[List[StreamMetadataError], Dict[str, StreamMetadata]]:
        request = GetProgramMetadataRequest(job_id=self._id)

        response = self._run(self._stub.get_program_metadata(request, timeout=self._timeout))
        metadata_errors = [
            StreamMetadataError(error.error, error.location)
            for error in response.program_stream_metadata.stream_metadata_extraction_error
        ]

        metadata_dict = _get_stream_metadata_dict_from_proto_resp(response.program_stream_metadata)
        return metadata_errors, metadata_dict

    def get_job_result_schema(self) -> Mapping[str, JobResultItemSchema]:
        request = GetJobResultSchemaRequest(job_id=self._id)
        response = self._run(self._stub.get_job_result_schema(request, timeout=self._timeout))
        return {
            item.name: JobResultItemSchema(
                name=item.name,
                bare_dtype=item.simple_dtype,
                shape=tuple(item.shape),
                is_single=item.is_single,
                expected_count=item.expected_count,
            )
            for item in response.items
        }

    def get_job_state(self) -> JobStreamingState:
        request = GetJobResultStateRequest(job_id=self._id)
        response = self._run(self._stub.get_job_result_state(request, timeout=self._timeout))
        return JobStreamingState(
            job_id=self._id,
            done=response.done,
            closed=response.closed,
            has_dataloss=response.has_dataloss,
        )

    def get_job_execution_status(self) -> JobExecutionStatus:
        request = JobServiceGetJobStatusRequest(job_id=self._id)
        response = self._run(self._stub.get_job_status(request, timeout=self._timeout))
        return response.status
