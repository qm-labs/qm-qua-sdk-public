import ssl
import json
import logging
import warnings
from pathlib import Path
from collections import UserDict
from dataclasses import field, dataclass
from typing_extensions import deprecated
from typing import Any, Dict, List, Tuple, Union, Mapping, Iterable, Optional, TypedDict, Collection, overload

import marshmallow
import packaging.version

import qm
from qm.api.v2.qm_api import QmApi
from qm.user_config import UserConfig
from qm.config import ControllerConfig
from qm.utils import deprecation_message
from qm.api.frontend_api import FrontendApi
from qm.program import Program, load_config
from qm.type_hinting.general import PathLike
from qm._stream_results import StreamsManager
from qm.api.v2.job_api.job_api import JobData
from qm.quantum_machine import QuantumMachine
from qm.api.models.channel import TlsFilePaths
from qm.api.models.debug_data import DebugData
from qm.jobs.simulated_job import SimulatedJob
from qm.logging_utils import set_logging_level
from qm.octave_sdk.octave import OctaveDetails
from qm.api.v2.job_api import JobApi, JobStatus
from qm.api.server_detector import detect_server
from qm.simulate.interface import SimulationConfig
from qm.version import __version__ as qm_qua_version
from qm.api.job_result_api import JobResultServiceApi
from qm.persistence import BaseStore, SimpleFileStore
from qm.api.models.server_details import ServerDetails
from qm.grpc.qm.pb import frontend_pb2, inc_qua_config_pb2
from qm.utils.config_utils import get_controller_pb_config
from qm.octave import QmOctaveConfig, AbstractCalibrationDB
from qm.api.v2.job_api.simulated_job_api import SimulatedJobApi
from qm.utils.general_utils import is_debug, parse_proto_version
from qm._octaves_container import load_config_from_calibration_db
from qm.program._qua_config_schema import validate_config_capabilities
from qm.api.simulation_api import SimulationApi, create_simulation_request
from qm.type_hinting.config_types import FullQuaConfig, ControllerQuaConfig
from qm.octave.octave_manager import OctaveManager, prep_config_for_calibration
from qm.api.v2.qmm_api import Controller, ControllerBase, QmmApiWithDeprecations
from qm.api.models.compiler import CompilerOptionArguments, standardize_compiler_params
from qm.api.models.capabilities import QopCaps, Capability, ServerCapabilities, offline_capabilities
from qm.simulate.credentials import CredentialOverrides, create_credentials, validate_client_cert_pair
from qm.exceptions import QmmException, ConfigSchemaError, InvalidCredentialsError, ConfigValidationException
from qm._config_converters._model_to_pb_converter.converters.element_converter import (
    convert_elements,
    convert_controller_config,
)

from .utils.deprecation_utils import QmQuaDeprecationWarning
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
    QOP: Optional[str] = field(init=False)

    def __post_init__(self) -> None:
        self.QOP = _get_qop_version(self.gateway)


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
    "2.70-a0974ba": "2.6.0",
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
    "3.0-beta-10692.d6b91d0": "3.5.1",
    "3.6.0-11345.aa8a9fd": "3.6.0",
    "3.6.0-12658.702d99c": "3.6.1",
    "3.6.0-13160.a7d6ed8": "3.6.2",
    "3.6.0-16662.9f76db9": "3.6.3",
}


def _get_qop_version(server_version: str) -> Optional[str]:
    """Convert a QOP server version string to a semantic version.

    For legacy server versions, uses a hardcoded lookup map. For newer versions,
    parses the server version string by replacing hyphens with local version
    separators and extracting the base version.

    Args:
        server_version: The raw version string reported by the QOP server
            (e.g. ``"2.40-144e7bb"`` or ``"3.7.0-RC1"``).

    Returns:
        The base semantic version string (e.g. ``"2.0.0"``, ``"3.7.0"``),
        or ``None`` if the version string cannot be parsed.
    """
    if server_version in SERVER_TO_QOP_VERSION_MAP:
        return SERVER_TO_QOP_VERSION_MAP[server_version]
    try:
        return packaging.version.parse(server_version.replace("-", "+")).base_version
    except packaging.version.InvalidVersion:
        return None


@dataclass
class Devices:
    controllers: Mapping[str, ControllerBase]
    octaves: Dict[str, OctaveDetails]


def _resolve_credentials(
    credentials: Optional[Union[ssl.SSLContext, CredentialOverrides]],
) -> Tuple[Optional[ssl.SSLContext], Optional[TlsFilePaths]]:
    """Normalize ``credentials`` into an SSLContext plus the PEM file paths gRPC needs.

    grpcio cannot consume an ``ssl.SSLContext`` (it requires raw PEM bytes) and Python's
    SSLContext does not expose the loaded private key / client certificate. To support a
    custom root CA and mutual TLS (mTLS) we therefore also pass the PEM file paths down to
    the gRPC channel.

    - ``None`` -> insecure / default connection (no SSLContext, no paths).
    - ``CredentialOverrides`` -> build an SSLContext (used by the non-gRPC redirection path)
      and return the CA / client-cert / client-key paths for the gRPC channel.
    - ``ssl.SSLContext`` -> legacy path: returned as-is with no PEM paths. A custom root CA
      or client certificate cannot be recovered from an SSLContext, so for mTLS or a custom
      CA use ``CredentialOverrides`` instead.
    """
    if credentials is None:
        return None, None
    if isinstance(credentials, CredentialOverrides):
        validate_client_cert_pair(credentials.client_cert_path, credentials.client_key_path)
        try:
            ssl_context = create_credentials(credentials)
        except (OSError, ssl.SSLError) as e:
            raise InvalidCredentialsError(f"Failed to load TLS credentials from the provided paths: {e}") from e
        tls_paths = TlsFilePaths(
            ca_cert_path=credentials.certificate_path or None,
            client_cert_path=credentials.client_cert_path or None,
            client_key_path=credentials.client_key_path or None,
        )
        return ssl_context, tls_paths
    return credentials, None


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
        credentials: Optional[Union[ssl.SSLContext, CredentialOverrides]] = None,
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
            connection_headers (Dict[str, str]): Additional HTTP headers to attach to every request sent to the gateway.
            add_debug_data (bool): If True, collects debug information about the requests sent to the gateway. Defaults to False.
            credentials (ssl.SSLContext): An optional SSL context used to establish a secure (TLS) connection to the gateway.
            store (BaseStore): An object used to persist job data. Deprecated since 1.2.3; will be removed in 2.0.0.
            file_store_root (str): The root directory used by the default file-based store. Deprecated since 1.2.3; will be removed in 2.0.0.
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
            message = "Failed to connect to QuantumMachines server. No host given"
            logger.error(message)
            raise QmmException(message)

        if file_store_root is not None:
            warnings.warn(
                deprecation_message(
                    "file_store_root",
                    "1.2.3",
                    "2.0.0",
                    "This parameter is going to be removed, remove it from you initialization",
                ),
                QmQuaDeprecationWarning,
                stacklevel=2,
            )
        else:
            file_store_root = "."

        if store is not None:
            warnings.warn(
                deprecation_message(
                    "store",
                    "1.2.3",
                    "2.0.0",
                    "This parameter is going to be removed, remove it from you initialization",
                ),
                QmQuaDeprecationWarning,
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
        self._raise_warning_for_outdated_qm_qua_version()

        if self._server_details.octaves:
            if octave is None:
                octave = QmOctaveConfig()
            if octave.get_devices():
                warnings.warn(
                    "QMM was opened with OctaveConfig. Please note that from QOP2.4.0 the octave devices "
                    "are managed by the cluster setting in the QM-app. It is recommended to remove the "
                    "OctaveConfig from the QMM instantiation",
                    category=QmQuaDeprecationWarning,
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
        credentials: Optional[Union[ssl.SSLContext, CredentialOverrides]],
        connection_headers: Optional[Dict[str, str]],
        follow_gateway_redirections: bool,
        async_follow_redirects: bool,
        async_trust_env: bool,
    ) -> ServerDetails:
        ssl_context, tls_paths = _resolve_credentials(credentials)
        server_details = detect_server(
            cluster_name=self._cluster_name,
            user_token=self._user_config.user_token,
            ssl_context=ssl_context,
            tls_paths=tls_paths,
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
        offline_capabilities.set_from_implementation(server_details.qua_implementation)
        return server_details

    @property
    @deprecated(
        'qmm.store is deprecated since "1.2.3" and will be removed in "2.0.0"',
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def store(self) -> BaseStore:
        """The persistence store.

        Deprecated since 1.2.3; will be removed in 2.0.0.
        """
        if isinstance(self._store, str):
            return SimpleFileStore(self._store)
        return self._store

    @property
    def capabilities(self) -> ServerCapabilities:
        """The capabilities supported by the connected QOP server."""
        return self._caps

    @property
    def octave_manager(self) -> OctaveManager:
        """The Octave manager for this QMM instance."""
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
        """The name of the cluster this QMM is connected to, or ``"any"`` if none was specified."""
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

    @staticmethod
    def _get_local_proto_version() -> str:
        version_path = Path(qm.__file__).parent / "grpc" / "VERSION"
        return version_path.read_text().strip()

    def _raise_warning_for_outdated_qm_qua_version(self) -> None:
        """
        Raises a warning if the current qm-qua version is outdated compared to the proto used by the server.
        For example, the qm-qua used is 1.2.2, while the qop version is a newer one, which uses a proto compatible with qm-qua 1.2.3.
        We do this check by comparing between the local proto version and the proto version returned by the gateway (which contains the qm-qua version it is compatible with).
        """
        if self._server_details.proto_version is not None:
            local_proto_version = parse_proto_version(QuantumMachinesManager._get_local_proto_version())
            qop_proto_version = parse_proto_version(self._server_details.proto_version)

            if local_proto_version < qop_proto_version:
                logger.warning(
                    "You are using an outdated version of `qm-qua` which was not tested against the current QOP "
                    "version. Please consider updating to the latest qm-qua version"
                )

    @deprecated(
        'qmm.version_dict() is deprecated since "1.3.0" and will be removed in "2.0.0". '
        "Please use qmm.version() instead",
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def version_dict(self) -> Version:
        """Returns a dictionary with the qm-qua and QOP versions.

        Deprecated since 1.3.0; will be removed in 2.0.0. Use ``qmm.version()`` instead.

        Returns:
            A dictionary with the qm-qua and QOP versions
        """
        output_dict: Version = {}
        server_version = self._server_details.server_version
        output_dict["qm-qua"] = qm_qua_version
        qop_version = _get_qop_version(server_version)
        if qop_version is not None:
            output_dict["QOP"] = qop_version
        else:
            output_dict["OPX"] = server_version
        if is_debug():
            logger.debug(f"OPX version: {server_version}")

        return output_dict

    def version(self) -> DevicesVersion:
        """
        Returns:
            An object with the qm-qua and QOP versions
        """
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
            qm_qua=qm_qua_version,
            octaves=octaves,
        )

    def reset_data_processing(self) -> None:
        """
        Stops current data processing for all running jobs.

        Warning:
            Resetting the data processing is a disruptive operation.
            It should be used only as a recovery measure when the system becomes unresponsive due to heavy data processing, and is not intended for routine use.
        """
        if self._api:
            self._api.reset_data_processing()
        else:
            self._frontend.reset_data_processing()

    def open_qm(
        self,
        config: Union[FullQuaConfig, ControllerQuaConfig, ControllerConfig],
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
            close_other_machines: When set to true, any open quantum machine
                that uses resources required for the opening of the new
                quantum machine will be closed. This simplifies the workflow
                but might result in unintended closure of quantun machines.
                The default `None` behavior is currently the same as `True`.
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
            logger.warning(f"Unused kwargs: {list(kwargs)}, please remove them")
        if isinstance(config, (dict, UserDict)):  # UserDict is for validation
            loaded_config = self._load_config(config, disable_marshmallow_validation=validate_with_protobuf)
        elif isinstance(config, ControllerConfig):
            loaded_config = convert_controller_config(config, capabilities=self._caps)
        else:
            raise QmmException(f"Invalid config type - {type(config)}")

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
    ) -> inc_qua_config_pb2.QuaConfig:
        try:
            if disable_marshmallow_validation:
                loaded_config = DictToQuaConfigConverter(self.capabilities).convert(qua_config)
            else:
                loaded_config = load_config(qua_config, capabilities=self.capabilities)
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

    @deprecated(
        'qmm.open_qm_from_file is deprecated since "1.2.0" and will be removed in "2.0.0". This method is going to be removed',
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def open_qm_from_file(self, filename: str, close_other_machines: bool = True) -> Union[QuantumMachine, QmApi]:
        """Opens a new quantum machine with config taken from a file on the local file system

        Deprecated since 1.2.0; will be removed in 2.0.0.

        Args:
            filename: The path to the file that contains the config
            close_other_machines: Flag whether to close all other
                running machines

        Returns:
            A quantum machine obj that can be used to execute programs
        """
        with open(filename) as json_file:
            json1_str = json_file.read()

            def remove_nulls(d: Dict[Any, Any]) -> Dict[Any, Any]:
                return {k: v for k, v in d.items() if v is not None}

            config = json.loads(json1_str, object_hook=remove_nulls)
        return self.open_qm(config, close_other_machines)

    def _create_simulation_request(
        self,
        config: FullQuaConfig,
        program: Program,
        simulate: SimulationConfig,
        compiler_options: Optional[CompilerOptionArguments] = None,
        *,
        strict: Optional[bool] = None,
        flags: Optional[List[str]] = None,
    ) -> frontend_pb2.SimulationRequest:
        """Creates a simulate request
        Args:
        """
        standardized_options = standardize_compiler_params(compiler_options, strict, flags)
        pb_config = load_config(config)

        return create_simulation_request(pb_config, program, simulate, standardized_options, self._caps)

    @overload
    def simulate(
        self,
        config: FullQuaConfig,
        program: Program,
        simulate: SimulationConfig,
        compiler_options: Optional[CompilerOptionArguments] = None,
        *,
        strict: Optional[bool] = None,
        flags: Optional[List[str]] = None,
    ) -> Union[SimulatedJob, SimulatedJobApi]: ...

    @overload
    def simulate(
        self,
        program: Program,
        simulate: SimulationConfig,
        compiler_options: Optional[CompilerOptionArguments] = None,
        *,
        strict: Optional[bool] = None,
        flags: Optional[List[str]] = None,
    ) -> Union[SimulatedJob, SimulatedJobApi]: ...

    def simulate(  # type: ignore[misc]  # the two overloads can't share a name for the first positional (config vs program)
        self,
        config: Any = None,
        program: Any = None,
        simulate: Any = None,
        compiler_options: Any = None,
        *,
        strict: Optional[bool] = None,
        flags: Optional[List[str]] = None,
    ) -> Union[SimulatedJob, SimulatedJobApi]:
        """Simulate the outputs of a deterministic QUA program.

        This method can be called in two ways:

        - With an explicit configuration: ``simulate(config, program, simulate, ...)``.
        - Without a configuration: ``simulate(program, simulate, compiler_options=None)``.
          In this case the configuration is derived from the program itself (the typed
          config model attached to it), so no separate config dictionary is needed.

        The form is selected by the first argument: a ``Program`` means the config-less
        form, otherwise an explicit ``config`` is expected.

        Example:
            ```python
            from qm.qua import *
            from qm import SimulationConfig, QuantumMachinesManager

            qmm = QuantumMachinesManager()

            with program() as prog:
                play('pulse1', 'qe1')

            # With an explicit config:
            job = qmm.simulate(config, prog, SimulationConfig(duration=100))
            # Or, deriving the config from the program:
            job = qmm.simulate(prog, SimulationConfig(duration=100))
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
        _config: FullQuaConfig | None
        _program: Program
        _simulate: SimulationConfig
        _compiler_options: Optional[CompilerOptionArguments]
        if isinstance(config, Program):
            # Config-less form: shift the positional arguments (config holds the program).
            if compiler_options is not None and simulate is not None:
                raise ValueError(
                    "Please pass 'compiler_options' either positionally (as the third argument) "
                    "or as a keyword, not both."
                )
            _config, _program, _simulate = None, config, program
            _compiler_options = simulate if simulate is not None else compiler_options
        else:
            _config, _program, _simulate, _compiler_options = config, program, simulate, compiler_options

        if _compiler_options is not None and not isinstance(_compiler_options, CompilerOptionArguments):
            raise TypeError(
                f"'compiler_options' must be a CompilerOptionArguments instance or None, got {type(_compiler_options)}"
            )

        self._caps.validate(_program.used_capabilities)
        options = standardize_compiler_params(_compiler_options, strict, flags)
        if _config is None:
            if _program.needs_external_config:
                raise QmmException(
                    "Some of the entities in the program do not appear in the config, cannot simulate the program"
                )
            pb_config = convert_elements(_program.elements, capabilities=self._caps)
        else:
            pb_config = load_config(_config)

        if self._api:
            request = create_simulation_request(pb_config, _program, _simulate, options, self._caps)
            return self._api.simulate(
                request.config, request.highLevelProgram, request.simulate, request.controllerConnections
            )

        job_id, simulated_response_part = self._simulation_api.simulate(
            pb_config, _program, _simulate, options, self._caps
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

    @deprecated(
        'qmm.list_open_quantum_machines is deprecated since "1.2.0" and will be removed in "2.0.0". '
        "This method was renamed to `qmm.list_open_qms()`",
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def list_open_quantum_machines(self) -> List[str]:
        """Returns a list of open quantum machines.

        Deprecated since 1.2.0; will be removed in 2.0.0. Renamed to ``qmm.list_open_qms()``.

        Returns:
            A list of the ids of the currently open quantum machines.
        """
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

    def close(self) -> None:
        """Tear down the gRPC channel and release its network resources.

        Without ``close()``, the channel is pinned to the process until
        interpreter shutdown — accumulating one open connection per QMM
        instance in long-running sessions (e.g. Jupyter kernels).

        Idempotent: subsequent calls are no-ops. After ``close()`` any
        RPC method on this instance raises ``QMConnectionError``.
        """
        self._server_details.connection_details.close()

    @deprecated(
        'qmm.close_all_quantum_machines is deprecated since "1.2.0" and will be removed in "2.0.0". '
        "This function is going to change its name to `qmm.close_all_qms()`",
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def close_all_quantum_machines(self) -> None:
        """Closes all open quantum machines.

        Deprecated since 1.2.0; will be removed in 2.0.0. Renamed to ``qmm.close_all_qms()``.
        """
        self.close_all_qms()

    def get_controllers(self) -> List[ControllerBase]:
        """Returns a list of all the controllers that are available.

        Deprecated since 1.2.0; will be removed in 2.0.0. The return type will change.

        Returns:
            A list of the controllers available in the cluster.
        """
        if self._api:
            warnings.warn(
                deprecation_message(
                    "get_controllers",
                    "1.2.0",
                    "2.0.0",
                    "This will have a different return type",
                ),
                category=QmQuaDeprecationWarning,
                stacklevel=2,
            )
            new_response = self._api.get_controllers()
            return list(new_response.values())
        else:
            old_response = self._frontend.get_controllers()
            return [
                Controller(message.name, message.temperature if message.HasField("temperature") else None)
                for message in old_response
            ]

    def _get_controllers_as_dict(self) -> Mapping[str, ControllerBase]:
        if self._api:
            return self._api.get_controllers()
        else:
            old_response = self._frontend.get_controllers()
            return {
                message.name: Controller(message.name, message.temperature if message.HasField("temperature") else None)
                for message in old_response
            }

    def get_devices(self) -> Devices:
        """Returns all devices connected to the system, including controllers and Octaves.

        Returns:
            A ``Devices`` object holding the connected controllers and Octaves.
        """
        controllers = self._get_controllers_as_dict()
        octaves: Dict[str, OctaveDetails] = {}
        if self._octave_config is not None:
            for octave_name in self._octave_config.devices:
                octave_client = self._octave_manager.get_client(octave_name)
                octaves[octave_name] = octave_client.get_details()
        return Devices(controllers=controllers, octaves=octaves)

    def clear_all_job_results(self) -> None:
        """Deletes all data from all previous jobs.

        Deprecated since 1.2.0; will be removed in 2.0.0.
        """
        if self._api:
            warnings.warn(
                deprecation_message(
                    "clear_all_job_results",
                    "1.2.0",
                    "2.0.0",
                    "This method is going to be removed.",
                ),
                category=QmQuaDeprecationWarning,
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
        capabilities: Optional[Union[Collection[Capability], ServerCapabilities]] = None,
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

        offline_capabilities.set(capabilities)
