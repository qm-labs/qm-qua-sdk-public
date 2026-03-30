import logging
from typing import List, Type, Mapping, Iterator, Optional

from google.protobuf.wrappers_pb2 import Int64Value

from qm.api.base_api import BaseApi
from qm.grpc.qm.pb import job_results_pb2
from qm.api.models.server_details import ConnectionDetails
from qm.utils.protobuf_utils import proto_repeated_to_list
from qm.grpc.qm.pb.job_results_pb2_grpc import JobResultsServiceStub
from qm.api.models.jobs import JobNamedResult, JobStreamingState, JobResultItemSchema, JobNamedResultHeader

logger = logging.getLogger(__name__)


class JobResultServiceApi(BaseApi[JobResultsServiceStub]):
    def __init__(self, connection_details: ConnectionDetails, job_id: str):
        super().__init__(connection_details)
        self._id = job_id

    @property
    def id(self) -> str:
        return self._id

    @property
    def _stub_class(self) -> Type[JobResultsServiceStub]:
        return JobResultsServiceStub

    def get_job_errors(self) -> List[job_results_pb2.GetJobErrorsResponse.Error]:
        request = job_results_pb2.GetJobErrorsRequest(jobId=self._id)
        response: job_results_pb2.GetJobErrorsResponse = self._run(
            self._stub.GetJobErrors, request, timeout=self._timeout
        )
        return proto_repeated_to_list(response.errors)

    def get_job_named_result(
        self,
        output_name: str,
        long_offset: int,
        limit: int,
        timeout: Optional[float],
    ) -> Iterator[JobNamedResult]:
        timeout = timeout if timeout is not None else self._timeout

        request = job_results_pb2.GetJobNamedResultRequest(
            jobId=self._id, outputName=output_name, longOffset=Int64Value(value=long_offset), limit=limit
        )
        response = self._run_iterator(self._stub.GetJobNamedResult, request, timeout=timeout)

        for result in response:
            yield JobNamedResult(data=result.data, count_of_items=result.countOfItems, output_name=output_name)

    def get_job_state(self) -> JobStreamingState:
        request = job_results_pb2.GetJobStateRequest(jobId=self._id)
        response = self._run(self._stub.GetJobState, request, timeout=self._timeout)
        return JobStreamingState(
            job_id=self._id,
            done=response.done,
            closed=response.closed,
            has_dataloss=response.hasDataloss,
        )

    def get_named_header(self, output_name: str, flat_struct: bool) -> JobNamedResultHeader:
        request = job_results_pb2.GetJobNamedResultHeaderRequest(
            jobId=self._id, outputName=output_name, flatFormat=flat_struct
        )
        response = self._run(self._stub.GetJobNamedResultHeader, request, timeout=self._timeout)
        return JobNamedResultHeader(
            count_so_far=response.countSoFar,
            bare_dtype=response.simpleDType,
            shape=tuple(response.shape),
            has_dataloss=response.hasDataloss,
            has_execution_errors=response.hasExecutionErrors.value,
        )

    def get_state_from_header(self, output_name: str, flat_struct: bool) -> JobStreamingState:
        """This function is for backward compatibility, when we didn't have the get_job_state"""
        request = job_results_pb2.GetJobNamedResultHeaderRequest(
            jobId=self._id, outputName=output_name, flatFormat=flat_struct
        )
        response: job_results_pb2.GetJobNamedResultHeaderResponse = self._run(
            self._stub.GetJobNamedResultHeader, request, timeout=self._timeout
        )
        return JobStreamingState(
            job_id=self._id,
            done=response.done,
            closed=response.closed,
            has_dataloss=response.hasDataloss,
        )

    def get_job_result_schema(self) -> Mapping[str, JobResultItemSchema]:
        request = job_results_pb2.GetJobResultSchemaRequest(jobId=self._id)
        response = self._run(self._stub.GetJobResultSchema, request, timeout=self._timeout)
        return {
            item.name: JobResultItemSchema(
                name=item.name,
                bare_dtype=item.simpleDType,
                shape=tuple(item.shape),
                is_single=item.isSingle,
                expected_count=item.expectedCount,
            )
            for item in response.items
        }
