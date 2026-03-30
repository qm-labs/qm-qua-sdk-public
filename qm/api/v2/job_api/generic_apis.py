from typing import Type

from qm.api.v2.base_api_v2 import BaseApiV2
from qm.api.models.server_details import ConnectionDetails
from qm.grpc.qm.grpc.v2.job_api_pb2_grpc import JobServiceStub


class JobGenericApi(BaseApiV2[JobServiceStub]):
    def __init__(self, connection_details: ConnectionDetails, job_id: str):
        super().__init__(connection_details)
        self._id = job_id

    @property
    def _stub_class(self) -> Type[JobServiceStub]:
        return JobServiceStub


class ElementGenericApi(JobGenericApi):
    def __init__(self, connection_details: ConnectionDetails, job_id: str, element_id: str) -> None:
        super().__init__(connection_details, job_id)
        self._element_id = element_id
