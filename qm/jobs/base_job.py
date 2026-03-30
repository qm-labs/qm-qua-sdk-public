import datetime
import warnings
from typing import List, Optional

from qm.type_hinting import Value
from qm.grpc.qm.pb import frontend_pb2
from qm.exceptions import QmQuaException
from qm.utils import deprecation_message
from qm.api.frontend_api import FrontendApi
from qm.api.job_manager_api import create_job_manager_from_api
from qm.api.models.capabilities import QopCaps, ServerCapabilities
from qm.utils.protobuf_utils import which_one_of, timestamp_to_datetime


class QmBaseJob:
    def __init__(
        self,
        job_id: str,
        machine_id: str,
        frontend_api: FrontendApi,
        capabilities: ServerCapabilities,
    ):
        self._id = job_id
        self._machine_id = machine_id
        self._frontend = frontend_api
        self._capabilities = capabilities

        self._job_manager = create_job_manager_from_api(frontend_api, capabilities)

        self._added_user_id: Optional[str] = None
        self._time_added: Optional[datetime.datetime] = None
        self._initialize_from_job_status()

    def _initialize_from_job_status(self) -> None:
        status: frontend_pb2.JobExecutionStatus = self._job_manager.get_job_execution_status(self._id, self._machine_id)
        _, job_state = which_one_of(status, "status")

        if isinstance(
            job_state,
            (
                frontend_pb2.JobExecutionStatus.Pending,
                frontend_pb2.JobExecutionStatus.Running,
                frontend_pb2.JobExecutionStatus.Completed,
                frontend_pb2.JobExecutionStatus.Loading,
            ),
        ):
            self._added_user_id = job_state.addedBy
            self._time_added = timestamp_to_datetime(job_state.timeAdded)

    @property
    def status(self) -> str:
        """Returns the status of the job, one of the following strings:
        "unknown", "pending", "running", "completed", "canceled", "loading", "error"
        """
        status: frontend_pb2.JobExecutionStatus = self._job_manager.get_job_execution_status(self._id, self._machine_id)
        name, _ = which_one_of(status, "status")
        return name

    @property
    def id(self) -> str:
        """
        Returns: The id of the job
        """
        return self._id

    @property
    def user_added(self) -> Optional[str]:
        """
        Returns: The id of the user who added the job
        """
        return self._added_user_id

    @property
    def time_added(self) -> Optional[datetime.datetime]:
        """
        Returns: The time at which the job was added
        """
        return self._time_added

    def insert_input_stream(
        self,
        name: str,
        data: List[Value],
    ) -> None:
        """Deprecated - Please use `job.push_to_input_stream`."""
        warnings.warn(
            deprecation_message(
                method="job.insert_input_stream",
                deprecated_in="1.2.0",
                removed_in="2.0.0",
                details="This method was renamed to `job.push_to_input_stream`.",
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        self.push_to_input_stream(name, data)

    def push_to_input_stream(self, name: str, data: List[Value]) -> None:
        """Push data to the input stream declared in the QUA program.
        The data is then ready to be read by the program using the advance
        input stream QUA statement.

        Multiple data entries can be inserted before the data is read by the program through successive calls of this method (one for each entry).

        See [Input streams](../Guides/features.md#input-streams) for more information.

        -- Available from QOP 2.0 --

        Args:
            name: The input stream name the data is to be inserted to.
            data: The data to be inserted. The data's size must match
                the size of the input stream.
        """
        if not self._capabilities.supports(QopCaps.input_stream):
            raise QmQuaException("`push_to_input_stream()` is not supported by the QOP version.")

        if not isinstance(data, list):
            data = [data]

        self._job_manager.insert_input_stream(self.id, name, data)
