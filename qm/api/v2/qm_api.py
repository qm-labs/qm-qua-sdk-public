import logging
import contextlib
from typing import (
    List,
    Type,
    Tuple,
    Union,
    Literal,
    Mapping,
    TypeVar,
    Iterable,
    Optional,
    Protocol,
    Sequence,
    Generator,
    TypedDict,
    cast,
    overload,
)

from qm.utils import LOG_LEVEL_MAP
from qm.octave import QmOctaveConfig
from qm.api.v2.base_api_v2 import BaseApiV2
from qm.program import Program, load_config
from qm.grpc.compiler import CompilerMessage
from qm.elements_db import init_octave_elements
from qm.grpc.frontend import SimulatedResponsePart
from qm.octave.octave_manager import OctaveManager
from qm.simulate.interface import SimulationConfig
from qm.grpc.qm_manager import ConfigValidationMessage
from qm.elements.element import NewApiUpconvertedElement
from qm.api.models.server_details import ConnectionDetails
from qm.utils.config_utils import get_controller_pb_config
from qm.api.simulation_api import create_simulation_request
from qm.api.v2.job_api.simulated_job_api import SimulatedJobApi
from qm.elements.up_converted_input import UpconvertedInputNewApi
from qm.api.models.capabilities import QopCaps, ServerCapabilities
from qm.grpc.qua_config import QuaConfig, QuaConfigCorrectionEntry
from qm.program._dict_to_pb_converter import DictToQuaConfigConverter
from qm.program._fill_defaults_in_config_v1 import fill_defaults_in_config_v1
from qm.api.v2.job_api.job_api import JobApi, JobData, JobStatus, transfer_statuses_to_enum
from qm.octave.qm_octave import QmOctaveForNewApi, create_mixer_correction, create_dc_offset_octave_update
from qm.type_hinting.config_types import FullQuaConfig, MixerConfigType, LogicalQuaConfig, ControllerQuaConfig
from qm.api.models.compiler import CompilerOptionArguments, standardize_compiler_params, get_request_compiler_options
from qm.octave.octave_mixer_calibration import (
    AutoCalibrationParams,
    MixerCalibrationResults,
    LOFrequencyCalibrationResult,
    NewApiOctaveMixerCalibration,
)
from qm.exceptions import (
    QopResponseError,
    CompilationException,
    JobNotFoundException,
    QopConfigValidationError,
    OctaveUnsupportedOnUpdate,
    FailedToExecuteJobException,
    UnsupportedCapabilitiesError,
)
from qm.grpc.v2 import (
    QmServiceStub,
    JobsQueryParams,
    RemoveJobsRequest,
    UpdateConfigRequest,
    QmServiceCloseRequest,
    QmServiceCompileRequest,
    QmServiceGetJobsRequest,
    QmServiceSimulateRequest,
    QmServiceGetConfigRequest,
    QmServiceAddToQueueRequest,
    ResetDigitalFiltersRequest,
    QmServiceAddCompiledToQueueRequest,
)

logger = logging.getLogger(__name__)


def _log_messages(messages: List[CompilerMessage]) -> None:
    for message in messages:
        logger.log(LOG_LEVEL_MAP[message.level], message.message)


class ErrorResponseWithConfigValidationErrors(Protocol):
    config_validation_errors: List[ConfigValidationMessage]
    messages: List[CompilerMessage]


def get_formatted_errors(error: ErrorResponseWithConfigValidationErrors) -> str:
    # Check if the exception is due to config validation errors
    if error.config_validation_errors:
        formatted_errors = str(QopConfigValidationError(error.config_validation_errors))
        logger.error(formatted_errors)
        return formatted_errors
    else:
        # Check if the exception is due to some other reason
        error_messages = []
        for msg in error.messages:
            lvl = LOG_LEVEL_MAP[msg.level]
            if lvl == logging.ERROR:
                error_messages.append(msg.message)
            logger.log(lvl, msg.message)

        return "\n".join(error_messages)


E = TypeVar("E", bound=Exception)


@contextlib.contextmanager
def handle_qop_error(custom_error: E) -> Generator[None, None, None]:
    """
    A context manager that catches QopResponseError exceptions and enriches the `custom_error` with additional details
    about the cause.
    """
    try:
        yield
    except QopResponseError as qop_error:
        logger.error(str(custom_error))

        try:
            formatted_errors = get_formatted_errors(qop_error.error)
            raise type(custom_error)(
                f"{str(custom_error)}. See the following errors:\n{formatted_errors}"
            ) from qop_error
        # In case the error doesn't have the expected fields (defined in the  ErrorResponseWithConfigValidationErrors
        # protocol)
        except AttributeError:
            raise custom_error


@contextlib.contextmanager
def handle_simulation_error() -> Generator[None, None, None]:
    with handle_qop_error(FailedToExecuteJobException("Job failed. Failed to execute program")):
        yield


class QmApi(BaseApiV2[QmServiceStub]):
    SIMULATED_JOB_CLASS = SimulatedJobApi

    def __init__(
        self,
        connection_details: ConnectionDetails,
        qm_id: str,
        capabilities: ServerCapabilities,
        octave_config: Optional[QmOctaveConfig],
        octave_manager: OctaveManager,
        pb_config: Optional[QuaConfig] = None,
    ) -> None:
        # todo - remove _pb_config when octave config is in the GW
        super().__init__(connection_details)
        self._caps = capabilities
        self._id = qm_id
        pb_config = pb_config or self._get_pb_config()
        self._elements = init_octave_elements(pb_config, octave_config)
        self._octave_manager = octave_manager
        self._octave = QmOctaveForNewApi(self, octave_manager)
        self._octave_already_configured = get_controller_pb_config(pb_config).octaves != {}

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

    def _convert_config_param_to_pb(
        self, config: Optional[Union[FullQuaConfig, LogicalQuaConfig]], function_name: str
    ) -> Optional[QuaConfig]:
        """
        Validates the config_v2 capability and converts the config to proto format.
        """
        if config:
            self._validate_capability_for_config_param(function_name)
            return self._load_config_with_exception_handling(config, function_name)
        return None

    def _validate_capability_for_config_param(self, function_name: str) -> None:
        """
        Validates that there is a config_v2 capability, since only from config_v2 (QOP 3.5) it is possible to pass a
        config to the api functions (which use this function for validation).
        """
        if not self._caps.supports(QopCaps.config_v2):
            raise UnsupportedCapabilitiesError(
                f"Passing a config to qm.{function_name}() is supported from QOP {QopCaps.config_v2.from_qop_version} and above."
            )

    def _load_config_with_exception_handling(
        self, config: Union[FullQuaConfig, ControllerQuaConfig, LogicalQuaConfig], function_name: str
    ) -> QuaConfig:
        try:
            return load_config(config, init_mode=False, octave_already_configured=self._octave_already_configured)
        except OctaveUnsupportedOnUpdate as e:
            raise OctaveUnsupportedOnUpdate(
                "Changing the octave parameters in an open QM is currently not "
                f"supported for qm.{function_name}. Please use the qm.octave functions instead."
            ) from e

    def update_config(self, config: ControllerQuaConfig) -> None:
        """Updates the controller config in the `QuantumMachine`.
        The controller config includes the "controllers", "octaves" & "mixers" sections.
        Updating the config will only update future jobs that were not executed or compiled yet.
        It will also update the idle values (e.g. DC Offset) which will be active between programs.

        Args:
            config: The physical config
        """
        config_pb = self._load_config_with_exception_handling(config, self.update_config.__name__)
        request = UpdateConfigRequest(quantum_machine_id=self._id, config=config_pb)
        self._run(self._stub.update_config(request, timeout=self._timeout))

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
        config = response.config
        fill_defaults_in_config_v1(config)
        return config

    def get_config(self) -> FullQuaConfig:
        """Gets the current config of the qm

        Returns:
            A dictionary with the QMs config
        """
        converter = DictToQuaConfigConverter(self._caps)
        return converter.deconvert(self._get_pb_config())

    def compile(
        self,
        program: Program,
        compiler_options: Optional[CompilerOptionArguments] = None,
        *,
        config: Optional[Union[FullQuaConfig, LogicalQuaConfig]] = None,
    ) -> str:
        """Compiles a QUA program to be executed later. The returned `program_id`
        can then be directly added to the queue. For a detailed explanation
        see [Precompile Jobs](../Guides/features.md#precompile-jobs).

        Args:
            program: A QUA program
            compiler_options: Optional arguments for compilation
            config: -- Available from QOP 3.5 --
                The configuration used with the program. The logical config is required if it was not supplied to the `QuantumMachine`.
                A full configuration (containing both logical and controller configs), can be used to override the default `QuantumMachine` settings.

        Returns:
            a program_id str

        Example:
            ```python
            program_id = qm.compile(program)
            job = qm.add_to_queue(program_id)
            job.wait_until("running")
            ```
        """
        self._caps.validate(program.used_capabilities)

        pb_config = self._convert_config_param_to_pb(config, self.compile.__name__)

        if compiler_options is None:
            compiler_options = CompilerOptionArguments()
        program.qua_program.compiler_options = get_request_compiler_options(compiler_options)
        request = QmServiceCompileRequest(
            quantum_machine_id=self._id, high_level_program=program.qua_program, config=pb_config
        )
        with handle_qop_error(CompilationException("Compilation failed")):
            response = self._run(self._stub.compile(request, timeout=self._timeout))

        _log_messages(response.messages)
        return response.program_id

    def _add_compiled(self, program_id: str) -> JobApi:
        request = QmServiceAddCompiledToQueueRequest(quantum_machine_id=self._id, program_id=program_id)
        response = self._run(self._stub.add_compiled_to_queue(request, timeout=self._timeout))
        return self._get_job(response.job_id)

    def _add_program(self, program: Program, config: Optional[QuaConfig]) -> JobApi:
        request = QmServiceAddToQueueRequest(
            quantum_machine_id=self._id, high_level_program=program.qua_program, config=config
        )
        with handle_qop_error(FailedToExecuteJobException("Failed to execute program")):
            response = self._run(self._stub.add_to_queue(request, timeout=self._timeout))

        _log_messages(response.messages)
        return self._get_job(response.job_id)

    @overload
    def add_to_queue(self, program: str) -> JobApi:
        pass

    @overload
    def add_to_queue(
        self,
        program: Program,
        *,
        config: Optional[Union[FullQuaConfig, LogicalQuaConfig]] = None,
        compiler_options: Optional[CompilerOptionArguments] = None,
    ) -> JobApi:
        pass

    def add_to_queue(
        self,
        program: Union[Program, str],
        *,
        config: Optional[Union[FullQuaConfig, LogicalQuaConfig]] = None,
        compiler_options: Optional[CompilerOptionArguments] = None,
    ) -> JobApi:
        """
        Adds a QmJob to the queue.
        Programs in the queue will play as soon as possible.

        Args:
            program: A QUA program or a compiled program id
            config: -- Available from QOP 3.5 --
                The configuration used with the program. The logical config is required if it was not supplied to the `QuantumMachine`.
                A full configuration (containing both logical and controller configs), can be used to override the default `QuantumMachine` settings.
            compiler_options: Optional arguments for compilation
        Returns:
            A job object
        """
        logger.info("Adding program to queue.")

        if isinstance(program, str):
            if compiler_options:
                raise ValueError("Cannot add compiler options to a compiled program.")
            if config is not None:
                raise ValueError("Cannot add a config to a compiled program.")
            return self._add_compiled(program)
        else:
            self._caps.validate(program.used_capabilities)
            pb_config = self._convert_config_param_to_pb(config, self.add_to_queue.__name__)

            if compiler_options is None:
                compiler_options = CompilerOptionArguments()
            program.qua_program.compiler_options = get_request_compiler_options(compiler_options)
            return self._add_program(program, pb_config)

    def get_job(self, job_id: str) -> JobApi:
        """
        Get a job based on the job_id.

        Args:
            job_id: A list of jobs ids
        Returns:
            The job
        """
        jobs_data = self.get_jobs(job_ids=[job_id])
        if not jobs_data:
            raise JobNotFoundException(job_id)
        else:
            job_data = jobs_data[0]
            if self._caps.supports(QopCaps.waveform_report_endpoint) and job_data.is_simulation:
                return self._get_simulated_job(job_id)

            return self._get_job(job_id)

    def _get_job(self, job_id: str) -> JobApi:
        return JobApi(self.connection_details, job_id, self._caps)

    def _get_simulated_job(self, job_id: str, simulated: Union[SimulatedResponsePart, None] = None) -> SimulatedJobApi:
        return self.SIMULATED_JOB_CLASS(
            self.connection_details, job_id, simulated_response=simulated, capabilities=self._caps
        )

    def simulate(
        self,
        program: Program,
        simulate: SimulationConfig,
        compiler_options: Optional[CompilerOptionArguments] = None,
        *,
        config: Optional[Union[FullQuaConfig, LogicalQuaConfig]] = None,
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
            config: -- Available from QOP 3.5 --
                The configuration used with the program. The logical config is required if it was not supplied to the `QuantumMachine`.
                A full configuration (containing both logical and controller configs), can be used to override the default `QuantumMachine` settings.
            strict: This parameter is deprecated, please use `compiler_options`
            flags: This parameter is deprecated, please use `compiler_options`
        Returns:
            A ``QmJob`` object (see Job API).
        """
        self._caps.validate(program.used_capabilities)

        standardized_compiler_options = standardize_compiler_params(compiler_options, strict, flags)
        pb_config = self._convert_config_param_to_pb(config, self.simulate.__name__)

        # We put self._get_pb_config() as the value for the config argument of create_simulation_request(), just
        # because we had to fill in something so it would work. We are not going to use that value, since in the new
        # request the config could be None. This is why when building the request we use the "pb_config" variable
        # instead of the "standard_request.config".
        standard_request = create_simulation_request(
            self._get_pb_config(), program, simulate, standardized_compiler_options
        )
        request = QmServiceSimulateRequest(
            quantum_machine_id=self._id,
            high_level_program=standard_request.high_level_program,
            simulate=standard_request.simulate,
            controller_connections=standard_request.controller_connections,
            config=pb_config,
        )
        logger.info("Simulating program.")

        with handle_simulation_error():
            response = self._run(self._stub.simulate(request, timeout=self._timeout))

        _log_messages(response.messages)

        return self._get_simulated_job(response.job_id, response.simulated)

    def execute(
        self,
        program: Program,
        config: Optional[Union[FullQuaConfig, LogicalQuaConfig]] = None,
        *,
        compiler_options: Optional[CompilerOptionArguments] = None,
    ) -> JobApi:
        """Closes all running jobs in the QM, clears the queue, executes a program, wait for it to start,
        and returns a job object.

        Note:

            Calling execute will halt any currently running program and clear the current
            queue. If you want to add a job to the queue, use qm.queue.add()

        Args:
            program: A QUA ``program()`` object to execute
            config: -- Available from QOP 3.5 --
                The configuration used with the program. The logical config is required if it was not supplied to the `QuantumMachine`.
                A full configuration (containing both logical and controller configs), can be used to override the default `QuantumMachine` settings.
            compiler_options: Optional arguments for compilation.
        Returns:
            A ``QmJob`` object (see Job API).
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
        lo_if_dict: Optional[Mapping[float, Sequence[float]]] = None,
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
            update: ControllerQuaConfig = {}
            if inst.intermediate_frequency in qe_cal.image:
                update = create_dc_offset_octave_update(inst_input, i_offset=qe_cal.i0, q_offset=qe_cal.q0)

            update["mixers"] = {inst_input.mixer: self._update_mixer_corrections(qe_cal, inst_input, inst)}
            self.update_config(update)

        return res

    def _update_mixer_corrections(
        self, qe_cal: LOFrequencyCalibrationResult, inst_input: UpconvertedInputNewApi, inst: NewApiUpconvertedElement
    ) -> List[MixerConfigType]:
        mixers_corrections = []

        should_add_original_frequency = True
        for if_freq, if_cal in qe_cal.image.items():
            mixers_corrections.append(create_mixer_correction(if_freq, inst_input.lo_frequency, if_cal.fine.correction))

            if if_freq == inst.intermediate_frequency:
                should_add_original_frequency = False

        if should_add_original_frequency:
            """
            Before QOP 3.5, there was no need to add the mixers that were used when opening the QM.
            Starting with 3.5, however, the introduction of “send program with config” changed this behavior: the list
            of mixers is now completely overridden by the configuration provided in either update_config or in the
            config sent with the program. So now we need to make sure that the mixer correction for the original IF
            frequency of the element is also added, in case it was not part of the calibration.
            """
            mixers_corrections.append(self._get_original_frequency_mixer_correction(inst_input, inst))
        return mixers_corrections

    def _get_original_frequency_mixer_correction(
        self,
        inst_input: UpconvertedInputNewApi,
        inst: NewApiUpconvertedElement,
    ) -> MixerConfigType:
        current_config = self._get_pb_config()

        current_correction_entries = get_controller_pb_config(current_config).mixers.get(inst_input.mixer, None)

        if current_correction_entries is None:
            raise KeyError("There should always be a correction entry for the mixer")

        correction_matrix = self._get_correction_matrix_for_if_lo_pair(
            inst.intermediate_frequency, inst_input.lo_frequency, current_correction_entries.correction
        )

        return create_mixer_correction(inst.intermediate_frequency, inst_input.lo_frequency, correction_matrix)

    @staticmethod
    def _get_correction_matrix_for_if_lo_pair(
        if_freq: float, lo_freq: float, correction_entries: List[QuaConfigCorrectionEntry]
    ) -> Tuple[float, float, float, float]:
        for correction_entry in correction_entries:
            if correction_entry.frequency_double == if_freq and correction_entry.lo_frequency_double == lo_freq:
                matrix = correction_entry.correction
                return matrix.v00, matrix.v01, matrix.v10, matrix.v11

        raise KeyError("There should always be a correction entry for the mixer with the given IF and LO frequencies.")

    def reset_digital_filters(self) -> None:
        """
        Reset the digital filters' state, specifically to remove the “memory” of the high-pass filter.
        See [High-Pass Compensation Filter](../Guides/output_filter.md#high-pass-compensation-filter)
        for more information.
        """
        if not self._caps.supports(QopCaps.exponential_dc_gain_filter):
            raise UnsupportedCapabilitiesError(
                f"qm.reset_digital_filters() is supported from QOP {QopCaps.exponential_dc_gain_filter.from_qop_version} and above."
            )

        self._run(
            self._stub.reset_digital_filters(
                ResetDigitalFiltersRequest(quantum_machine_id=self._id), timeout=self._timeout
            )
        )


class NoRunningQmJob(Exception):
    pass


IoValue = TypedDict(
    "IoValue",
    {"io_number": Literal[1, 2], "int_value": int, "fixed_value": float, "boolean_value": bool},
    total=False,
)
