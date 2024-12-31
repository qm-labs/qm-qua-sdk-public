import logging
from typing import Dict, List, Tuple, AsyncIterator

from qm.utils.async_utils import run_async
from qm.api.models.server_details import ConnectionDetails
from qm.api.base_api import BaseApi, connection_error_handle
from qm.StreamMetadata import StreamMetadata, StreamMetadataError, _get_stream_metadata_dict_from_proto_resp
from qm.grpc.results_analyser import (
    GetJobStateRequest,
    GetJobErrorsRequest,
    GetJobStateResponse,
    JobResultsServiceStub,
    GetJobNamedResultRequest,
    GetJobErrorsResponseError,
    GetJobNamedResultResponse,
    GetJobResultSchemaRequest,
    GetProgramMetadataRequest,
    GetJobResultSchemaResponse,
    GetJobNamedResultHeaderRequest,
    GetJobNamedResultHeaderResponse,
)

logger = logging.getLogger(__name__)


@connection_error_handle()
class JobResultServiceApi(BaseApi):
    def __init__(self, connection_details: ConnectionDetails):
        super().__init__(connection_details)
        self._stub = JobResultsServiceStub(self._channel)

    def get_job_errors(self, job_id: str) -> List[GetJobErrorsResponseError]:
        request = GetJobErrorsRequest(job_id=job_id)
        response = run_async(self._stub.get_job_errors(request, timeout=self._timeout))
        return response.errors

    def get_job_named_result(
        self, job_id: str, output_name: str, long_offset: int, limit: int
    ) -> AsyncIterator[GetJobNamedResultResponse]:
        request = GetJobNamedResultRequest(job_id=job_id, output_name=output_name, long_offset=long_offset, limit=limit)
        return self._stub.get_job_named_result(request, timeout=self._timeout)

    def get_job_state(self, job_id: str) -> GetJobStateResponse:
        request = GetJobStateRequest(job_id=job_id)
        response = run_async(self._stub.get_job_state(request, timeout=self._timeout))
        return response

    def get_named_header(self, job_id: str, output_name: str, flat_struct: bool) -> GetJobNamedResultHeaderResponse:
        request = GetJobNamedResultHeaderRequest(job_id=job_id, output_name=output_name, flat_format=flat_struct)
        response = run_async(self._stub.get_job_named_result_header(request, timeout=self._timeout))
        return response

    def get_program_metadata(self, job_id: str) -> Tuple[List[StreamMetadataError], Dict[str, StreamMetadata]]:
        request = GetProgramMetadataRequest(job_id=job_id)

        response = run_async(self._stub.get_program_metadata(request, timeout=self._timeout))

        if response.success:
            metadata_errors = [
                StreamMetadataError(error.error, error.location)
                for error in response.program_stream_metadata.stream_metadata_extraction_error
            ]

            metadata_dict = _get_stream_metadata_dict_from_proto_resp(response.program_stream_metadata)
            return metadata_errors, metadata_dict
        logger.warning(f"Failed to fetch program metadata for job: {job_id}")
        return [], {}

    def get_job_result_schema(self, job_id: str) -> GetJobResultSchemaResponse:
        request = GetJobResultSchemaRequest(job_id=job_id)
        response = run_async(self._stub.get_job_result_schema(request, timeout=self._timeout))
        return response
