from collections import defaultdict
from typing import Dict, Type, Union, Mapping, Iterator, Optional, Sequence

from google.protobuf.wrappers_pb2 import Int64Value

from qm.api.v2.base_api_v2 import BaseApiV2
from qm.exceptions import DataFetchingError
from qm.utils.protobuf_utils import which_one_of
from qm.api.models.server_details import ConnectionDetails
from qm.grpc.qm.grpc.v2 import job_api_pb2, common_types_pb2
from qm.grpc.qm.grpc.v2.job_api_pb2_grpc import JobServiceStub
from qm.api.models.jobs import JobNamedResult, JobStreamingState, JobResultItemSchema, JobNamedResultHeader


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

    def get_job_named_result(
        self, output_name: str, long_offset: int, limit: int, timeout: Optional[float] = None
    ) -> Iterator[JobNamedResult]:
        timeout = timeout if timeout is not None else self._timeout

        request = job_api_pb2.GetNamedResultRequest(
            job_id=self._id, output_name=output_name, long_offset=Int64Value(value=long_offset), limit=limit
        )
        if self._supports_chunk_streaming:
            results_iterator = self._run_iterator(self._stub.GetNamedResult, request, timeout=timeout)
            for result in self._group_results(results_iterator):
                yield result
        else:
            for response in self._stub.GetNamedResult(request, timeout=timeout):
                yield JobNamedResult(
                    data=response.success.data, count_of_items=response.success.count_of_items, output_name=output_name
                )

    def get_job_named_results(
        self, data_to_fetch: Mapping[str, slice], timeout: Optional[float]
    ) -> Iterator[JobNamedResult]:
        request = job_api_pb2.GetNamedResultsRequest(
            job_id=self._id,
            outputs=[
                job_api_pb2.GetNamedResultsRequest.Output(
                    output_name=output_name,
                    range=common_types_pb2.Range(
                        **{"from": Int64Value(value=s.start), "to": Int64Value(value=s.stop - 1)}
                    ),
                )
                for output_name, s in data_to_fetch.items()
            ],
        )
        timeout = timeout if timeout is not None else self._timeout
        results_iterator = self._stub.GetNamedResults(request, timeout=timeout)
        for result in self._group_results(results_iterator):
            yield result

    def _group_results(
        self, results_iterator: Iterator[job_api_pb2.GetNamedResultResponse]
    ) -> Iterator[JobNamedResult]:
        output_name_to_accumulated_bytes: Dict[str, bytes] = defaultdict(lambda: b"")
        # Note that the result name is a new attribute, so for old QOP we will receive just empty string.
        # But it is guaranteed that all the results belong to the same stream.
        for response in results_iterator:
            _, response_val = which_one_of(response, "response_oneof")
            if isinstance(response_val, job_api_pb2.GetNamedResultResponse.GetNamedResultResponseError):
                raise DataFetchingError(f"{response_val.details}")
            if not isinstance(response_val, job_api_pb2.GetNamedResultResponse.GetNamedResultResponseSuccess):
                raise ValueError(f"Unexpected response: {response}")
            name = response_val.output_name
            _, data_one_of = which_one_of(response_val, "data_oneof")
            if isinstance(data_one_of, job_api_pb2.GetNamedResultResponse.GetNamedResultResponseSuccess.DataChunk):
                output_name_to_accumulated_bytes[name] += data_one_of.data
            elif isinstance(data_one_of, job_api_pb2.GetNamedResultResponse.GetNamedResultResponseSuccess.DataSummary):
                data = output_name_to_accumulated_bytes.pop(name)
                result = JobNamedResult(data=data, count_of_items=data_one_of.count, output_name=name)
                yield result
            else:
                raise ValueError(f"Unexpected response: {response}")

    def get_named_headers(self, name_to_flat_struct: Mapping[str, bool]) -> Mapping[str, JobNamedResultHeader]:
        request = job_api_pb2.GetJobNamedResultsHeadersRequest(
            job_id=self._id,
            outputs=[
                job_api_pb2.GetJobNamedResultsHeadersRequest.Output(output_name=name, flat_format=flat_struct)
                for name, flat_struct in name_to_flat_struct.items()
            ],
        )
        headers = self._fetch_headers(request)
        return {response.output_name: self._convert_header_response_to_model(response) for response in headers}

    def _fetch_headers(
        self, request: job_api_pb2.GetJobNamedResultsHeadersRequest
    ) -> Sequence[job_api_pb2.GetJobNamedResultsHeadersResponse.GetJobNamedResultsHeadersResponseSuccess.OutputHeader]:
        response: job_api_pb2.GetJobNamedResultsHeadersResponse.GetJobNamedResultsHeadersResponseSuccess = self._run(
            self._stub.GetJobNamedResultsHeaders, request, timeout=self._timeout
        )
        return response.headers

    def get_named_header(self, output_name: str, flat_struct: bool) -> JobNamedResultHeader:
        request = job_api_pb2.GetJobNamedResultHeaderRequest(
            job_id=self._id, output_name=output_name, flat_format=flat_struct
        )
        response: job_api_pb2.GetJobNamedResultHeaderResponse.GetJobNamedResultHeaderResponseSuccess = self._run(
            self._stub.GetJobNamedResultHeader, request, timeout=self._timeout
        )
        return self._convert_header_response_to_model(response)

    @staticmethod
    def _convert_header_response_to_model(
        response: Union[
            job_api_pb2.GetJobNamedResultHeaderResponse.GetJobNamedResultHeaderResponseSuccess,
            job_api_pb2.GetJobNamedResultsHeadersResponse.GetJobNamedResultsHeadersResponseSuccess.OutputHeader,
        ],
    ) -> JobNamedResultHeader:
        return JobNamedResultHeader(
            count_so_far=response.count_so_far,
            bare_dtype=response.simple_dtype,
            shape=tuple(response.shape),
            has_dataloss=response.has_data_loss,
            has_execution_errors=False,
        )

    def get_job_result_schema(self) -> Mapping[str, JobResultItemSchema]:
        request = job_api_pb2.GetJobResultSchemaRequest(job_id=self._id)
        response: job_api_pb2.GetJobResultSchemaResponse.GetJobResultSchemaResponseSuccess = self._run(
            self._stub.GetJobResultSchema, request, timeout=self._timeout
        )
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
        request = job_api_pb2.GetJobResultStateRequest(job_id=self._id)
        response: job_api_pb2.GetJobResultStateResponse.GetJobResultStateResponseSuccess = self._run(
            self._stub.GetJobResultState, request, timeout=self._timeout
        )
        return JobStreamingState(
            job_id=self._id,
            done=response.done,
            closed=response.closed,
            has_dataloss=response.has_dataloss,
        )

    def get_job_execution_status(self) -> common_types_pb2.JobExecutionStatus:
        request = job_api_pb2.JobServiceGetJobStatusRequest(job_id=self._id)
        response: job_api_pb2.JobServiceGetJobStatusResponse.JobServiceGetJobStatusResponseSuccess = self._run(
            self._stub.GetJobStatus, request, timeout=self._timeout
        )
        return response.status
