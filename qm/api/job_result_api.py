import logging
from typing import Dict, List, Type, Tuple, AsyncIterator

from qm.api.base_api import BaseApi
from qm.api.models.jobs import JobNamedResult
from qm.api.models.server_details import ConnectionDetails
from qm.StreamMetadata import StreamMetadata, StreamMetadataError, _get_stream_metadata_dict_from_proto_resp
from qm.grpc.results_analyser import (
    GetJobStateRequest,
    GetJobErrorsRequest,
    GetJobStateResponse,
    JobResultsServiceStub,
    GetJobNamedResultRequest,
    GetJobErrorsResponseError,
    GetJobResultSchemaRequest,
    GetProgramMetadataRequest,
    GetJobResultSchemaResponse,
    GetJobNamedResultHeaderRequest,
    GetJobNamedResultHeaderResponse,
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
        self, output_name: str, long_offset: int, limit: int
    ) -> AsyncIterator[JobNamedResult]:
        request = GetJobNamedResultRequest(
            job_id=self._id, output_name=output_name, long_offset=long_offset, limit=limit
        )
        response = self._run_async_iterator(self._stub.get_job_named_result, request, timeout=self._timeout)
        async for result in response:
            yield JobNamedResult(data=result.data, count_of_items=result.count_of_items)

    def get_job_state(self) -> GetJobStateResponse:
        request = GetJobStateRequest(job_id=self._id)
        response = self._run(self._stub.get_job_state(request, timeout=self._timeout))
        return response

    def get_named_header(self, output_name: str, flat_struct: bool) -> GetJobNamedResultHeaderResponse:
        request = GetJobNamedResultHeaderRequest(job_id=self._id, output_name=output_name, flat_format=flat_struct)
        response = self._run(self._stub.get_job_named_result_header(request, timeout=self._timeout))
        return response

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

    def get_job_result_schema(self) -> GetJobResultSchemaResponse:
        request = GetJobResultSchemaRequest(job_id=self._id)
        response = self._run(self._stub.get_job_result_schema(request, timeout=self._timeout))
        return response
