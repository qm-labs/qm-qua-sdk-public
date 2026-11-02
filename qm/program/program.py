from pathlib import Path
from collections.abc import Collection

from qm.grpc.qm.pb.inc_qua_pb2 import QuaProgram
from qm.api.models.capabilities import Capability
from qm.exceptions import ProgramScopeAccessError
from qm.program._qua_config_schema import load_config
from qm.type_hinting.config_types import FullQuaConfig
from qm.config import AnyElement, LogicalConfig, FullConfigModel, ControllerConfig


class Program:
    def __init__(self, program: QuaProgram | None = None) -> None:
        """
        The `Program` class encapsulates a `QuaProgram` protobuf object along with additional metadata.
        It provides properties to access the program's state, including the capabilities used and
        whether it is currently being edited (`is_in_scope`). Additionally, it includes methods to
        serialize and deserialize the `QuaProgram` to and from various formats.

        This class is used internally during construction (within `ProgramScope`) and externally
        as a read-only API for users. Protected methods (prefixed with `_`) are intended only
        for internal use during the building phase.
        """
        self._program = program
        self._used_capabilities: set[Capability] = set()
        self._is_in_scope = False
        self._elements: Collection[AnyElement] = ()
        self.needs_external_config = False

    def _ensure_not_in_scope(self) -> None:
        if self._is_in_scope:
            raise ProgramScopeAccessError()

    # -------- Public API (for users) --------
    @property
    def qua_program(self) -> QuaProgram:
        self._ensure_not_in_scope()
        if self._program is None:
            # This should technically never occur, but since "_program" is defined as Optional in the constructor, this check is required to satisfy mypy.
            raise RuntimeError("Program is not set")
        return self._program

    @property
    def used_capabilities(self) -> frozenset[Capability]:
        self._ensure_not_in_scope()
        return frozenset(self._used_capabilities)

    @property
    def elements(self) -> Collection[AnyElement]:
        return tuple(self._elements)

    @property
    def qua_config(self) -> FullConfigModel:
        self._ensure_not_in_scope()
        return FullConfigModel(LogicalConfig(self._elements))

    def get_controller_config(self, init_mode: bool = True) -> ControllerConfig:
        self._ensure_not_in_scope()
        return self.qua_config.get_controller_config(init_mode=init_mode)

    def is_in_scope(self) -> bool:
        return self._is_in_scope

    def to_protobuf(self, config: FullQuaConfig) -> bytes:
        """
        Serialize the program to a protobuf binary.

        Args:
            config: The QUA configuration to embed in the serialized program.

        Returns:
            The serialized program as a protobuf binary.
        """
        self._ensure_not_in_scope()
        loaded_config = load_config(config)
        copy = QuaProgram()
        copy.CopyFrom(self.qua_program)
        copy.config.CopyFrom(loaded_config)
        return copy.SerializeToString()

    @classmethod
    def from_protobuf(cls, binary: bytes) -> "Program":
        """
        Deserialize the program from a protobuf binary.

        Args:
            binary: The protobuf binary to deserialize.

        Returns:
            The deserialized program.
        """
        program = QuaProgram()
        program.ParseFromString(binary)
        return cls(program=program)

    def to_file(self, path: str | Path, config: FullQuaConfig) -> None:
        """
        Serialize the program to a protobuf binary and write it to a file.

        Args:
            path: The file path to write the serialized program to.
            config: The QUA configuration to embed in the serialized program.
        """
        self._ensure_not_in_scope()
        if isinstance(path, str):
            path = Path(path)
        path.write_bytes(self.to_protobuf(config))

    @classmethod
    def from_file(cls, path: str | Path) -> "Program":
        """
        Deserialize the program from a protobuf binary file.

        Args:
            path: The file path to read the serialized program from.

        Returns:
            The deserialized program.
        """
        if isinstance(path, str):
            path = Path(path)
        return cls.from_protobuf(path.read_bytes())

    # -------- Protected API (Internal Builder Methods) --------
    def _set_in_scope(self) -> None:
        self._is_in_scope = True

    def _set_and_exit(
        self,
        program: QuaProgram,
        used_capabilities: set[Capability],
        elements: Collection[AnyElement],
    ) -> None:
        self._program = program
        self._used_capabilities = used_capabilities
        self._elements = elements
        self._is_in_scope = False
