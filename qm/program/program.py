from pathlib import Path
from typing import Set, Union, Optional, FrozenSet

from qm import DictQuaConfig
from qm.grpc.qua_config import QuaConfig
from qm.api.models.capabilities import Capability
from qm.program._qua_config_schema import load_config
from qm.program._ResultAnalysis import _ResultAnalysis
from qm.program.StatementsCollection import StatementsCollection
from qm.grpc.qua import (
    QuaProgram,
    QuaProgramScript,
    QuaResultAnalysis,
    QuaProgramVarDeclaration,
    QuaProgramStatementsCollection,
)


class Program:
    def __init__(
        self,
        config: Optional[QuaConfig] = None,
        program: Optional[QuaProgram] = None,
    ):
        if program is None:
            program = QuaProgram(
                script=QuaProgramScript(variables=[], body=QuaProgramStatementsCollection(statements=[])),
                result_analysis=QuaResultAnalysis(model=[]),
            )

        self._program = program
        self._qua_config = config
        self._result_analysis = _ResultAnalysis(self._program.result_analysis)
        self._is_in_scope = False
        self._used_capabilities: Set[Capability] = set()

    def add_declaration(self, declaration: QuaProgramVarDeclaration) -> None:
        self._program.script.variables.append(declaration)

    @property
    def body(self) -> StatementsCollection:
        return StatementsCollection(self._program.script.body)

    @property
    def result_analysis(self) -> _ResultAnalysis:
        return self._result_analysis

    @property
    def qua_program(self) -> QuaProgram:
        return self._program

    def to_protobuf(self, config: DictQuaConfig) -> bytes:
        """
        Serialize the program to a protobuf binary.
        """
        loaded_config = load_config(config)
        copy = QuaProgram().from_dict(self._program.to_dict())
        copy.config = QuaConfig().from_dict(loaded_config.to_dict())
        return bytes(copy)

    @classmethod
    def from_protobuf(cls, binary: bytes) -> "Program":
        """
        Deserialize the program from a protobuf binary.
        """
        program = QuaProgram().parse(binary)
        return cls(program=program, config=program.config)

    def to_file(self, path: Union[str, Path], config: DictQuaConfig) -> None:
        """
        Serialize the program to a protobuf binary and write it to a file.
        """
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

    def set_in_scope(self) -> None:
        self._is_in_scope = True

    def set_exit_scope(self) -> None:
        self._is_in_scope = False

    def is_in_scope(self) -> bool:
        return self._is_in_scope

    @property
    def used_capabilities(self) -> FrozenSet[Capability]:
        return frozenset(self._used_capabilities)

    def add_used_capability(self, capability: Capability) -> None:
        self._used_capabilities.add(capability)
