import logging
from abc import ABCMeta
from typing import Any, List, Type, Tuple, Union, TypeVar, Optional, cast

from qm.type_hinting import Value
from qm.api.base_api import BaseApi
from qm.exceptions import QmValueError
from qm.api.models.jobs import PendingJobData
from qm.grpc.qm.pb.frontend_pb2_grpc import FrontendStub
from qm.utils.protobuf_utils import timestamp_to_datetime
from qm.api.models.server_details import ConnectionDetails
from qm.utils.general_utils import create_input_stream_name
from qm.api.models.capabilities import QopCaps, ServerCapabilities
from qm.grpc.qm.pb.job_manager_pb2_grpc import JobManagerServiceStub
from qm.api.stubs.deprecated_job_manager_stub import DeprecatedJobManagerServiceStub
from qm.grpc.qm.pb import frontend_pb2, qm_manager_pb2, job_manager_pb2, general_messages_pb2
from qm._QmJobErrors import (
    MissingJobError,
    MissingElementError,
    UnknownInputStreamError,
    ElementWithSingleInputError,
    InvalidElementCorrectionError,
    InvalidJobExecutionStatusError,
    ElementWithoutIntermediateFrequencyError,
    _handle_job_manager_error,
)

logger = logging.getLogger(__name__)


JobStubType = TypeVar("JobStubType", JobManagerServiceStub, DeprecatedJobManagerServiceStub)


class JobManagerBaseApi(BaseApi[JobStubType], metaclass=ABCMeta):
    def __init__(self, connection_details: ConnectionDetails):
        super().__init__(connection_details)
        self._frontend_stub = FrontendStub(self._channel)  # type: ignore[no-untyped-call]

    def set_element_correction(
        self, job_id: str, element_name: str, correction: general_messages_pb2.Matrix
    ) -> Tuple[float, float, float, float]:
        request = job_manager_pb2.SetElementCorrectionRequest(jobId=job_id, qeName=element_name, correction=correction)

        response: job_manager_pb2.SetElementCorrectionResponse = self._run(
            self._stub.SetElementCorrection, request, timeout=self._timeout
        )

        valid_errors = (
            MissingElementError,
            ElementWithSingleInputError,
            InvalidElementCorrectionError,
            ElementWithoutIntermediateFrequencyError,
        )
        _handle_job_manager_error(request, response, valid_errors)
        return (
            response.correction.v00,
            response.correction.v01,
            response.correction.v10,
            response.correction.v11,
        )

    def get_element_correction(self, job_id: str, element_name: str) -> Tuple[float, float, float, float]:
        request = job_manager_pb2.GetElementCorrectionRequest(jobId=job_id, qeName=element_name)

        response: job_manager_pb2.GetElementCorrectionResponse = self._run(
            self._stub.GetElementCorrection, request, timeout=self._timeout
        )
        valid_errors = (
            MissingElementError,
            ElementWithSingleInputError,
            ElementWithoutIntermediateFrequencyError,
        )
        _handle_job_manager_error(request, response, valid_errors)
        return (
            response.correction.v00,
            response.correction.v01,
            response.correction.v10,
            response.correction.v11,
        )

    def insert_input_stream(self, job_id: str, stream_name: str, data: List[Value]) -> None:
        stream_name = create_input_stream_name(stream_name)
        request = job_manager_pb2.InsertInputStreamRequest(jobId=job_id, streamName=stream_name)

        if all(type(element) == bool for element in data):
            request.boolStreamData.CopyFrom(job_manager_pb2.BoolStreamData(data=cast(List[bool], data)))
        elif all(type(element) == int for element in data):
            request.intStreamData.CopyFrom(job_manager_pb2.IntStreamData(data=cast(List[int], data)))
        elif all(type(element) == float for element in data):
            request.fixedStreamData.CopyFrom(job_manager_pb2.FixedStreamData(data=cast(List[float], data)))
        else:
            raise QmValueError(
                f"Invalid type in data, type is '{set(type(el) for el in data)}', "
                f"accepted types are bool | int | float"
            )

        response: job_manager_pb2.InsertInputStreamResponse = self._run(
            self._stub.InsertInputStream, request, timeout=self._timeout
        )

        valid_errors = (
            MissingJobError,
            InvalidJobExecutionStatusError,
            UnknownInputStreamError,
        )
        _handle_job_manager_error(request, response, valid_errors)

    def halt(self, job_id: str) -> bool:
        request = frontend_pb2.HaltRequest(jobId=job_id)
        response: frontend_pb2.HaltResponse = self._run(self._frontend_stub.Halt, request, timeout=self._timeout)
        return response.ok

    def resume(self, job_id: str) -> bool:
        request = frontend_pb2.ResumeRequest(jobId=job_id)
        self._run(self._frontend_stub.Resume, request, timeout=self._timeout)
        return True

    def is_paused(self, job_id: str) -> bool:
        request = frontend_pb2.PausedStatusRequest(jobId=job_id)
        response: frontend_pb2.PausedStatusResponse = self._run(
            self._frontend_stub.PausedStatus, request, timeout=self._timeout
        )
        return response.isPaused

    def is_job_running(self, job_id: str) -> bool:
        request = frontend_pb2.IsJobRunningRequest(jobId=job_id)

        response: frontend_pb2.IsJobRunningResponse = self._run(
            self._frontend_stub.IsJobRunning, request, timeout=self._timeout
        )
        return response.isRunning

    def is_data_acquiring(self, job_id: str) -> frontend_pb2.IsJobAcquiringDataResponse.AcquiringStatus:
        request = frontend_pb2.IsJobAcquiringDataRequest(jobId=job_id)
        response: frontend_pb2.IsJobAcquiringDataResponse = self._run(
            self._frontend_stub.IsJobAcquiringData, request, timeout=self._timeout
        )
        return response.acquiringStatus

    def get_job_execution_status(self, job_id: str, quantum_machine_id: str) -> frontend_pb2.JobExecutionStatus:
        request = frontend_pb2.GetJobExecutionStatusRequest(jobId=job_id, quantumMachineId=quantum_machine_id)
        response: frontend_pb2.GetJobExecutionStatusResponse = self._run(
            self._frontend_stub.GetJobExecutionStatus, request, timeout=self._timeout
        )
        return response.status

    @staticmethod
    def _create_job_query_params(
        quantum_machine_id: str,
        job_id: Optional[str],
        position: Optional[int],
        user_id: Optional[str],
    ) -> frontend_pb2.JobQueryParams:
        request = frontend_pb2.JobQueryParams(quantumMachineId=quantum_machine_id)

        if position is not None:
            request.position.value = position

        if job_id is not None:
            request.jobId.CopyFrom(frontend_pb2.QueryValueMatcher(value=job_id))

        if user_id is not None:
            request.userId.CopyFrom(frontend_pb2.QueryValueMatcher(value=user_id))

        return request

    def remove_job(
        self,
        quantum_machine_id: str,
        job_id: Optional[str] = None,
        position: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> int:
        request = JobManagerBaseApi._create_job_query_params(quantum_machine_id, job_id, position, user_id)

        response: frontend_pb2.RemovePendingJobsResponse = self._run(
            self._frontend_stub.RemovePendingJobs, request, timeout=self._timeout
        )
        return response.numbersOfJobsRemoved

    def get_pending_jobs(
        self,
        quantum_machine_id: str,
        job_id: Optional[str],
        position: Optional[int],
        user_id: Optional[str],
    ) -> List[PendingJobData]:
        request = JobManagerBaseApi._create_job_query_params(quantum_machine_id, job_id, position, user_id)
        response = self._run(self._frontend_stub.GetPendingJobs, request, timeout=self._timeout)
        return [
            PendingJobData(
                job_id=job_id,
                position_in_queue=status.positionInQueue,
                time_added=timestamp_to_datetime(status.timeAdded),
                added_by=status.addedBy,
            )
            for job_id, status in response.pendingJobs.items()
        ]

    def get_running_job(self, machine_id: str) -> Optional[str]:
        request = qm_manager_pb2.GetRunningJobRequest(machineID=machine_id)
        response: qm_manager_pb2.GetRunningJobResponse = self._run(
            self._frontend_stub.GetRunningJob, request, timeout=self._timeout
        )

        if response.jobId:
            return response.jobId
        return None


class JobManagerApi(JobManagerBaseApi[JobManagerServiceStub]):
    @property
    def _stub_class(self) -> Type[JobManagerServiceStub]:
        return JobManagerServiceStub


class DeprecatedJobManagerApi(JobManagerBaseApi[DeprecatedJobManagerServiceStub]):
    @property
    def _stub_class(self) -> Type[DeprecatedJobManagerServiceStub]:
        return DeprecatedJobManagerServiceStub


def create_job_manager_from_api(
    api: BaseApi[Any], capabilities: ServerCapabilities
) -> Union[JobManagerApi, DeprecatedJobManagerApi]:
    if capabilities.supports(QopCaps.new_grpc_structure):
        return JobManagerApi(api.connection_details)
    return DeprecatedJobManagerApi(api.connection_details)
