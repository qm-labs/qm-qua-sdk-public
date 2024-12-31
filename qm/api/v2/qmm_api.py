import logging
import warnings
from dataclasses import field, dataclass
from typing import Dict, List, Type, Union, Literal, Mapping, Iterable, Optional

from qm.grpc.qua import QuaProgram
from qm.utils import LOG_LEVEL_MAP
from qm.octave import QmOctaveConfig
from qm.persistence import BaseStore
from qm.grpc.qua_config import QuaConfig
from qm.api.v2.base_api_v2 import BaseApiV2
from qm.octave.octave_manager import OctaveManager
from qm.api.v2.qm_api_old import QmApiWithDeprecations
from qm.type_hinting.config_types import DictQuaConfig
from qm.api.models.capabilities import ServerCapabilities
from qm.api.models.server_details import ConnectionDetails
from qm.api.v2.qm_api import QmApi, handle_simulation_error
from qm.exceptions import OpenQmException, QopResponseError
from qm.api.v2.job_api.simulated_job_api import SimulatedJobApi
from qm.grpc.frontend import InterOpxConnection, ExecutionRequestSimulate
from qm.api.v2.job_api.job_api import JobApi, JobData, JobStatus, JobApiWithDeprecations, transfer_statuses_to_enum
from qm.grpc.v2 import (
    GetJobsRequest,
    QmmServiceStub,
    JobsQueryParams,
    GetVersionRequest,
    HealthCheckRequest,
    GetControllersRequest,
    ClearAllJobResultsRequest,
    OpenQuantumMachineRequest,
    QmmServiceSimulateRequest,
    CloseAllQuantumMachinesRequest,
    ListOpenQuantumMachinesRequest,
    OpenQuantumMachineRequestCloseMode,
    QmmServiceResetDataProcessingRequest,
)

logger = logging.getLogger(__name__)


@dataclass
class VersionResponse:
    gateway: str
    controllers: Dict[str, str]


ControllerTypes = Literal["OPX", "OPX1000"]
FemTypes = Literal["LF", "MW"]
FEM_TYPES_MAPPING: Dict[int, FemTypes] = {1: "LF", 2: "MW"}


@dataclass
class ControllerBase:
    name: str

    @property
    def temperature(self) -> Optional[float]:
        return None

    @property
    def controller_type(self) -> ControllerTypes:
        raise NotImplementedError


@dataclass
class Controller(ControllerBase):
    _temperature: Optional[float] = field(repr=False)

    @property
    def temperature(self) -> Optional[float]:
        if self._temperature is None:
            logger.warning(
                "Temperature is not available for this controller, "
                "Either because it uses an old gateway or its state is not known."
            )
        return self._temperature

    @property
    def controller_type(self) -> ControllerTypes:
        return "OPX"


@dataclass
class ControllerOPX1000(ControllerBase):
    hostname: str
    fems: Dict[int, FemTypes]

    @property
    def controller_type(self) -> ControllerTypes:
        return "OPX1000"

    @property
    def temperature(self) -> Optional[float]:
        logger.warning("Temperature is not yet available for OPX1000 controllers.")
        return None


class QmmApi(BaseApiV2[QmmServiceStub]):
    QM_CLASS = QmApi
    JOB_CLASS = JobApi

    def __init__(
        self,
        connection_details: ConnectionDetails,
        store: BaseStore,
        capabilities: ServerCapabilities,
        octave_config: Optional[QmOctaveConfig],
        octave_manager: OctaveManager,
    ) -> None:
        super().__init__(connection_details)
        self._store = store
        self._caps = capabilities
        self._octave_config = octave_config
        self._octave_manager = octave_manager

    @property
    def _stub_class(self) -> Type[QmmServiceStub]:
        return QmmServiceStub

    def get_qm(self, qm_id: str, _pb_config: Optional[QuaConfig] = None) -> QmApi:
        # todo - remove _pb_config when octave config is in the GW
        return self.QM_CLASS(
            connection_details=self.connection_details,
            qm_id=qm_id,
            store=self._store,
            capabilities=self._caps,
            octave_config=self._octave_config,
            octave_manager=self._octave_manager,
            pb_config=_pb_config,
        )

    def get_job(self, job_id: str) -> JobApi:
        return self.JOB_CLASS(self.connection_details, job_id, store=self._store, capabilities=self._caps)

    def get_jobs(
        self,
        qm_ids: Iterable[str] = tuple(),
        job_ids: Iterable[str] = tuple(),
        user_ids: Iterable[str] = tuple(),
        description: str = "",
        status: Union[JobStatus, Iterable[JobStatus]] = tuple(),
    ) -> List[JobData]:
        query_params = JobsQueryParams(
            quantum_machine_ids=list(qm_ids),
            job_ids=list(job_ids),
            user_ids=list(user_ids),
            description=description,
            status=transfer_statuses_to_enum(status),
        )
        request = GetJobsRequest(query=query_params)
        response = self._run(self._stub.get_jobs(request, timeout=self._timeout))
        return [JobData.from_grpc(j) for j in response.jobs]

    def open_qm(self, config: QuaConfig, close_other_machines: Optional[bool] = None) -> QmApi:
        if close_other_machines is None:
            warnings.warn(
                "close_other_machines is not set, future default will be False, now setting to True", DeprecationWarning
            )
            close_other_machines = True
        request = OpenQuantumMachineRequest(
            config=config,
            close_mode=OpenQuantumMachineRequestCloseMode.CLOSE_MODE_IF_NEEDED
            if close_other_machines
            else OpenQuantumMachineRequestCloseMode.CLOSE_MODE_UNSPECIFIED,
        )

        try:
            response = self._run(self._stub.open_quantum_machine(request, timeout=self._timeout))

        except QopResponseError as e:
            error = e.error
            error_messages = []
            for sub_error in error.config_validation_errors:
                error_messages.append(
                    f'CONFIG ERROR in key "{sub_error.path}" [{sub_error.group}] : {sub_error.message}'
                )

            for physical_error in error.physical_validation_errors:
                error_messages.append(
                    f'PHYSICAL CONFIG ERROR in key "{physical_error.path}" [{physical_error.group}] : {physical_error.message}'
                )

            for msg in error_messages:
                logger.error(msg)

            error_details = [(item.group, item.path, item.message) for item in error.config_validation_errors] + [
                (item.group, item.path, item.message) for item in error.physical_validation_errors
            ]
            formatted_errors = "\n".join(error_messages)
            raise OpenQmException(
                f"Can not open QM, see the following errors:\n{formatted_errors}", errors=error_details
            )

        for warning in response.open_qm_warnings:
            logger.warning(f"Open QM ended with warning {warning.code}: {warning.message}")

        return self.get_qm(response.quantum_machine_id, _pb_config=config)

    def perform_healthcheck(self) -> None:
        logger.info("Performing health check")
        response = self._run(self._stub.health_check(HealthCheckRequest(), timeout=self._timeout))
        msg = "Cluster healthcheck completed successfully."
        if response.details:
            msg += " Details:"
            for k, v in response.details.items():
                msg += f"\n  {k}: {v}"
        logger.info(msg)

    def get_version(self) -> VersionResponse:
        response = self._run(self._stub.get_version(GetVersionRequest(), timeout=self._timeout))
        return VersionResponse(
            gateway=response.gateway,
            controllers={k: v for k, v in response.controllers.items()},
        )

    def get_controllers(self) -> Mapping[str, ControllerBase]:
        response = self._run(self._stub.get_controllers(GetControllersRequest(), timeout=self._timeout))
        to_return = {}
        correction_offset = 0 if self._caps.opx1000_fems_return_1_based else 1
        for name, value in response.control_devices.items():
            if value.controller_type == 1:
                to_return[name] = ControllerOPX1000(
                    name=name,
                    hostname=value.hostname,
                    fems={
                        int(i) + correction_offset: FEM_TYPES_MAPPING[f.type]
                        for i, f in value.fems.items()
                        if f.type > 0
                    },
                )
            else:
                raise NotImplementedError(f"Controller type {value.controller_type} is not supported.")
        return to_return

    def reset_data_processing(self) -> None:
        request = QmmServiceResetDataProcessingRequest()
        self._run(self._stub.reset_data_processing(request, timeout=self._timeout))

    def validate_qua_config(self, config: DictQuaConfig) -> None:
        pass

    def simulate(
        self,
        config: QuaConfig,
        program: QuaProgram,
        simulate: ExecutionRequestSimulate,
        controller_connections: List[InterOpxConnection],
    ) -> SimulatedJobApi:
        request = QmmServiceSimulateRequest(
            config=config,
            high_level_program=program,
            simulate=simulate,
            controller_connections=controller_connections,
        )
        logger.info("Simulating program.")
        try:
            response = self._run(self._stub.simulate(request, timeout=self._timeout))
        except QopResponseError as e:
            raise handle_simulation_error(e)

        for msg in response.messages:
            lvl = LOG_LEVEL_MAP[msg.level]
            logger.log(lvl, msg.message)

        return self.QM_CLASS.SIMULATED_JOB_CLASS(
            self.connection_details,
            response.job_id,
            store=self._store,
            simulated_response=response.simulated,
            capabilities=self._caps,
        )

    def list_open_qms(self) -> List[str]:
        request = ListOpenQuantumMachinesRequest()
        response = self._run(self._stub.list_open_quantum_machines(request, timeout=self._timeout))
        return response.machine_ids

    def close_all_qms(self) -> None:
        request = CloseAllQuantumMachinesRequest()
        self._run(self._stub.close_all_quantum_machines(request, timeout=self._timeout))

    def clear_all_job_results(self) -> None:
        request = ClearAllJobResultsRequest()
        self._run(self._stub.clear_all_job_results(request, timeout=self._timeout))


class QmmApiWithDeprecations(QmmApi):
    QM_CLASS = QmApiWithDeprecations
    JOB_CLASS = JobApiWithDeprecations
