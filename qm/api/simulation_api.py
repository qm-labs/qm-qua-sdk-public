import logging
from typing import Type, Tuple, Iterator

from qm.program import Program
from qm.simulate import interface
from qm.api.base_api import BaseApi
from qm.utils.protobuf_utils import LOG_LEVEL_MAP
from qm.simulate.interface import SimulationConfig
from qm.grpc.qm.pb.frontend_pb2_grpc import FrontendStub
from qm.api.models.capabilities import ServerCapabilities
from qm.api.models.server_details import ConnectionDetails
from qm.exceptions import QMSimulationError, FailedToExecuteJobException
from qm.grpc.qm.pb import frontend_pb2, job_results_pb2, inc_qua_config_pb2
from qm.api.models.compiler import CompilerOptionArguments, get_request_compiler_options

logger = logging.getLogger(__name__)


def create_simulation_request(
    config: inc_qua_config_pb2.QuaConfig,
    program: Program,
    simulate: SimulationConfig,
    compiler_options: CompilerOptionArguments,
    capabilities: ServerCapabilities,
) -> frontend_pb2.SimulationRequest:
    if not isinstance(program, Program):
        raise Exception("program argument must be of type qm.program.Program")

    request = frontend_pb2.SimulationRequest()

    if hasattr(config, "v1_beta"):
        config.v1_beta._unknown_fields = b""  # This correction is for a return of unknown fields from
        # an old GW, that changes the flow of the config parsing (in the GW, and to a buggy one).
        # Check a year from now (This change was done on Feb/2024) if this is still necessary.
    request.config.CopyFrom(config)

    if isinstance(simulate, SimulationConfig):
        request.simulate.CopyFrom(
            frontend_pb2.ExecutionRequest.Simulate(
                duration=simulate.duration,
                includeAnalogWaveforms=simulate.include_analog_waveforms,
                includeDigitalWaveforms=simulate.include_digital_waveforms,
                extraProcessingTimeoutMs=simulate.extraProcessingTimeoutInMs,
            )
        )
        request = simulate.update_simulate_request(request, capabilities)

        for connection in simulate.controller_connections:
            if not isinstance(connection.source, type(connection.target)):
                raise Exception(
                    f"Unsupported InterOpx connection. Source is "
                    f"{type(connection.source).__name__} but target is "
                    f"{type(connection.target).__name__}"
                )

            if isinstance(connection.source, interface.InterOpxAddress) and isinstance(
                connection.target, interface.InterOpxAddress
            ):
                con = frontend_pb2.InterOpxConnection(
                    addressToAddress=frontend_pb2.InterOpxConnection.AddressToAddress(
                        source=frontend_pb2.InterOpxAddress(
                            controller=connection.source.controller,
                            left=connection.source.is_left_connection,
                        ),
                        target=frontend_pb2.InterOpxAddress(
                            controller=connection.target.controller,
                            left=connection.target.is_left_connection,
                        ),
                    )
                )
            elif isinstance(connection.source, interface.InterOpxChannel) and isinstance(
                connection.target, interface.InterOpxChannel
            ):
                con = frontend_pb2.InterOpxConnection(
                    channelToChannel=frontend_pb2.InterOpxConnection.ChannelToChannel(
                        source=frontend_pb2.InterOpxChannel(
                            controller=connection.source.controller,
                            channelNumber=connection.source.channel_number,
                        ),
                        target=frontend_pb2.InterOpxChannel(
                            controller=connection.target.controller,
                            channelNumber=connection.target.channel_number,
                        ),
                    )
                )
            else:
                raise Exception(
                    f"Unsupported InterOpx connection. Source is "
                    f"{type(connection.source).__name__}. Supported types are "
                    f"frontend_pb2.InterOpxAddress "
                    f"or frontend_pb2.InterOpxChannel"
                )

            request.controllerConnections.append(con)

    request.highLevelProgram.CopyFrom(program.qua_program)
    request.highLevelProgram.compilerOptions.CopyFrom(get_request_compiler_options(compiler_options))
    return request


class SimulationApi(BaseApi[FrontendStub]):
    def __init__(self, connection_details: ConnectionDetails):
        super().__init__(connection_details)
        self._timeout = None

    @property
    def _stub_class(self) -> Type[FrontendStub]:
        return FrontendStub

    def simulate(
        self,
        config: inc_qua_config_pb2.QuaConfig,
        program: Program,
        simulate: SimulationConfig,
        compiler_options: CompilerOptionArguments,
        capabilities: ServerCapabilities,
    ) -> Tuple[str, frontend_pb2.SimulatedResponsePart]:
        if type(program) is not Program:
            raise Exception("program argument must be of type qm.program.Program")

        request = create_simulation_request(config, program, simulate, compiler_options, capabilities)
        logger.info("Simulating program")

        response = self._run(self._stub.Simulate, request, timeout=self._timeout)

        messages = [(LOG_LEVEL_MAP[msg.level], msg.message) for msg in response.messages]

        config_messages = [(LOG_LEVEL_MAP[msg.level], msg.message) for msg in response.configValidationErrors]

        job_id = response.jobId

        for lvl, msg in messages:
            logger.log(lvl, msg)

        for lvl, msg in config_messages:
            logger.log(lvl, msg)

        if not response.success:
            logger.error("Job " + job_id + " failed. Failed to execute program.")
            for error in response.simulated.errors:
                logger.error(f"Simulation error: {error}")
            raise FailedToExecuteJobException(job_id)

        return job_id, response.simulated

    def get_simulated_quantum_state(self, job_id: str) -> frontend_pb2.DensityMatrix:
        request = frontend_pb2.GetSimulatedQuantumStateRequest(jobId=job_id)
        response: frontend_pb2.GetSimulatedQuantumStateResponse = self._run(
            self._stub.GetSimulatedQuantumState, request, timeout=self._timeout
        )

        if response.ok:
            return response.state

        raise QMSimulationError("Error while pulling quantum state")

    def pull_simulator_samples(
        self, job_id: str, include_analog: bool, include_digital: bool
    ) -> Iterator[job_results_pb2.SimulatorSamplesResponse]:
        request = job_results_pb2.PullSimulatorSamplesRequest(
            jobId=job_id,
            includeAnalog=include_analog,
            includeDigital=include_digital,
            includeAllConnections=True,  # TODO: Check whether it should appear
        )
        return self._run_iterator(self._stub.PullSimulatorSamples, request)
