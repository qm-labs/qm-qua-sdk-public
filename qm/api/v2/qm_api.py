import logging
from typing import List, Type, Tuple, Union, Literal, Mapping, Iterable, Optional, TypedDict, cast, overload

from qm.utils import LOG_LEVEL_MAP
from qm.octave import QmOctaveConfig
from qm.persistence import BaseStore
from qm.grpc.qua_config import QuaConfig
from qm.utils.async_utils import run_async
from qm.api.v2.base_api_v2 import BaseApiV2
from qm.program import Program, load_config
from qm.grpc.compiler import CompilerMessage
from qm.elements_db import init_octave_elements
from qm.grpc.frontend import SimulatedResponsePart
from qm.octave.octave_manager import OctaveManager
from qm.simulate.interface import SimulationConfig
from qm.type_hinting.config_types import DictQuaConfig
from qm.api.models.capabilities import ServerCapabilities
from qm.api.models.server_details import ConnectionDetails
from qm.program.ConfigBuilder import convert_msg_to_config
from qm.api.simulation_api import create_simulation_request
from qm.api.v2.job_api.simulated_job_api import SimulatedJobApi
from qm.elements.up_converted_input import UpconvertedInputNewApi
from qm.api.v2.job_api.job_api import JobApi, JobData, JobStatus, transfer_statuses_to_enum
from qm.exceptions import QopResponseError, CompilationException, FailedToExecuteJobException
from qm.octave.qm_octave import QmOctaveForNewApi, create_mixer_correction, create_dc_offset_octave_update
from qm.api.models.compiler import CompilerOptionArguments, standardize_compiler_params, get_request_compiler_options
from qm.octave.octave_mixer_calibration import (
    AutoCalibrationParams,
    MixerCalibrationResults,
    NewApiOctaveMixerCalibration,
)
from qm.grpc.v2 import (
    QmServiceStub,
    JobsQueryParams,
    SimulationError,
    RemoveJobsRequest,
    UpdateConfigRequest,
    QmServiceCloseRequest,
    QmServiceCompileRequest,
    QmServiceGetJobsRequest,
    QmServiceSimulateRequest,
    QmServiceGetConfigRequest,
    QmServiceAddToQueueRequest,
    CompileResponseCompilationError,
    QmServiceAddCompiledToQueueRequest,
    AddToQueueResponseAddToQueueResponseError,
)

logger = logging.getLogger(__name__)


def _log_messages(messages: List[CompilerMessage]) -> None:
    for message in messages:
        logger.log(LOG_LEVEL_MAP[message.level], message.message)


class QmApi(BaseApiV2[QmServiceStub]):
    SIMULATED_JOB_CLASS = SimulatedJobApi

    def __init__(
        self,
        connection_details: ConnectionDetails,
        qm_id: str,
        store: BaseStore,
        capabilities: ServerCapabilities,
        octave_config: Optional[QmOctaveConfig],
        octave_manager: OctaveManager,
        pb_config: Optional[QuaConfig] = None,
    ) -> None:
        # todo - remove _pb_config when octave config is in the GW
        super().__init__(connection_details)
        self._caps = capabilities
        self._id = qm_id
        self._store = store
        pb_config = pb_config or self._get_pb_config()
        self._elements = init_octave_elements(pb_config, octave_config)
        self._octave_manager = octave_manager
        self._octave = QmOctaveForNewApi(self, octave_manager)

    @property
    def octave(self) -> QmOctaveForNewApi:
        return self._octave

    @property
    def id(self) -> str:
        """Hopefully temporary, till we move to the new API."""
        return self._id

    @property
    def _stub_class(self) -> Type[QmServiceStub]:
        return QmServiceStub

    def update_config(self, config: DictQuaConfig) -> None:
        """Updates the physical config in the QM.
        The physical config includes the "controllers", "octaves" & "mixers" sections.
        Updating the config will only update future jobs that were not executed or compiled yet.
        It will also update the idle values (e.g. DC Offset) which will be active between programs.

        Args:
            config: The physical config
        """
        config_pb = load_config(config)
        request = UpdateConfigRequest(quantum_machine_id=self._id, config=config_pb)
        run_async(self._stub.update_config(request, timeout=self._timeout))

    def get_jobs(
        self,
        job_ids: Iterable[str] = tuple(),
        user_ids: Iterable[str] = tuple(),
        description: str = "",
        status: Union[JobStatus, Iterable[JobStatus]] = tuple(),
    ) -> List[JobData]:
        """
        Get jobs based on filtering criteria. All fields are optional.

        Args:
            job_ids: A list of jobs ids
            user_ids: A list of user ids
            description: Jobs' description
            status: A list of job statuses
        Returns:
            A list of jobs
        """
        query_params = JobsQueryParams(
            quantum_machine_ids=[self._id],
            job_ids=list(job_ids),
            user_ids=list(user_ids),
            description=description,
            status=transfer_statuses_to_enum(status),
        )
        request = QmServiceGetJobsRequest(query=query_params)
        response = self._run(self._stub.get_jobs(request, timeout=self._timeout))
        return [JobData.from_grpc(j) for j in response.jobs]

    def _get_pb_config(self) -> QuaConfig:
        request = QmServiceGetConfigRequest(quantum_machine_id=self._id)
        response = self._run(self._stub.get_config(request, timeout=self._timeout))
        return response.config

    def get_config(self) -> DictQuaConfig:
        """Gets the current config of the qm

        Returns:
            A dictionary with the QMs config
        """
        return convert_msg_to_config(self._get_pb_config())

    def compile(self, program: Program, compiler_options: Optional[CompilerOptionArguments] = None) -> str:
        """Compiles a QUA program to be executed later. The returned `program_id`
        can then be directly added to the queue. For a detailed explanation
        see [Precompile Jobs](../Guides/features.md#precompile-jobs).

        Args:
            program: A QUA program
            compiler_options: Optional arguments for compilation

        Returns:
            a program_id str

        Example:
            ```python
            program_id = qm.compile(program)
            job = qm.add_to_queue(program_id)
            job.wait_until("running")
            ```
        """
        if compiler_options is None:
            compiler_options = CompilerOptionArguments()
        program.qua_program.compiler_options = get_request_compiler_options(compiler_options)
        request = QmServiceCompileRequest(quantum_machine_id=self._id, high_level_program=program.qua_program)
        try:
            response = self._run(self._stub.compile(request, timeout=self._timeout))
        except QopResponseError as e:
            error: CompileResponseCompilationError = e.error
            error_messages = []
            logger.error("Compilation failed")
            for msg in error.messages:
                logger.error(msg)
                error_messages.append(msg.message)
            formatted_errors = "\n".join(error_messages)
            raise CompilationException("Compilation failed, see the following errors:\n" + formatted_errors)

        _log_messages(response.messages)
        return response.program_id

    def _add_compiled(self, program_id: str) -> JobApi:
        request = QmServiceAddCompiledToQueueRequest(quantum_machine_id=self._id, program_id=program_id)
        response = self._run(self._stub.add_compiled_to_queue(request, timeout=self._timeout))
        return self._get_job(response.job_id, store=self._store)

    def _add_program(self, program: Program) -> JobApi:
        request = QmServiceAddToQueueRequest(quantum_machine_id=self._id, high_level_program=program.qua_program)
        try:
            response = self._run(self._stub.add_to_queue(request, timeout=self._timeout))
        except QopResponseError as e:
            error: AddToQueueResponseAddToQueueResponseError = e.error
            error_messages = []
            logger.error(f"Execution failed - {error.details}")
            for msg in error.messages:
                logger.error(msg)
                error_messages.append(msg.message)
            formatted_errors = "\n".join(error_messages)

            _log_messages(e.error.messages)
            raise FailedToExecuteJobException(
                f"Failed to execute program. See the following errors:\n{formatted_errors}"
            )
        _log_messages(response.messages)
        return self._get_job(response.job_id, store=self._store)

    @overload
    def add_to_queue(self, program: str) -> JobApi:
        pass

    @overload
    def add_to_queue(self, program: Program, *, compiler_options: Optional[CompilerOptionArguments] = None) -> JobApi:
        pass

    def add_to_queue(
        self, program: Union[Program, str], *, compiler_options: Optional[CompilerOptionArguments] = None
    ) -> JobApi:
        """
        Adds a QmJob to the queue.
        Programs in the queue will play as soon as possible.

        Args:
            program: A QUA program or a compiled program id
            compiler_options: Optional arguments for compilation
        Returns:
            A job object
        """
        logger.info("Adding program to queue.")
        if isinstance(program, str):
            if compiler_options:
                logger.warning("Cannot add compiler options to a compiled program. Ignoring.")
            return self._add_compiled(program)
        else:
            if compiler_options is None:
                compiler_options = CompilerOptionArguments()
            program.qua_program.compiler_options = get_request_compiler_options(compiler_options)
            return self._add_program(program)

    def get_job(self, job_id: str) -> JobApi:
        """
        Get a job based on the job_id.

        Args:
            job_id: A list of jobs ids
        Returns:
            The job
        """
        return self._get_job(job_id, self._store)

    def _get_job(self, job_id: str, store: BaseStore) -> JobApi:
        return JobApi(self.connection_details, job_id, store, self._caps)

    def _get_simulated_job(self, job_id: str, simulated: SimulatedResponsePart) -> SimulatedJobApi:
        return self.SIMULATED_JOB_CLASS(
            self.connection_details, job_id, store=self._store, simulated_response=simulated, capabilities=self._caps
        )

    def simulate(
        self,
        program: Program,
        simulate: SimulationConfig,
        compiler_options: Optional[CompilerOptionArguments] = None,
        *,
        strict: Optional[bool] = None,
        flags: Optional[List[str]] = None,
    ) -> SimulatedJobApi:
        """Simulates the outputs of a deterministic QUA program.

        Equivalent to ``execute()`` with ``simulate=SimulationConfig`` (see example).

        Note:
            A simulated job does not support calling QuantumMachine API functions.

        Args:
            program: A QUA ``program()`` object to execute
            simulate: If given, will be simulated instead of executed.
            compiler_options: Optional arguments for compilation.
            strict: This parameter is deprecated, please use `compiler_options`
            flags: This parameter is deprecated, please use `compiler_options`
        Returns:
            A ``QmJob`` object (see QM Job API).
        """
        standardized_compiler_options = standardize_compiler_params(compiler_options, strict, flags)
        standard_request = create_simulation_request(
            self._get_pb_config(), program, simulate, standardized_compiler_options
        )
        request = QmServiceSimulateRequest(
            quantum_machine_id=self._id,
            high_level_program=standard_request.high_level_program,
            simulate=standard_request.simulate,
            controller_connections=standard_request.controller_connections,
        )
        logger.info("Simulating program.")
        try:
            response = self._run(self._stub.simulate(request, timeout=self._timeout))
        except QopResponseError as e:
            raise handle_simulation_error(e)

        _log_messages(response.messages)

        return self._get_simulated_job(response.job_id, response.simulated)

    def execute(self, program: Program, *, compiler_options: Optional[CompilerOptionArguments] = None) -> JobApi:
        """Closes all running jobs in the QM, clears the queue, executes a program, wait for it to start,
        and returns a job object.

        Note:

            Calling execute will halt any currently running program and clear the current
            queue. If you want to add a job to the queue, use qm.queue.add()

        Args:
            program: A QUA ``program()`` object to execute
            compiler_options: Optional arguments for compilation.
        Returns:
            A ``QmJob`` object (see QM Job API).
        """
        # todo: change to an API call that stops programs, clears queue, executes, and returns job once it's running
        raise NotImplementedError()

    def clear_queue(
        self,
        job_ids: Iterable[str] = tuple(),
        user_ids: Iterable[str] = tuple(),
        description: str = "",
        status: Union[JobStatus, Iterable[JobStatus]] = tuple(),
    ) -> List[str]:
        """
        Clears jobs from the queue based on filtering criteria. All fields are optional.

        Args:
            job_ids: A list of jobs ids
            user_ids: A list of user ids
            description: Jobs' description
            status: A list of job statuses
        Returns:
            A list of the removed jobs ids
        """
        query_params = JobsQueryParams(
            quantum_machine_ids=[self._id],
            job_ids=list(job_ids),
            user_ids=list(user_ids),
            description=description,
            status=transfer_statuses_to_enum(status),
        )
        response = self._run(self._stub.remove_jobs(RemoveJobsRequest(query_params), timeout=self._timeout))
        return response.removed_job_ids

    def close(self) -> None:
        """
        Closes the quantum machine.
        """
        self._run(self._stub.close(QmServiceCloseRequest(quantum_machine_id=self._id), timeout=self._timeout))

    def get_queue_count(self) -> int:
        """
        Get the number of jobs currently on the queue

        Returns:
            The number of jobs in the queue
        """
        jobs = self.get_jobs(status=["In queue"])
        return len(jobs)

    def calibrate_element(
        self,
        qe: str,
        lo_if_dict: Optional[Mapping[float, Tuple[float, ...]]] = None,
        save_to_db: bool = True,
        params: Optional[AutoCalibrationParams] = None,
    ) -> MixerCalibrationResults:
        """Calibrate the up converters associated with a given element for the given LO & IF frequencies.

        - Frequencies can be given as a dictionary with LO frequency as the key and a list of IF frequencies for every LO
        - If no frequencies are given calibration will occur according to LO & IF declared in the element
        - The function need to be run for each element separately
        - The results are saved to a database for later use

        Args:
            qe (str): The name of the element for calibration
            lo_if_dict ([Mapping[float, Tuple[float, ...]]]): a dictionary with LO frequency as the key and
                a list of IF frequencies for every LO
            save_to_db (bool): If true (default), The calibration
                parameters will be saved to the calibration database
            params: Optional calibration parameters
        """

        inst = self._elements[qe]

        if params is None:
            params = AutoCalibrationParams()

        inst_input = inst.input
        assert isinstance(inst_input, UpconvertedInputNewApi)

        if lo_if_dict is None:
            lo_if_dict = {inst_input.lo_frequency: (inst.intermediate_frequency,)}
        client = self._octave_manager._get_client_from_port(inst_input.port)
        res = NewApiOctaveMixerCalibration(client=client, qm_api=self).calibrate(
            element=inst,
            lo_if_dict=lo_if_dict,
            params=params,
        )

        if save_to_db:
            calibration_db = self._octave_manager._octave_config._calibration_db
            if calibration_db is None:
                logger.warning("No calibration db found, can't save results")
            else:
                calibration_db.update_calibration_result(res, inst_input.port, "auto")

        key = (inst_input.lo_frequency, cast(float, inst_input.gain))
        if key in res:
            qe_cal = res[key]
            if inst.intermediate_frequency in qe_cal.image:
                update = create_dc_offset_octave_update(inst_input, i_offset=qe_cal.i0, q_offset=qe_cal.q0)
            else:
                update = {"version": 1}
            mixers = [
                create_mixer_correction(if_freq, inst_input.lo_frequency, if_cal.fine.correction)
                for if_freq, if_cal in qe_cal.image.items()
            ]
            update["mixers"] = {inst_input.mixer: mixers}
            self.update_config(update)
        return res


def handle_simulation_error(e: QopResponseError[SimulationError]) -> FailedToExecuteJobException:
    error = e.error
    logger.error("Job failed. Failed to execute program.")

    error_messages = []
    for msg in error.messages:
        lvl = LOG_LEVEL_MAP[msg.level]
        if lvl == logging.ERROR:
            error_messages.append(msg.message)
        logger.log(lvl, msg.message)

    formatted_errors = "\n".join(error_messages)

    return FailedToExecuteJobException(
        f"Job failed. Failed to execute program. see the following errors:\n{formatted_errors}"
    )


class NoRunningQmJob(Exception):
    pass


IoValue = TypedDict(
    "IoValue",
    {"io_number": Literal[1, 2], "int_value": int, "fixed_value": float, "boolean_value": bool},
    total=False,
)
