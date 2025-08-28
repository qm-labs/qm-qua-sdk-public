import ssl
import json
import logging
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Union, Mapping, Iterable, Optional, TypedDict, Collection

import marshmallow
from octave_sdk.octave import OctaveDetails

from qm.api.v2.qm_api import QmApi
from qm.user_config import UserConfig
from qm.grpc.qua_config import QuaConfig
from qm.utils import deprecation_message
from qm.api.frontend_api import FrontendApi
from qm.program import Program, load_config
from qm.utils.general_utils import is_debug
from qm.type_hinting.general import PathLike
from qm.api.v2.job_api.job_api import JobData
from qm.quantum_machine import QuantumMachine
from qm.api.models.debug_data import DebugData
from qm.jobs.simulated_job import SimulatedJob
from qm.logging_utils import set_logging_level
from qm.api.v2.job_api import JobApi, JobStatus
from qm.api.server_detector import detect_server
from qm.simulate.interface import SimulationConfig
from qm.api.job_result_api import JobResultServiceApi
from qm.persistence import BaseStore, SimpleFileStore
from qm.api.models.server_details import ServerDetails
from qm.utils.config_utils import get_controller_pb_config
from qm.octave import QmOctaveConfig, AbstractCalibrationDB
from qm.api.v2.job_api.simulated_job_api import SimulatedJobApi
from qm._octaves_container import load_config_from_calibration_db
from qm.api.models.info import QuaMachineInfo, ImplementationInfo
from qm.program._qua_config_schema import validate_config_capabilities
from qm.api.simulation_api import SimulationApi, create_simulation_request
from qm.type_hinting.config_types import FullQuaConfig, ControllerQuaConfig
from qm.api.models.capabilities import QopCaps, Capability, ServerCapabilities
from qm.containers.capabilities_container import create_capabilities_container
from qm.octave.octave_manager import OctaveManager, prep_config_for_calibration
from qm.api.v2.qmm_api import Controller, ControllerBase, QmmApiWithDeprecations
from qm.exceptions import QmmException, ConfigSchemaError, ConfigValidationException
from qm.api.models.compiler import CompilerOptionArguments, standardize_compiler_params

from ._stream_results import StreamsManager
from .program._dict_to_pb_converter import DictToQuaConfigConverter

logger = logging.getLogger(__name__)

Version = TypedDict(
    "Version",
    {"qm-qua": str, "QOP": str, "OPX": str, "client": str, "server": str},
    total=False,
)


@dataclass
class DevicesVersion:
    gateway: str
    controllers: Dict[str, str]
    qm_qua: str
    octaves: Dict[str, str]

    @property
    def QOP(self) -> Optional[str]:
        return SERVER_TO_QOP_VERSION_MAP.get(self.gateway)


SERVER_TO_QOP_VERSION_MAP = {
    "2.40-144e7bb": "2.0.0",
    "2.40-82d4afc": "2.0.1",
    "2.40-8521884": "2.0.2",
    "2.40-3a0d7f1": "2.0.3",
    "2.50-1a24163": "2.1.3",
    "2.60-5ba458f": "2.2.0",
    "2.60-b62e6b6": "2.2.1",
    "2.60-0b17cac": "2.2.2",
    "2.70-7abf0e0": "2.4.0",
    "2.70-ed75211": "2.4.2",
    "2.70-0b3bd6b": "2.4.4",
    "2.70-cb7c3ee": "2.5.0",
    "a6f8bc5": "3.1.0",
    "fcdfb69": "3.1.1",
    "3.0-beta-78b5e00": "3.2.0",
    "3.0-beta-b43e229": "3.2.2",
    "3.0-beta-ba2d179": "3.2.3",
    "3.0-beta-eddf92b": "3.2.4",
    "3.0-beta-a3d43d5": "3.3.0",
    "3.0-beta-a59f2ea": "3.3.1",
    "3.0-beta-f47a556": "3.4.0",
    "3.0-beta-c2dd405": "3.4.1",
    "3.0-beta-4e4aa38": "3.5.0",
}


@dataclass
class Devices:
    controllers: Mapping[str, ControllerBase]
    octaves: Dict[str, OctaveDetails]


class QuantumMachinesManager:
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        *,
        cluster_name: Optional[str] = None,
        timeout: Optional[float] = None,
        log_level: Union[int, str] = logging.INFO,
        connection_headers: Optional[Dict[str, str]] = None,
        add_debug_data: bool = False,
        credentials: Optional[ssl.SSLContext] = None,
        store: Optional[BaseStore] = None,
        file_store_root: Optional[str] = None,
        octave: Optional[QmOctaveConfig] = None,
        octave_calibration_db_path: Optional[Union[PathLike, AbstractCalibrationDB]] = None,
        follow_gateway_redirections: bool = True,
        async_follow_redirects: bool = False,
        async_trust_env: bool = True,
    ):
        """
        Args:
            host (string): Host where to find the QM orchestrator. If ``None``, local settings are used.
            port: Port where to find the QM orchestrator. If None, local settings are used.
            cluster_name (string): The name of the cluster. Requires redirection between devices.
            timeout (float): The timeout, in seconds, for detecting the qmm and most other gateway API calls. Default is 60.
            log_level (Union[int, string]): The logging level for the connection instance. Defaults to `INFO`. Please check `logging` for available options.
            octave (QmOctaveConfig): The configuration for the Octave devices. Deprecated from QOP 2.4.0.
            octave_calibration_db_path (PathLike): The path for storing the Octave's calibration database. It can also be a calibration database which is an instance of `AbstractCalibrationDB`.
            follow_gateway_redirections (bool): If True (default), the client will follow redirections to find a QuantumMachinesManager and Octaves. Otherwise, it will only connect to the given host and port.
            async_follow_redirects (bool): If False (default), async httpx will not follow redirections, relevant only in case follow_gateway_redirections is True.
            async_trust_env (bool): If True (default), async httpx will read the environment variables for settings as proxy settings, relevant only in case follow_gateway_redirections is True.
        """
        set_logging_level(log_level)
        self._user_config = UserConfig.create_from_file()
        self._port = port
        host = host or self._user_config.manager_host or ""
        octave_calibration_db_path = octave_calibration_db_path or self._user_config.octave_calibration_db_path
        if host is None:
            message = "Failed to connect to QuantumMachines server. No host given."
            logger.error(message)
            raise QmmException(message)

        if file_store_root is not None:
            warnings.warn(
                deprecation_message(
                    "file_store_root",
                    "1.2.3",
                    "1.3.0",
                    "This parameter is going to be removed, remove it from you initialization",
                ),
                DeprecationWarning,
                stacklevel=2,
            )
        else:
            file_store_root = "."

        if store is not None:
            warnings.warn(
                deprecation_message(
                    "store",
                    "1.2.3",
                    "1.3.0",
                    "This parameter is going to be removed, remove it from you initialization",
                ),
                DeprecationWarning,
                stacklevel=2,
            )

        self._cluster_name = cluster_name
        self._store = store if store else file_store_root
        self._server_details = self._initialize_connection(
            host=host,
            port=port,
            timeout=timeout,
            add_debug_data=add_debug_data,
            connection_headers=connection_headers,
            credentials=credentials,
            follow_gateway_redirections=follow_gateway_redirections,
            async_follow_redirects=async_follow_redirects,
            async_trust_env=async_trust_env,
        )
        if self._server_details.octaves:
            if octave is None:
                octave = QmOctaveConfig()
            if octave.get_devices():
                warnings.warn(
                    "QMM was opened with OctaveConfig. Please note that from QOP2.4.0 the octave devices "
                    "are managed by the cluster setting in the QM-app. It is recommended to remove the "
                    "OctaveConfig from the QMM instantiation.",
                    category=DeprecationWarning,
                )
            else:
                for name, info in self._server_details.octaves.items():
                    octave.add_device(name, info)
        elif octave is not None:
            opx_headers = self._server_details.connection_details.headers
            for _, device in octave.get_devices().items():
                device.headers = {**opx_headers, **device.headers}

        self._caps = self._server_details.capabilities
        self._frontend = FrontendApi(self._server_details.connection_details)
        self._simulation_api = SimulationApi(self._server_details.connection_details)
        self._octave_config = octave
        self._octave_manager_cached: Optional[OctaveManager] = None

        self._perform_octaves_healthcheck_if_needed()

        self._api = None
        if self._caps.supports(QopCaps.qop3):
            self._api = QmmApiWithDeprecations(
                self._server_details.connection_details,
                capabilities=self._caps,
                octave_config=self._octave_config,
                octave_manager=self._octave_manager,
            )
            self._api.perform_healthcheck()
        else:
            strict = self._user_config.strict_healthcheck is not False
            self._frontend.healthcheck(strict)

        if octave_calibration_db_path is not None and self._octave_config:
            if self._octave_config.calibration_db is not None:
                raise QmmException(
                    "Duplicate calibration_db path detected, please set the calibration db only through the QMM."
                )
            else:
                self._octave_config.set_calibration_db_without_warning(octave_calibration_db_path)

    def _initialize_connection(
        self,
        host: str,
        port: Optional[int],
        timeout: Optional[float],
        add_debug_data: bool,
        credentials: Optional[ssl.SSLContext],
        connection_headers: Optional[Dict[str, str]],
        follow_gateway_redirections: bool,
        async_follow_redirects: bool,
        async_trust_env: bool,
    ) -> ServerDetails:
        server_details = detect_server(
            cluster_name=self._cluster_name,
            user_token=self._user_config.user_token,
            ssl_context=credentials,
            host=host,
            port_from_user_config=self._user_config.manager_port,
            user_provided_port=port,
            add_debug_data=add_debug_data,
            timeout=timeout,
            extra_headers=connection_headers,
            follow_gateway_redirections=follow_gateway_redirections,
            async_follow_redirects=async_follow_redirects,
            async_trust_env=async_trust_env,
        )
        create_capabilities_container(server_details.qua_implementation)
        return server_details

    @property
    def store(self) -> BaseStore:
        warnings.warn(
            deprecation_message("qmm.store", "1.2.3", "1.3.0"),
            DeprecationWarning,
            stacklevel=2,
        )
        if isinstance(self._store, str):
            return SimpleFileStore(self._store)
        return self._store

    @property
    def capabilities(self) -> ServerCapabilities:
        return self._caps

    @property
    def octave_manager(self) -> OctaveManager:
        # warnings.warn(
        #     "Do not use OctaveManager, it will be removed in the next version", DeprecationWarning, stacklevel=2
        # )
        return self._octave_manager

    @property
    def _octave_manager(self) -> OctaveManager:
        """
        There are two flows of initialization:
        1. (Healthcheck is supported in GW) - in this case, we first initialize the qmm and then, when we see that the
           Octaves are healthy, we initialize the Octave manager (when needed).
        2. (Healthcheck is not supported in GW) - in this case, we first initialize the qmm and create the
           Octave manager, so we will be able to use it in the healthcheck.
        """
        if self._octave_manager_cached is None:
            self._octave_manager_cached = OctaveManager(self._octave_config, self, self._caps)
        return self._octave_manager_cached

    @property
    def cluster_name(self) -> str:
        return self._cluster_name or "any"

    def perform_healthcheck(self, strict: bool = True) -> None:
        """Perform a health check against the QM server.

        Args:
            strict: Will raise an exception if health check failed
        """
        if self._api:
            self._api.perform_healthcheck()
        else:
            self._frontend.healthcheck(strict)
        self._perform_octaves_healthcheck_if_needed()

    def _perform_octaves_healthcheck_if_needed(self) -> None:
        if self._octave_config is not None and not self._caps.supports(QopCaps.octave_management):
            for octave in self._octave_config.get_devices():
                octave_client = self._octave_manager.get_client(octave)
                octave_client.perform_healthcheck()

    def version_dict(self) -> Version:
        """
        Returns:
            A dictionary with the qm-qua and QOP versions
        """
        from qm.version import __version__

        output_dict: Version = {}
        server_version = self._server_details.server_version
        output_dict["qm-qua"] = __version__
        if server_version in SERVER_TO_QOP_VERSION_MAP:
            output_dict["QOP"] = SERVER_TO_QOP_VERSION_MAP[server_version]
        else:
            output_dict["OPX"] = server_version
        if is_debug():
            logger.debug(f"OPX version: {server_version}")

        return output_dict

    def version(self) -> Union[Version, DevicesVersion]:
        """
        Returns:
            An object with the qm-qua and QOP versions
        """
        from qm.version import __version__

        octaves = {}
        if self._octave_config is not None:
            for octave_name in self._octave_config.get_devices():
                octaves[octave_name] = self._octave_manager.get_client(octave_name).get_version()

        if self._api is None:
            gateway = self._server_details.server_version
            controllers = set(self._get_controllers_as_dict())
        else:
            response = self._api.get_version()
            gateway = response.gateway
            controllers = set(response.controllers)
        return DevicesVersion(
            gateway=gateway,
            controllers={k: None for k in controllers},  # type: ignore[misc]
            qm_qua=__version__,
            octaves=octaves,
        )

    def reset_data_processing(self) -> None:
        """Stops current data processing for ALL running jobs"""
        if self._api:
            self._api.reset_data_processing()
        else:
            self._frontend.reset_data_processing()

    def open_qm(
        self,
        config: Union[FullQuaConfig, ControllerQuaConfig],
        close_other_machines: Optional[bool] = None,
        validate_with_protobuf: bool = False,
        add_calibration_elements_to_config: bool = True,
        use_calibration_data: bool = True,
        keep_dc_offsets_when_closing: bool = False,
        **kwargs: Any,
    ) -> Union[QuantumMachine, QmApi]:
        """Opens a new quantum machine. A quantum machine can use multiple OPXes, and a
        single OPX can also be used by multiple quantum machines as long as they do not
        share the same physical resources (input/output ports) as defined in the config.

        -- Available from QOP 3.5 --
        The configuration is split into two: controller config and logical config.
        When opening a QuantumMachine, the physical configuration defines the physical resources (e.g., ports), idle values (e.g., DC offsets), and port configurations.
        A full configuration (containing both logical and controller configs) can also be supplied, which will be used as the program's default.
        See the documentation website for more information.
        Args:
            config: The config that will be used by the Quantum Machine
            close_other_machines: When set to true, any open
                quantum machines will be closed. This simplifies the
                workflow but does not enable opening more than one
                quantum machine. The default `None` behavior is currently
                the same as `True`.
            validate_with_protobuf (bool): Validates config with
                protobuf instead of marshmallow. It is usually faster
                when working with large configs. Defaults to False.
            add_calibration_elements_to_config: Automatically adds config entries to allow Octave calibration.
            use_calibration_data: Automatically load updated calibration data from the calibration database into the config.
            keep_dc_offsets_when_closing: Available in QOP 2.4.2 - When closing the QM, do not change the DC offsets.

        Returns:
            A quantum machine obj that can be used to execute programs
        """
        if kwargs:
            logger.warning(f"unused kwargs: {list(kwargs)}, please remove them.")

        loaded_config = self._load_config(config, disable_marshmallow_validation=validate_with_protobuf)

        if use_calibration_data and self._octave_config is not None and self._octave_config.devices:
            if self._octave_config.calibration_db is not None:
                loaded_config = load_config_from_calibration_db(
                    loaded_config, self._octave_config.calibration_db, self._octave_config, self._caps
                )
            else:
                logger.warning("No calibration_db set in octave config, skipping loading calibration data")

        if add_calibration_elements_to_config and self._octave_config is not None and self._octave_config.devices:
            loaded_config = prep_config_for_calibration(loaded_config, self._octave_config, self._caps)

        octaves_config = get_controller_pb_config(loaded_config).octaves
        self._octave_manager.set_octaves_from_qua_config(octaves_config)

        if self._api:
            if keep_dc_offsets_when_closing:
                raise NotImplementedError("keep_dc_offsets_when_closing is not supported in the current QOP version")
            return self._api.open_qm(loaded_config, close_other_machines)

        close_other_machines = True if close_other_machines is None else close_other_machines

        if not self._caps.supports(QopCaps.keeping_dc_offsets):
            if keep_dc_offsets_when_closing:
                raise QmmException(
                    "The server does not support keeping DC offsets when closing. "
                    "Please upgrade the server to a version that supports this feature."
                )
        machine_id = self._frontend.open_qm(
            loaded_config, close_other_machines, keep_dc_offsets_when_closing=keep_dc_offsets_when_closing
        )

        return QuantumMachine(
            machine_id=machine_id,
            pb_config=loaded_config,
            frontend_api=self._frontend,
            capabilities=self._caps,
            octave_config=self._octave_config,
            octave_manager=self._octave_manager,
        )

    def _load_config(
        self, qua_config: Union[FullQuaConfig, ControllerQuaConfig], *, disable_marshmallow_validation: bool = False
    ) -> QuaConfig:
        try:
            if disable_marshmallow_validation:
                loaded_config = DictToQuaConfigConverter(self.capabilities).convert(qua_config)
            else:
                loaded_config = load_config(qua_config)
            validate_config_capabilities(loaded_config, self._caps)
            return loaded_config
        except KeyError as key_error:
            raise ConfigValidationException(f"Missing key {key_error} in config") from key_error
        except marshmallow.exceptions.ValidationError as validation_error:
            raise ConfigSchemaError(validation_error) from validation_error

    def validate_qua_config(self, qua_config: Union[FullQuaConfig, ControllerQuaConfig]) -> None:
        """
        Validates a qua config based on the connected server's capabilities.
        Raises an exception if the config is invalid.
        Args:
            qua_config: A python dict containing the qua config to validate
        """
        self._load_config(qua_config)

    def open_qm_from_file(self, filename: str, close_other_machines: bool = True) -> Union[QuantumMachine, QmApi]:
        """Opens a new quantum machine with config taken from a file on the local file system

        Args:
            filename: The path to the file that contains the config
            close_other_machines: Flag whether to close all other
                running machines

        Returns:
            A quantum machine obj that can be used to execute programs
        """
        warnings.warn(
            deprecation_message(
                "qmm.open_qm_from_file",
                "1.2.0",
                "1.3.0",
                "This method is going to be removed.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        with open(filename) as json_file:
            json1_str = json_file.read()

            def remove_nulls(d: Dict[Any, Any]) -> Dict[Any, Any]:
                return {k: v for k, v in d.items() if v is not None}

            config = json.loads(json1_str, object_hook=remove_nulls)
        return self.open_qm(config, close_other_machines)

    def simulate(
        self,
        config: FullQuaConfig,
        program: Program,
        simulate: SimulationConfig,
        compiler_options: Optional[CompilerOptionArguments] = None,
        *,
        strict: Optional[bool] = None,
        flags: Optional[List[str]] = None,
    ) -> Union[SimulatedJob, SimulatedJobApi]:
        """Simulate the outputs of a deterministic QUA program.

        The following example shows a simple execution of the simulator, where the
        associated config object is omitted for brevity.

        Example:
            ```python
            from qm.qua import *
            from qm import SimulationConfig, QuantumMachinesManager

            qmm = QuantumMachinesManager()

            with program() as prog:
                play('pulse1', 'qe1')

            job = qmm.simulate(config, prog, SimulationConfig(duration=100))
            ```
        Args:
            config: The full QUA configuration used to simulate the program, containing both the controller and logical configurations.
            program: A QUA ``program()`` object to execute
            simulate: A ``SimulationConfig`` configuration object
            compiler_options: additional parameters to pass to execute
            strict: a deprecated option for the compiler
            flags: deprecated way to provide flags to the compiler

        Returns:
            a ``QmJob`` object (see Job API).
        """
        self._caps.validate(program.used_capabilities)

        standardized_options = standardize_compiler_params(compiler_options, strict, flags)
        pb_config = load_config(config)

        if self._api:
            request = create_simulation_request(pb_config, program, simulate, standardized_options)
            simulated_job = self._api.simulate(
                request.config, request.high_level_program, request.simulate, request.controller_connections
            )
            return simulated_job
        else:
            job_id, simulated_response_part = self._simulation_api.simulate(
                pb_config, program, simulate, standardized_options
            )
            return SimulatedJob(
                job_id=job_id,
                frontend_api=self._frontend,
                capabilities=self._server_details.capabilities,
                simulated_response=simulated_response_part,
            )

    def list_open_qms(self) -> List[str]:
        """Return a list of open quantum machines. (Returns only the ids, use ``get_qm(...)`` to get the machine object)

        Returns:
            The ids list
        """
        if self._api:
            return self._api.list_open_qms()
        else:
            return self._frontend.list_open_quantum_machines()

    def list_open_quantum_machines(self) -> List[str]:
        warnings.warn(
            deprecation_message(
                "qmm.list_open_quantum_machines",
                "1.2.0",
                "1.4.0",
                "This method was renamed to `qmm.list_open_qms()`",
            )
        )
        return self.list_open_qms()

    def get_qm(self, machine_id: str) -> Union[QuantumMachine, QmApi]:
        """Gets an open quantum machine object with the given machine id

        Args:
            machine_id: The id of the open quantum machine to get

        Returns:
            A quantum machine obj that can be used to execute programs
        """
        if self._api:
            return self._api.get_qm(machine_id)

        qm_data = self._frontend.get_quantum_machine(machine_id)
        machine_id = qm_data.machine_id
        pb_config = qm_data.config

        return QuantumMachine(
            machine_id=machine_id,
            pb_config=pb_config,
            frontend_api=self._frontend,
            capabilities=self._caps,
            octave_manager=self.octave_manager,
        )

    def get_job_result_handles(self, job_id: str) -> StreamsManager:
        """
        -- Available in QOP 2.x --

        Returns the result handles for a job.
        Args:
            job_id: The job id
        Returns:
            The handles that this job generated
        """
        if self._api is not None:
            raise NotImplementedError(
                "This method is not available in the current QOP version, "
                "please use `qmm.get_job(job_id).result_handles`"
            )
        return StreamsManager(
            JobResultServiceApi(self._server_details.connection_details, job_id), self._caps, wait_until_func=None
        )

    def close_all_qms(self) -> None:
        """Closes ALL open quantum machines"""
        if self._api:
            self._api.close_all_qms()
        else:
            self._frontend.close_all_quantum_machines()

    def close_all_quantum_machines(self) -> None:
        warnings.warn(
            deprecation_message(
                "qmm.close_all_quantum_machines",
                "1.2.0",
                "1.4.0",
                "This function is going to change its name to `qmm.close_all_qms()`",
            ),
            category=DeprecationWarning,
            stacklevel=2,
        )
        self.close_all_qms()

    def get_controllers(self) -> List[ControllerBase]:
        """Returns a list of all the controllers that are available"""
        if self._api:
            warnings.warn(
                deprecation_message(
                    "get_controllers",
                    "1.2.0",
                    "1.3.0",
                    "This will have a different return type",
                ),
                category=DeprecationWarning,
                stacklevel=2,
            )
            new_response = self._api.get_controllers()
            return list(new_response.values())
        else:
            old_response = self._frontend.get_controllers()
            return [Controller(message.name, message.temperature) for message in old_response]

    def _get_controllers_as_dict(self) -> Mapping[str, ControllerBase]:
        if self._api:
            return self._api.get_controllers()
        else:
            old_response = self._frontend.get_controllers()
            return {message.name: Controller(message.name, message.temperature) for message in old_response}

    def get_devices(self) -> Devices:
        controllers = self._get_controllers_as_dict()
        octaves: Dict[str, OctaveDetails] = {}
        if self._octave_config is not None:
            for octave_name in self._octave_config.devices:
                octave_client = self._octave_manager.get_client(octave_name)
                octaves[octave_name] = octave_client.get_details()
        return Devices(controllers=controllers, octaves=octaves)

    def clear_all_job_results(self) -> None:
        """Deletes all data from all previous jobs"""
        if self._api:
            warnings.warn(
                deprecation_message(
                    "clear_all_job_results",
                    "1.2.0",
                    "1.3.0",
                    "This method is going to be removed.",
                ),
                category=DeprecationWarning,
                stacklevel=1,
            )
            self._api.clear_all_job_results()
        else:
            self._frontend.clear_all_job_results()

    def get_jobs(
        self,
        qm_ids: Iterable[str] = tuple(),
        job_ids: Iterable[str] = tuple(),
        user_ids: Iterable[str] = tuple(),
        description: str = "",
        status: Iterable[JobStatus] = tuple(),
    ) -> List[JobData]:
        """
        -- Available in QOP 3.x --

        Get jobs based on filtering criteria. All fields are optional.

        Args:
            qm_ids: A list of qm ids
            job_ids: A list of jobs ids
            user_ids: A list of user ids
            description: Jobs' description
            status: A list of job statuses
        Returns:
            A list of jobs
        """
        if self._api is None:
            raise NotImplementedError("This method is not available in the current QOP version")
        return self._api.get_jobs(
            qm_ids=qm_ids, job_ids=job_ids, user_ids=user_ids, description=description, status=status
        )

    def get_job(self, job_id: str) -> JobApi:
        """
        -- Available in QOP 3.x --

        Get a job based on the job_id.

        Args:
            job_id: A list of jobs ids
        Returns:
            The job
        """
        if self._api is None:
            raise NotImplementedError("This method is not available in the current QOP version")
        return self._api.get_job(job_id)

    @property
    def _debug_data(self) -> Optional[DebugData]:
        return self._server_details.connection_details.debug_data

    @staticmethod
    def set_capabilities_offline(
        capabilities: Optional[Union[Collection[Capability], ServerCapabilities]] = None
    ) -> None:
        """
        Some modules of the sdk cannot be run without the capabilities of the QOP server, which is automatically set
        when connecting to the server via QuantumMachinesManager (in "_initialize_connection"). This function provides
        an alternative to connecting to a QOP server via QuantumMachinesManager, by setting the capabilities
        manually and globally.

        It is possible to extract the capabilities of an existing QuantumMachinesManager object by checking the `capabilities` attribute,
        e.g. `qmm = QuantumMachinesManager(); capabilities = qmm.capabilities`.

        The QopCaps class (from `qm import QopCaps`) can be used to get and view all capabilities.

        Warning: Setting the capabilities when there is an open QuantumMachinesManager will override them and can cause unexpected behavior.

        Args:
            capabilities: A set of capabilities (or a ServerCapabilities object) to create the container with. If None,
                all capabilities are set. Warning: Using all capabilities might not produce the expected behavior.

        """
        if capabilities is None:
            capabilities = QopCaps.get_all()
        elif isinstance(capabilities, ServerCapabilities):
            capabilities = capabilities.supported_capabilities

        capabilities_qop_names = [cap.qop_name for cap in capabilities]
        create_capabilities_container(QuaMachineInfo(capabilities_qop_names, ImplementationInfo("", "", "")))
