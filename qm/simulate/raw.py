from typing import List, Tuple, cast

from qm.grpc.qm.pb import frontend_pb2
from qm.api.models.capabilities import ServerCapabilities
from qm.simulate.interface import SimulatorInterface, SupportedConnectionTypes


class RawInterface(
    SimulatorInterface[frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.RawInterface.Connections]
):
    """Creates a raw interface for use in [qm.simulate.interface.SimulationConfig][].
    A raw interface defines samples that will be inputted into the OPX inputs.

    Args:
        connections (list):

            List of tuples with the connection. Each tuple should be:

                ``(toController: str, toFEM: int, toPort: int, toSamples: List[float])``
        noisePower: How much noise to add to the input.

    Example:
        ```python
        job = qmm.simulate(config, prog, SimulationConfig(
                          duration=20000,
                          # 500 ns of DC 0.2 V into con1 input 1
                          simulation_interface=RawInterface([("con1", 1, [0.2]*500)])
        ```
    """

    @classmethod
    def _validate_and_standardize_single_connection(
        cls, connection: SupportedConnectionTypes, fem_number_in_simulator: int
    ) -> frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.RawInterface.Connections:
        if not isinstance(connection, tuple):
            raise Exception("each connection must be of type tuple")
        if len(connection) == 4:
            cls._validate_connection_type(
                connection, [str, int, str, list], "(from_controller, from_fem, from_port, to_samples)"
            )
            tuple_4 = cast(Tuple[str, int, int, List[float]], connection)
            return frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.RawInterface.Connections(
                fromController=tuple_4[0], fromFem=tuple_4[1], fromPort=tuple_4[2], toSamples=tuple_4[3]
            )
        if len(connection) == 3:
            cls._validate_connection_type(connection, [str, int, list], "(from_controller, from_port, to_samples)")
            tuple_3 = cast(Tuple[str, int, List[float]], connection)
            return frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.RawInterface.Connections(
                fromController=tuple_3[0],
                fromFem=fem_number_in_simulator,
                fromPort=tuple_3[1],
                toSamples=tuple_3[2],
            )
        raise Exception("connection should be tuple of length of 3 or 4")

    def update_simulate_request(
        self, request: frontend_pb2.SimulationRequest, capabilities: ServerCapabilities
    ) -> frontend_pb2.SimulationRequest:
        request.simulate.simulationInterface.raw.CopyFrom(
            frontend_pb2.ExecutionRequest.Simulate.SimulationInterface.RawInterface(
                noisePower=self.noisePower,
                connections=self._validate_and_standardize_connections(
                    self._raw_connections, capabilities.fem_number_in_simulator
                ),
            )
        )
        return request
