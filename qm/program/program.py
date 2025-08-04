from pathlib import Path
from typing import Set, Union, Optional, FrozenSet

from qm.grpc.qua import QuaProgram
from qm.grpc.qua_config import QuaConfig
from qm.api.models.capabilities import Capability
from qm.exceptions import ProgramScopeAccessError
from qm.program._qua_config_schema import load_config
from qm.type_hinting.config_types import FullQuaConfig


class Program:
    def __init__(self, program: Optional[QuaProgram] = None) -> None:
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
        self._used_capabilities: Set[Capability] = set()
        self._is_in_scope = False

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
    def used_capabilities(self) -> FrozenSet[Capability]:
        self._ensure_not_in_scope()
        return frozenset(self._used_capabilities)

    def is_in_scope(self) -> bool:
        return self._is_in_scope

    def to_protobuf(self, config: FullQuaConfig) -> bytes:
        """
        Serialize the program to a protobuf binary.
        """
        self._ensure_not_in_scope()
        loaded_config = load_config(config)
        copy = QuaProgram().from_dict(self.qua_program.to_dict())
        copy.config = QuaConfig().from_dict(loaded_config.to_dict())
        return bytes(copy)

    @classmethod
    def from_protobuf(cls, binary: bytes) -> "Program":
        """
        Deserialize the program from a protobuf binary.
        """
        program = QuaProgram().parse(binary)
        return cls(program=program)

    def to_file(self, path: Union[str, Path], config: FullQuaConfig) -> None:
        """
        Serialize the program to a protobuf binary and write it to a file.
        """
        self._ensure_not_in_scope()
        if isinstance(path, str):
            path = Path(path)
        path.write_bytes(self.to_protobuf(config))

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "Program":
        """
        Deserialize the program from a protobuf binary file.
        """
        if isinstance(path, str):
            path = Path(path)
        return cls.from_protobuf(path.read_bytes())

    # -------- Protected API (Internal Builder Methods) --------
    def _set_in_scope(self) -> None:
        self._is_in_scope = True

    def _set_and_exit(self, program: QuaProgram, used_capabilities: Set[Capability]) -> None:
        self._program = program
        self._used_capabilities = used_capabilities
        self._is_in_scope = False
