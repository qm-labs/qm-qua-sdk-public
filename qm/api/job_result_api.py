import logging
from typing import Dict, List, Type, Tuple, Mapping, Optional, AsyncIterator

from qm.api.base_api import BaseApi
from qm.api.models.server_details import ConnectionDetails
from qm.api.models.jobs import JobNamedResult, JobStreamingState, JobResultItemSchema, JobNamedResultHeader
from qm.StreamMetadata import StreamMetadata, StreamMetadataError, _get_stream_metadata_dict_from_proto_resp
from qm.grpc.results_analyser import (
    GetJobStateRequest,
    GetJobErrorsRequest,
    JobResultsServiceStub,
    GetJobNamedResultRequest,
    GetJobErrorsResponseError,
    GetJobResultSchemaRequest,
    GetProgramMetadataRequest,
    GetJobNamedResultHeaderRequest,
)

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

    def get_job_errors(self) -> List[GetJobErrorsResponseError]:
        request = GetJobErrorsRequest(job_id=self._id)
        response = self._run(self._stub.get_job_errors(request, timeout=self._timeout))
        return response.errors

    async def get_job_named_result(
        self,
        output_name: str,
        long_offset: int,
        limit: int,
        timeout: Optional[float],
    ) -> AsyncIterator[JobNamedResult]:
        timeout = timeout if timeout is not None else self._timeout

        request = GetJobNamedResultRequest(
            job_id=self._id, output_name=output_name, long_offset=long_offset, limit=limit
        )
        response = self._run_async_iterator(self._stub.get_job_named_result, request, timeout=timeout)

        async for result in response:
            yield JobNamedResult(data=result.data, count_of_items=result.count_of_items, output_name=output_name)

    def get_job_state(self) -> JobStreamingState:
        request = GetJobStateRequest(job_id=self._id)
        response = self._run(self._stub.get_job_state(request, timeout=self._timeout))
        return JobStreamingState(
            job_id=self._id,
            done=response.done,
            closed=response.closed,
            has_dataloss=response.has_dataloss,
        )

    def get_named_header(self, output_name: str, flat_struct: bool) -> JobNamedResultHeader:
        request = GetJobNamedResultHeaderRequest(job_id=self._id, output_name=output_name, flat_format=flat_struct)
        response = self._run(self._stub.get_job_named_result_header(request, timeout=self._timeout))
        return JobNamedResultHeader(
            count_so_far=response.count_so_far,
            bare_dtype=response.simple_d_type,
            shape=tuple(response.shape),
            has_dataloss=response.has_dataloss,
            has_execution_errors=bool(response.has_execution_errors),
        )

    def get_state_from_header(self, output_name: str, flat_struct: bool) -> JobStreamingState:
        """This function is for backward compatibility, when we didn't have the get_job_state"""
        request = GetJobNamedResultHeaderRequest(job_id=self._id, output_name=output_name, flat_format=flat_struct)
        response = self._run(self._stub.get_job_named_result_header(request, timeout=self._timeout))
        return JobStreamingState(
            job_id=self._id,
            done=response.done,
            closed=response.closed,
            has_dataloss=response.has_dataloss,
        )

    def get_program_metadata(self) -> Tuple[List[StreamMetadataError], Dict[str, StreamMetadata]]:
        request = GetProgramMetadataRequest(job_id=self._id)

        response = self._run(self._stub.get_program_metadata(request, timeout=self._timeout))

        if response.success:
            metadata_errors = [
                StreamMetadataError(error.error, error.location)
                for error in response.program_stream_metadata.stream_metadata_extraction_error
            ]
            metadata_dict = _get_stream_metadata_dict_from_proto_resp(response.program_stream_metadata)
            return metadata_errors, metadata_dict
        logger.warning(f"Failed to fetch program metadata for job: {self._id}")
        return [], {}

    def get_job_result_schema(self) -> Mapping[str, JobResultItemSchema]:
        request = GetJobResultSchemaRequest(job_id=self._id)
        response = self._run(self._stub.get_job_result_schema(request, timeout=self._timeout))
        return {
            item.name: JobResultItemSchema(
                name=item.name,
                bare_dtype=item.simple_d_type,
                shape=tuple(item.shape),
                is_single=item.is_single,
                expected_count=item.expected_count,
            )
            for item in response.items
        }
