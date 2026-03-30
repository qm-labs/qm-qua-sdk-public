from dataclasses import dataclass

from qm.grpc.qm.pb import inc_qua_config_pb2


@dataclass(frozen=True)
class QuantumMachineData:
    machine_id: str
    config: inc_qua_config_pb2.QuaConfig
