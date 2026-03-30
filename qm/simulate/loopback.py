import logging
from typing import List, Tuple, cast

from qm.grpc.qm.pb import frontend_pb2
from qm.api.models.capabilities import ServerCapabilities
from qm.simulate.interface import SimulatorInterface, SupportedConnectionTypes

logger = logging.getLogger(__name__)


class LoopbackInterface(
    SimulatorInterface[frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.Loopback.Connections]
):
    """Creates a loopback interface for use in
    [qm.simulate.interface.SimulationConfig][].
    A loopback connects the output of the OPX into it's input. This can be defined
    directly using the ports or through the elements.

    Args:
        connections (list):
            List of tuples with loopback connections. Each tuple should represent physical connection between ports:

                    ``(from_controller: str, from_port: int, to_controller: str, to_port: int)``

        latency (int): The latency between the OPX outputs and its
            input.
        noisePower (float): How much noise to add to the input.

                ``(fromController: str, fromFEM: int, fromPort: int, toController: str, toFEM: int, toPort: int)``

            2. Virtual connection between elements:

                ``(fromElement: str, toElement: str, toElementInput: int)``
        latency: The latency between the OPX outputs and its input.
        noisePower: How much noise to add to the input.

    Example:
        ```python
        job = qmm.simulate(config, prog, SimulationConfig(
        duration=20000,
        # loopback from output 1 to input 2 of controller 1:
        simulation_interface=LoopbackInterface([("con1", 1, "con1", 2)])
        ```
    """

    def __init__(self, connections: List[SupportedConnectionTypes], latency: int = 24, noisePower: float = 0.0):
        super().__init__(connections, noisePower)
        self._validate_latency(latency)
        self.latency = latency

    @staticmethod
    def _validate_latency(latency: int) -> None:
        if (not isinstance(latency, int)) or latency < 0:
            raise Exception("latency must be a positive integer")

    @classmethod
    def _validate_and_standardize_single_connection(
        cls, connection: SupportedConnectionTypes, fem_number_in_simulator: int
    ) -> frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.Loopback.Connections:
        if not connection:
            logger.warning("No loopback was defined, treating as no loopback.")
        if not isinstance(connection, tuple):
            raise Exception("each connection must be of type tuple")
        if len(connection) == 6:
            cls._validate_connection_type(
                connection,
                [str, int, int, str, int, int],
                "(from_controller, from_fem, from_port, to_controller, to_fem, to_port)",
            )
            tuple_6 = connection
            return frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.Loopback.Connections(
                fromController=tuple_6[0],
                fromFem=tuple_6[1],
                fromPort=tuple_6[2],
                toController=tuple_6[3],
                toFem=tuple_6[4],
                toPort=tuple_6[5],
            )
        if len(connection) == 4:
            cls._validate_connection_type(
                connection, [str, int, str, int], "(from_controller, from_port, to_controller, to_port)"
            )
            tuple_4 = cast(Tuple[str, int, str, int], connection)
            return frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.Loopback.Connections(
                fromController=tuple_4[0],
                fromFem=fem_number_in_simulator,
                fromPort=tuple_4[1],
                toController=tuple_4[2],
                toFem=fem_number_in_simulator,
                toPort=tuple_4[3],
            )
        if len(connection) == 3:
            cls._validate_connection_type(connection, [str, str, int], "(from_Element, to_Element, to_ElementInput)")
            tuple_3 = cast(Tuple[str, str, int], connection)
            return frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.Loopback.Connections(
                fromController=tuple_3[0],
                fromFem=-1,
                fromPort=-1,
                toController=tuple_3[1],
                toFem=-1,
                toPort=tuple_3[2],
            )
        raise Exception("connection should be tuple of length 3, 4 or 6")

    def update_simulate_request(
        self, request: frontend_pb2.SimulationRequest, capabilities: ServerCapabilities
    ) -> frontend_pb2.SimulationRequest:
        if not self._raw_connections:
            request.simulate.simulationInterface.none.CopyFrom(
                getattr(frontend_pb2.ExecutionRequest.Simulate.SimulationInterface, "None")()
            )
            return request

        request.simulate.simulationInterface.loopback.CopyFrom(
            frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.Loopback(
                latency=self.latency,
                noisePower=self.noisePower,
                connections=self._validate_and_standardize_connections(
                    self._raw_connections, capabilities.fem_number_in_simulator
                ),
            )
        )
        return request
