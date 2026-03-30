import logging
import warnings
from dataclasses import dataclass
from collections import defaultdict
from typing import (
    Dict,
    List,
    Type,
    Tuple,
    Union,
    Literal,
    TypeVar,
    Iterable,
    Optional,
    Sequence,
    Collection,
    cast,
    overload,
)

import numpy as np

from qm.qua import fixed
from qm.utils import deprecation_message
from qm.api.v2.job_result_api import JobResultApi
from qm._report import ExecutionError, ExecutionReport
from qm.type_hinting import Value, NumpySupportedValue
from qm.type_hinting.config_types import FullQuaConfig
from qm.utils.config_utils import get_logical_pb_config
from qm.api.v2.job_api.generic_apis import JobGenericApi
from qm.api.models.server_details import ConnectionDetails
from qm.api.v2.job_api.job_elements_db import JobElementsDB
from qm.utils.general_utils import create_input_stream_name
from qm.grpc.qm.pb import job_manager_pb2, inc_qua_config_pb2
from qm.api.models.capabilities import QopCaps, ServerCapabilities
from qm.grpc.qm.grpc.v2 import qm_api_pb2, job_api_pb2, qmm_api_pb2, common_types_pb2
from qm.api.v2.job_api.element_input_api import MwInputApi, MixInputsApi, SingleInputApi
from qm.exceptions import QmValueError, JobFailedError, QMTimeoutError, FunctionInputError

from ...._stream_results import StreamsManager
from ....program._dict_to_pb_converter import DictToQuaConfigConverter

logger = logging.getLogger(__name__)

NumberType = Union[bool, int, float]
NumberTypeVar = TypeVar("NumberTypeVar", bool, int, float)
JobStatus = Literal["In queue", "Running", "Processing", "Done", "Canceled", "Error"]

JOB_STATUS_MAPPING: Dict[common_types_pb2.JobExecutionStatus.ValueType, JobStatus] = {  # type: ignore[name-defined]
    common_types_pb2.JobExecutionStatus.UNKNOWN: "Error",
    common_types_pb2.JobExecutionStatus.PENDING: "In queue",
    common_types_pb2.JobExecutionStatus.RUNNING: "Running",
    common_types_pb2.JobExecutionStatus.COMPLETED: "Done",
    common_types_pb2.JobExecutionStatus.CANCELED: "Canceled",
    common_types_pb2.JobExecutionStatus.LOADING: "In queue",
    common_types_pb2.JobExecutionStatus.ERROR: "Error",
    common_types_pb2.JobExecutionStatus.PROCESSING: "Processing",
}

VALID_STATES_TRANSITION: Dict[JobStatus, set[JobStatus]] = {
    "In queue": {"In queue", "Running", "Processing"},
    "Running": {"Running", "Processing"},
}

_inverse_job_status_mapping_tmp = defaultdict(list)
for k, v in JOB_STATUS_MAPPING.items():
    _inverse_job_status_mapping_tmp[v].append(k)
_INVERSE_JOB_STATUS_MAPPING = dict(_inverse_job_status_mapping_tmp)

IoValueTypes = Union[Type[bool], Type[int], Type[float], Type[fixed]]


def transfer_statuses_to_enum(
    status: Union[JobStatus, Iterable[JobStatus]]
) -> List[common_types_pb2.JobExecutionStatus.ValueType]:  # type: ignore[name-defined]
    if isinstance(status, str):
        status = [status]
    try:
        return sum([_INVERSE_JOB_STATUS_MAPPING[x] for x in status], [])
    except KeyError:
        raise QmValueError(f"One ore more statuses is invalid: {status}")


@overload
def _extract_io_value_type(
    io_value: job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData, io_type: None
) -> job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData:
    pass


@overload
def _extract_io_value_type(
    io_value: job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData, io_type: Type[bool]
) -> bool:
    pass


@overload
def _extract_io_value_type(
    io_value: job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData, io_type: Type[int]
) -> int:
    pass


@overload
def _extract_io_value_type(
    io_value: job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData,
    io_type: Union[Type[float], Type[fixed]],
) -> float:
    pass


def _extract_io_value_type(
    io_value: job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData, io_type: Optional[IoValueTypes]
) -> Union[bool, int, float, job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData]:
    if io_type is None:
        return io_value
    if io_type == bool:
        return io_value.boolean_value
    if io_type == int:
        return io_value.int_value
    if io_type == float or io_type == fixed:
        return io_value.double_value
    raise TypeError(f"Data type {io_type} is not supported")


@dataclass
class JobData:
    id: str
    status: JobStatus
    description: str
    metadata: qmm_api_pb2.JobMetadata  # This is a GRPC class, consider replacing with a dataclass
    is_simulation: bool

    @classmethod
    def from_grpc(cls, grpc_job: qmm_api_pb2.JobResponseData) -> "JobData":
        return cls(
            id=grpc_job.job_id,
            status=JOB_STATUS_MAPPING[grpc_job.status],
            description=grpc_job.description,
            metadata=grpc_job.metadata,
            is_simulation=grpc_job.is_simulation,
        )


class JobApi(JobGenericApi):
    def __init__(self, connection_details: ConnectionDetails, job_id: str, capabilities: ServerCapabilities) -> None:
        super().__init__(connection_details, job_id)
        self._elements: Optional[JobElementsDB] = None
        self._caps = capabilities

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(connection_details={self._connection_details}, job_id={self._id})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}:\n\tid: {self._id}\n\tstatus: {self.get_status()}"

    @property
    def elements(self) -> JobElementsDB:
        if self._elements is None:  # This is done lazily to avoid unnecessary calls to the server
            self._elements = self._create_elements()
        return self._elements

    @property
    def id(self) -> str:
        return self._id

    def get_job_id(self) -> str:
        """
        Returns:
             The job's ID
        """
        return self.id

    def _create_elements(self) -> JobElementsDB:
        elements_pb_config = get_logical_pb_config(self._get_pb_config()).elements
        return JobElementsDB.init_from_data(elements_pb_config, self._connection_details, self._id)

    def _get_pb_config(self) -> inc_qua_config_pb2.QuaConfig:
        request = job_api_pb2.JobServiceGetConfigRequest(job_id=self._id)
        success: qm_api_pb2.GetConfigSuccess = self._run(self._stub.GetConfig, request, timeout=self._timeout)
        return success.config

    def get_compilation_config(self) -> FullQuaConfig:
        """
        Returns:
             The config with which this job was compiled
        """
        converter = DictToQuaConfigConverter(self._caps)
        return converter.deconvert(self._get_pb_config())

    def push_to_input_stream(self, stream_name: str, data: List[Union[bool, int, float]]) -> None:
        """Push data to the input stream declared in the QUA program.
        The data is then ready to be read by the program using the advance input stream QUA statement.
        The type of QUA variable is inferred from the python type passed to ``data`` according to the following rule:

        int -> int
        float -> fixed
        bool -> bool

        When sending a list (into a QUA array), all data must be of the same type.

        Multiple data entries can be pushed before the data is read by the program.

        See [Input streams](../Guides/features.md#input-streams) for more information.

        Args:
            stream_name: The input stream name the data is to be pushed to.
            data: The data to be pushed. The data's size & type must match
                the size & type of the input stream.
        """
        if all(type(element) == bool for element in data):
            self._typed_push_to_input_stream(stream_name, bool, data)
        elif all(type(element) == int for element in data):
            self._typed_push_to_input_stream(stream_name, int, data)
        elif all(type(element) == float for element in data):
            self._typed_push_to_input_stream(stream_name, float, data)
        else:
            raise QmValueError(
                f"Invalid type in data, type is '{set(type(el) for el in data)}', "
                f"expected types are bool | int | float"
            )

    def _typed_push_to_input_stream(
        self, stream_name: str, data_type: Type[NumberTypeVar], data: Sequence[NumberTypeVar]
    ) -> None:
        stream_name = create_input_stream_name(stream_name)
        if data_type == bool:
            request = job_api_pb2.JobServicePushToInputStreamRequest(
                job_id=self._id,
                stream_name=stream_name,
                bool_stream_data=job_manager_pb2.BoolStreamData(data=[bool(d) for d in data]),
            )
        elif data_type == int:
            request = job_api_pb2.JobServicePushToInputStreamRequest(
                job_id=self._id,
                stream_name=stream_name,
                int_stream_data=job_manager_pb2.IntStreamData(data=[int(d) for d in data]),
            )
        elif data_type == float:
            request = job_api_pb2.JobServicePushToInputStreamRequest(
                job_id=self._id,
                stream_name=stream_name,
                fixed_stream_data=job_manager_pb2.FixedStreamData(data=[float(d) for d in data]),
            )
        else:
            raise TypeError(f"Data type {data_type} is not supported")
        self._run(self._stub.PushToInputStream, request, timeout=self._timeout)

    def get_status(self) -> JobStatus:
        """
        Returns the status of the job, one of the following strings:

        - `In queue` - Program is in the queue
        - `Running` - Program is currently running
        - `Processing` - Program done but data processing is ongoing
        - `Done` - Program and data processing done
        - `Canceled` - Program was canceled before it was done
        - `Error` - Program encountered an error

        Returns:

             The job status
        """
        request = job_api_pb2.JobServiceGetJobStatusRequest(job_id=self._id)
        success: job_api_pb2.JobServiceGetJobStatusResponse.JobServiceGetJobStatusResponseSuccess = self._run(
            self._stub.GetJobStatus, request, timeout=self._timeout
        )
        return JOB_STATUS_MAPPING[success.status]

    def is_running(self) -> bool:
        """
        Returns:

             `True` if the job is currently running
        """
        return self.get_status() == "Running"

    def wait_until(self, state: Union[JobStatus, Collection[JobStatus]], timeout: Optional[float] = None) -> None:
        """
        Waits until a specific state is reached. If the job is already passed the given state, the function will
        immediately return. See [get_status][qm.api.v2.job_api.job_api.JobApi.get_status] for a list of statuses.

        If the state cannot be reached (e.g., waiting for “Done” but the job is “Canceled”) then an error is raised.

        If the timeout time, has passed, an error is raised.

        Args:
            state: The state to wait for
            timeout: The timeout time, in seconds
        """
        if isinstance(state, str):
            state = {state}
        try:
            timeout = timeout if timeout is not None else self._timeout
            self._wait_until(state, timeout)  # type: ignore[arg-type]

        except QMTimeoutError as e:
            raise QMTimeoutError(f"Job {self.id} did not reach any state of {state} within {timeout} seconds") from e

    def _wait_until(self, states: Collection[JobStatus], timeout: float) -> None:
        request = job_api_pb2.JobServiceGetJobStatusRequest(job_id=self._id)
        all_valid_states = [VALID_STATES_TRANSITION.get(state, {state}) for state in states]
        valid_states_flatten = set.union(*all_valid_states)
        for status in self._run_iterator(self._stub.GetJobStatusUpdates, request, timeout=timeout):
            status_str = JOB_STATUS_MAPPING[status.success.status]
            if status_str in valid_states_flatten:
                logger.debug(f"Job {self.id} reached state {status_str}")
                return
            if status_str == "Done":
                logger.info(f"Job {self.id} is done")
                return
            if status_str in {"Error", "Canceled"}:
                raise JobFailedError(f"Job {self.id} reached state {status_str}")

    def is_finished(self) -> bool:
        """
        Returns:

             `True` if the job will no longer run (Has reached "Done", "Canceled" or "Error").
        """
        return self.get_status() in {"Done", "Canceled", "Error"}

    def cancel(self) -> None:
        """
        Cancels the job
        """
        request = job_api_pb2.CancelRequest(job_id=self._id)
        self._run(self._stub.Cancel, request, timeout=self._timeout)

    def is_paused(self) -> bool:
        """
        Returns:

             `True` if the job was paused from QUA.
        """
        request = job_api_pb2.JobServiceIsPausedRequest(job_id=self._id)
        success: job_api_pb2.IsPausedResponse.IsPausedResponseSuccess = self._run(
            self._stub.IsPaused, request, timeout=self._timeout
        )
        return success.is_paused

    def resume(self) -> None:
        """Resumes a program that was halted using the [pause][qm.qua.pause] statement"""
        if self.get_status() == "Error":
            return
        request = job_api_pb2.ResumeRequest(job_id=self._id)
        self._run(self._stub.Resume, request, timeout=self._timeout)

    @staticmethod
    def _fix_io_value_type(value: Optional[NumpySupportedValue]) -> job_api_pb2.SetIoValuesRequest.IOValueSetData:
        if value is None:
            return job_api_pb2.SetIoValuesRequest.IOValueSetData()
        if isinstance(value, (np.bool_, bool)):
            return job_api_pb2.SetIoValuesRequest.IOValueSetData(boolean_value=bool(value))
        if isinstance(value, (np.integer, int)):
            return job_api_pb2.SetIoValuesRequest.IOValueSetData(int_value=int(value))
        if isinstance(value, (np.floating, float)):
            return job_api_pb2.SetIoValuesRequest.IOValueSetData(double_value=float(value))
        raise QmValueError(f"cannot convert {type(value)} to int | float | bool")

    def set_io_values(
        self, io1: Optional[NumpySupportedValue] = None, io2: Optional[NumpySupportedValue] = None
    ) -> None:
        """
        Sets the values of ``IO1`` & ``IO2`. If only one is given, then the value of the second will remain unchanged.

        This can be used later inside a QUA program as a QUA variable ``IO1``, ``IO2`` without declaration.
        The type of QUA variable is inferred from the python type according to the following rule:

        int -> int
        float -> fixed
        bool -> bool

        Args:
            io1: The value to be placed in ``IO1``
            io2: The value to be placed in ``IO2``
        """
        request = job_api_pb2.SetIoValuesRequest(
            job_id=self._id,
        )
        if io1 is not None:
            request.io1.CopyFrom(self._fix_io_value_type(io1))
        if io2 is not None:
            request.io2.CopyFrom(self._fix_io_value_type(io2))
        self._run(self._stub.SetIOValues, request, timeout=self._timeout)

    def set_io1_value(self, value: Optional[NumpySupportedValue]) -> None:
        """
        Sets the values of ``IO1``.

        This can be used later inside a QUA program as a QUA variable ``IO1``, ``IO2`` without declaration.
        The type of QUA variable is inferred from the python type according to the following rule:

        int -> int
        float -> fixed
        bool -> bool

        Args:
            value: The value to be placed in ``IO1``
        """
        self.set_io_values(io1=value)

    def set_io2_value(self, value: Optional[NumpySupportedValue]) -> None:
        """
        Sets the values of ``IO2``.

        This can be used later inside a QUA program as a QUA variable ``IO1``, ``IO2`` without declaration.
        The type of QUA variable is inferred from the python type according to the following rule:

        int -> int
        float -> fixed
        bool -> bool

        Args:
            value: The value to be placed in ``IO2``
        """
        self.set_io_values(io2=value)

    @overload
    def get_io_values(
        self, *, io1_type: None = ..., io2_type: None = ...
    ) -> Tuple[
        job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData,
        job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData,
    ]:
        pass

    @overload
    def get_io_values(
        self, *, io1_type: Type[bool], io2_type: None = ...
    ) -> Tuple[bool, job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData]:
        pass

    @overload
    def get_io_values(
        self, *, io1_type: Type[int], io2_type: None = ...
    ) -> Tuple[int, job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData]:
        pass

    @overload
    def get_io_values(
        self, *, io1_type: Union[Type[float], Type[fixed]], io2_type: None = ...
    ) -> Tuple[float, job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData]:
        pass

    @overload
    def get_io_values(
        self, *, io1_type: None = ..., io2_type: Type[bool]
    ) -> Tuple[job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData, bool]:
        pass

    @overload
    def get_io_values(self, *, io1_type: Type[bool], io2_type: Type[bool]) -> Tuple[bool, bool]:
        pass

    @overload
    def get_io_values(  # type: ignore[overload-overlap]
        self, *, io1_type: Type[int], io2_type: Type[bool]
    ) -> Tuple[int, bool]:
        # This overlap is because int and bool are not distinct types in runtime
        pass

    @overload
    def get_io_values(self, *, io1_type: Union[Type[float], Type[fixed]], io2_type: Type[bool]) -> Tuple[float, bool]:
        pass

    @overload
    def get_io_values(
        self, *, io1_type: None = ..., io2_type: Type[int]
    ) -> Tuple[job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData, int]:
        pass

    @overload
    def get_io_values(self, *, io1_type: Type[bool], io2_type: Type[int]) -> Tuple[bool, int]:
        pass

    @overload
    def get_io_values(self, *, io1_type: Type[int], io2_type: Type[int]) -> Tuple[int, int]:
        pass

    @overload
    def get_io_values(self, *, io1_type: Union[Type[float], Type[fixed]], io2_type: Type[int]) -> Tuple[float, int]:
        pass

    @overload
    def get_io_values(
        self, *, io1_type: None = ..., io2_type: Union[Type[float], Type[fixed]]
    ) -> Tuple[job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData, float]:
        pass

    @overload
    def get_io_values(self, *, io1_type: Type[bool], io2_type: Union[Type[float], Type[fixed]]) -> Tuple[bool, float]:
        pass

    @overload
    def get_io_values(self, *, io1_type: Type[int], io2_type: Union[Type[float], Type[fixed]]) -> Tuple[int, float]:
        pass

    @overload
    def get_io_values(
        self, *, io1_type: Union[Type[float], Type[fixed]], io2_type: Union[Type[float], Type[fixed]]
    ) -> Tuple[float, float]:
        pass

    def get_io_values(
        self, *, io1_type: Optional[IoValueTypes] = None, io2_type: Optional[IoValueTypes] = None
    ) -> Tuple[
        Union[bool, int, float, job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData],
        Union[bool, int, float, job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData],
    ]:
        """
        Gets the data stored in ``IO1`` & ``IO2``

        Data will be presented as the type given. If no type was given, it'll have three fields: `int_value`,
        `double_value`, & `boolean_value`

        Args:
            io1_type: The type of ``IO1``
            io2_type:  The type of ``IO1``

        Returns:
             A tuple of (``IO1``, ``IO2``)
        """
        v1, v2 = self._fetch_io_values()
        return _extract_io_value_type(v1, io1_type), _extract_io_value_type(v2, io2_type)

    @overload
    def get_io1_value(
        self,
        as_type: None = ...,
    ) -> job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData:
        pass

    @overload
    def get_io1_value(self, as_type: Type[bool]) -> bool:
        pass

    @overload
    def get_io1_value(self, as_type: Type[int]) -> int:
        pass

    @overload
    def get_io1_value(self, as_type: Union[Type[float], Type[fixed]]) -> float:
        pass

    def get_io1_value(
        self, as_type: Optional[IoValueTypes] = None
    ) -> Union[bool, int, float, job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData]:
        """
        Gets the data stored in ``IO1``

        Data will be presented as the type given. If no type was given, it'll have three fields: `int_value`,
        `double_value`, & `boolean_value`

        Args:
            as_type: The type of ``IO1``

        Returns:
             ``IO1``
        """
        return self.get_io_values(io1_type=as_type)[0]

    @overload
    def get_io2_value(
        self,
        as_type: None = ...,
    ) -> job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData:
        pass

    @overload
    def get_io2_value(self, as_type: Type[bool]) -> bool:
        pass

    @overload
    def get_io2_value(self, as_type: Type[int]) -> int:
        pass

    @overload
    def get_io2_value(self, as_type: Union[Type[float], Type[fixed]]) -> float:
        pass

    def get_io2_value(
        self, as_type: Optional[IoValueTypes] = None
    ) -> Union[bool, int, float, job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData]:
        """
        Gets the data stored in ``IO12`

        Data will be presented as the type given. If no type was given, it'll have three fields: `int_value`,
        `double_value`, & `boolean_value`

        Args:
            as_type: The type of ``IO2``

        Returns:
             ``IO2``
        """
        return self.get_io_values(io2_type=as_type)[1]

    def _fetch_io_values(
        self,
    ) -> Tuple[
        job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData,
        job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess.IOValuesData,
    ]:
        request = job_api_pb2.GetIoValuesRequest(job_id=self._id)
        success: job_api_pb2.GetIoValuesResponse.GetIoValuesResponseSuccess = self._run(
            self._stub.GetIOValues, request, timeout=self._timeout
        )
        return success.io1, success.io2

    @property
    def result_handles(self) -> StreamsManager:
        results_api = JobResultApi(self.connection_details, self._id, self._caps.supports(QopCaps.chunk_streaming))
        return StreamsManager(results_api, self._caps, self.wait_until)

    def get_errors(self) -> List[ExecutionError]:
        """
        Returns:

             A list of all errors in the execution report
        """
        request = job_api_pb2.GetJobErrorsRequest(job_id=self._id)
        success: job_api_pb2.GetJobErrorsResponse.GetJobErrorsResponseSuccess = self._run(
            self._stub.GetErrors, request, timeout=self._timeout
        )
        return [ExecutionError.create_from_grpc_message(error) for error in success.errors]

    def execution_report(self) -> ExecutionReport:
        """Get runtime errors report for this job. See [Runtime errors](../Guides/error.md#runtime-errors).

        Returns:
            An object holding the errors that this job generated.
        """
        errors = self.get_errors()
        return ExecutionReport(self._id, errors)

    def set_element_correction(self, element: str, correction: Tuple[float, float, float, float]) -> None:
        r"""Sets the correction matrix for correcting gain and phase imbalances
        of an IQ mixer associated with an element.

        Values will be rounded to an accuracy of $2^{-16}$.
        Valid values for the correction values are between $-2$ and $(2 - 2^{-16})$.

        Warning - the correction matrix can increase the output voltage which might result in an
        overflow.

        Args:
            element (str): The name of the element to update the correction for
            correction (tuple):
                Tuple is of the form (v00, v01, v10, v11) where
                the matrix is
                $\begin{pmatrix} v_{00} & v_{01} \\ v_{10} & v_{11}\end{pmatrix}$
        """
        element_input = self.elements[element].input
        if not isinstance(element_input, MixInputsApi):
            raise ValueError(f"Element {element} is not an IQ mixer")
        element_input.set_correction(correction)

    def get_element_correction(self, element: str) -> Tuple[float, float, float, float]:
        """Gets the correction matrix for correcting gain and phase imbalances
        of an IQ mixer associated with an element.

        Args:
            element (str): The name of the element to update the correction for

        Returns:
            The current correction matrix
        """
        element_input = self.elements[element].input
        if not isinstance(element_input, MixInputsApi):
            raise ValueError(f"Element {element} is not an IQ mixer")
        return element_input.get_correction()

    def set_intermediate_frequency(self, element: str, freq: float) -> None:
        """Sets the intermediate frequency of the element

        Args:
            element (str): The name of the element whose intermediate frequency will be updated
            freq (float): The intermediate frequency to set to the given element
        """
        element_inst = self.elements[element]
        element_inst.set_intermediate_frequency(freq)

    def get_intermediate_frequency(self, element: str) -> float:
        """Gets the intermediate frequency of the element

        Args:
            element (str): The name of the element whose intermediate frequency will be updated

        Returns:
            float: The intermediate frequency of the given element
        """
        element_inst = self.elements[element]
        return element_inst.get_intermediate_frequency()

    def get_output_dc_offset_by_element(
        self, element: str, iq_input: Optional[Literal["I", "Q", "single"]] = None
    ) -> float:
        """Get the current DC offset of the OPX analog output channel associated with an element.

        Args:
            element: The name of the element to get the correction for
            iq_input: The port name as appears in the element config.
                Options:

                `'single'`
                    for an element with a single input

                `'I'` or `'Q'`
                    for an element with mixer inputs

        Returns:
            The offset, in volts
        """
        input_instance = self.elements[element].input
        if isinstance(input_instance, SingleInputApi):
            return input_instance.get_dc_offset()
        elif isinstance(input_instance, MixInputsApi):
            i, q = input_instance.get_dc_offsets()
            if iq_input == "I":
                return i
            elif iq_input == "Q":
                return q
            else:
                raise FunctionInputError(f"Port must be I or Q, got {iq_input}.")
        else:
            raise ValueError(f"Element {element} of type {type(input_instance)} does not have a 'port' property.")

    @overload
    def set_output_dc_offset_by_element(
        self,
        element: str,
        input: Union[Tuple[Literal["I", "Q"], Literal["I", "Q"]], List[Literal["I", "Q"]]],
        offset: Union[Tuple[float, float], List[float]],
    ) -> None:
        pass

    @overload
    def set_output_dc_offset_by_element(
        self,
        element: str,
        input: Literal["single", "I", "Q"],
        offset: float,
    ) -> None:
        pass

    def set_output_dc_offset_by_element(
        self,
        element: str,
        input: Union[Literal["single", "I", "Q"], Tuple[Literal["I", "Q"], Literal["I", "Q"]], List[Literal["I", "Q"]]],
        offset: Union[float, Tuple[float, float], List[float]],
    ) -> None:
        """Set the current DC offset of the OPX analog output channel associated with an element.

        Args:
            element (str): the name of the element to update the correction for
            input (Union[str, Tuple[str,str], List[str]]): the input name as appears in the element config. Options:

                `'single'`
                    for an element with a single input

                `'I'` or `'Q'` or a tuple ('I', 'Q')
                    for an element with mixer inputs
            offset (Union[float, Tuple[float,float], List[float]]): The dc value to set to, in volts. Ranges
                from -0.5 to 0.5 - 2^-16 in steps of 2^-16.

        Examples:
            ```python
            job.set_output_dc_offset_by_element('flux', 'single', 0.1)
            job.set_output_dc_offset_by_element('qubit', 'I', -0.01)
            job.set_output_dc_offset_by_element('qubit', ('I', 'Q'), (-0.01, 0.05))
            ```

        Note:

            If the sum of the DC offset and the largest waveform data-point exceed the range,
            DAC output overflow will occur and the output will be corrupted.

            This change is **job-scoped**: it updates the current hardware value for the
            duration of the running job only and does **not** update the idle value. When the
            job ends, the hardware reverts to the idle value from the controller config (or from
            the last [update_config][qm.api.v2.qm_api.QmApi.update_config] call). To permanently
            update the idle value, use [update_config][qm.api.v2.qm_api.QmApi.update_config].
            See [Output Idle Values](../../Guides/output_idle_values.md) for the full lifecycle.
        """
        input_instance = self.elements[element].input
        if isinstance(input_instance, MixInputsApi):
            if isinstance(input, (list, tuple)):
                if not set(input) <= {"I", "Q"}:
                    raise FunctionInputError(f"Input names should be 'I' or 'Q', got {input}")
                if not (isinstance(offset, (list, tuple)) and len(input) == len(offset)):
                    raise FunctionInputError(
                        f"input should be two iterables of the same size," f"got input = {input} and offset = {offset}"
                    )
                channel_to_offset = dict(zip(input, offset))
            elif isinstance(input, str):
                if input not in {"I", "Q"}:
                    raise FunctionInputError(f"Input names should be 'I' or 'Q', got {input}")
                if not isinstance(offset, (int, float)):
                    raise FunctionInputError(f"Input should be int or float, got {type(offset)}")
                channel_to_offset = {cast(Literal["I", "Q"], input): offset}
            else:
                raise ValueError(f"Invalid input - {input}")
            input_instance.set_dc_offsets(i_offset=channel_to_offset.get("I"), q_offset=channel_to_offset.get("Q"))
        elif isinstance(input_instance, SingleInputApi):
            if input != "single":
                raise ValueError(f"Invalid input - {input} while the element has a single input")
            if not isinstance(offset, (int, float)):
                raise FunctionInputError(f"Input should be int or float, got {type(offset)}")
            input_instance.set_dc_offset(offset)
        else:
            raise ValueError(
                f"Element {element} with input of type {input_instance.__class__.__name__} "
                f"does not support dc offset setting."
            )

    def set_input_dc_offset_by_element(self, element: str, output: str, offset: float) -> None:
        """Set the current DC offset of the OPX analog input channel associated with an element.

        Args:
            element (str): the name of the element to update the
                correction for
            output (str): the output key name as appears in the element
                config under 'outputs'.
            offset (float): the dc value to set to, in volts. Ranges from -0.5 to 0.5 - 2^-16 in steps of
                2^-16.

        Note:
            If the sum of the DC offset and the largest waveform data-point exceed the range,
            DAC output overflow will occur and the output will be corrupted.
        """
        element_instance = self.elements[element]
        element_instance.outputs[output].set_dc_offset(offset)

    def get_input_dc_offset_by_element(self, element: str, output: str) -> float:
        """Get the current DC offset of the OPX analog input channel associated with an element.

        Args:
            element: the name of the element to get the correction for
            output: the output key name as appears in the element config
                under 'outputs'.

        Returns:
            The offset, in volts
        """
        element_instance = self.elements[element]
        return element_instance.outputs[output].get_dc_offset()

    def get_output_digital_delay(self, element: str, digital_input: str) -> int:
        """Gets the delay of the digital input of the element

        Args:
            element: The name of the element to get the delay for
            digital_input: The digital input name as appears in the
                element's config

        Returns:
            The delay
        """
        element_instance = self.elements[element]
        return element_instance.digital_inputs[digital_input].get_delay()

    def set_output_digital_delay(self, element: str, digital_input: str, delay: int) -> None:
        """Sets the delay of the digital input of the element

        Args:
            element (str): The name of the element to update delay for
            digital_input (str): The digital input name as appears in
                the element's config
            delay (int): The delay value to set to, in ns.
        """
        element_instance = self.elements[element]
        element_instance.digital_inputs[digital_input].set_delay(delay)

    def get_output_digital_buffer(self, element: str, digital_input: str) -> int:
        """Gets the buffer for digital input of the element

        Args:
            element (str): The name of the element to get the buffer for
            digital_input (str): The digital input name as appears in
                the element's config

        Returns:
            The buffer
        """
        element_instance = self.elements[element]
        return element_instance.digital_inputs[digital_input].get_buffer()

    def set_output_digital_buffer(self, element: str, digital_input: str, buffer: int) -> None:
        """Sets the buffer for digital input of the element

        Args:
            element (str): The name of the element to update buffer for
            digital_input (str): the digital input name as appears in
                the element's config
            buffer (int): The buffer value to set to, in ns.
        """
        element_instance = self.elements[element]
        element_instance.digital_inputs[digital_input].set_buffer(buffer)

    def update_oscillator_frequency(
        self,
        element: str,
        frequency_hz: float,
        update_component: Literal["upconverter", "downconverter", "both"] = "both",
    ) -> None:
        """Set the upconverter frequency or downconverter frequency of the microwave input of the element

        Args:
            element (str): The name of the element to update the correction for
            frequency_hz (float): The frequency to set to the given element
            update_component (str): The component to update the frequency for: "upconverter", "downconverter", or "both"
        """
        deprecation_message(
            method="job.update_oscillator_frequency",
            deprecated_in="1.2.2",
            removed_in="2.0.0",
            details="Use job.set_converter_frequency.",
        )
        self.set_converter_frequency(element, frequency_hz, update_component)

    def set_converter_frequency(
        self,
        element: str,
        frequency_hz: float,
        update_component: Literal["upconverter", "downconverter", "both"] = "both",
    ) -> None:
        """Set the upconverter frequency or downconverter frequency of the microwave input of the element

        Args:
            element (str): The name of the element to update the correction for
            frequency_hz (float): The frequency to set to the given element
            update_component (str): The component to update the frequency for: "upconverter", "downconverter", or "both"
        """
        if update_component == "upconverter":
            input_instance = self.elements[element].input
            if not isinstance(input_instance, MwInputApi):
                raise ValueError(f"Element {element} does not have a microwave input")
            input_instance.set_converter_frequency(frequency_hz, set_also_output=False)
        elif update_component == "downconverter":
            output_instance = self.elements[element].microwave_output
            output_instance.set_oscillator_frequency(frequency_hz)
        elif update_component == "both":
            input_instance = self.elements[element].input
            if isinstance(input_instance, MwInputApi):
                input_instance.set_converter_frequency(
                    frequency_hz, set_also_output=self.elements[element].has_mw_output
                )
            else:
                output_instance = self.elements[element].microwave_output
                output_instance.set_oscillator_frequency(frequency_hz)
        else:
            raise ValueError(f"Invalid update_component: {update_component}")


class JobApiWithDeprecations(JobApi):
    @property
    def status(self) -> str:
        """Returns the status of the job, one of the following strings:
        "unknown", "pending", "running", "completed", "canceled", "loading", "error"
        """
        new_status = self.get_status()
        old_api_status = {
            "In queue": "pending",
            "Running": "running",
            "Processing": "running",
            "Done": "completed",
            "Canceled": "canceled",
            "Error": "error",
        }[new_status]
        return old_api_status

    @property
    def user_added(self) -> None:
        return None

    @property
    def time_added(self) -> None:
        return None

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
                details="This method was renamed to `job.push_to_input_stream()`.",
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        self.push_to_input_stream(name, data)

    def push_to_input_stream(self, name: str, data: List[Value]) -> None:
        """Push data to the input stream declared in the QUA program.
        The data is then ready to be read by the program using the advance input stream QUA statement.
        The type of QUA variable is inferred from the python type passed to ``data`` according to the following rule:

        int -> int
        float -> fixed
        bool -> bool

        When sending a list (into a QUA array), all data must be of the same type.

        Multiple data entries can be pushed before the data is read by the program.

        See [Input streams](../Guides/features.md#input-streams) for more information.

        Args:
            name: The input stream name the data is to be pushed to.
            data: The data to be pushed. The data's size & type must match
                the size & type of the input stream.
        """
        if not isinstance(data, list):
            data = [data]
        super().push_to_input_stream(name, data)

    def halt(self) -> bool:
        """Halts the job on the opx"""
        warnings.warn(
            deprecation_message(
                method="job.halt",
                deprecated_in="1.2.0",
                removed_in="2.0.0",
                details="This method was renamed to `job.cancel`.",
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        self.cancel()
        return True

    def wait_for_execution(self, timeout: Optional[float] = None) -> "JobApi":
        """Deprecated - This method is going to be removed, please use `job.wait_until("Running")`.

        Waits until the job has passed the "Running" state.
        If the timeout is reached, the function will raise an error.

        Args:
            timeout: The timeout time, in seconds

        Returns:
             The running job
        """
        warnings.warn(
            deprecation_message(
                method="job.wait_for_execution",
                deprecated_in="1.2.0",
                removed_in="2.0.0",
                details='This method is going to be removed, please use `job.wait_until("Running")`.',
            ),
            DeprecationWarning,
            stacklevel=2,
        )

        if timeout is None:
            timeout = 60 * 60 * 24 * 365  # 1 year

        self.wait_until({"Running"}, timeout)
        return self
