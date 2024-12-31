from dataclasses import dataclass

from qm.grpc import qm_manager


@dataclass
class Controller:
    name: str

    @staticmethod
    def build_from_message(message: qm_manager.Controller) -> "Controller":
        return Controller(message.name)
