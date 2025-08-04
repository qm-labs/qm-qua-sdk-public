import abc
from collections import deque
from abc import abstractmethod
from types import TracebackType
from typing import TYPE_CHECKING, Set, Dict, List, Type, Deque, Tuple, Literal, Optional

from qm.program.program import Program
from qm.exceptions import QmQuaException
from qm.api.models.capabilities import Capability
from qm.grpc.qua import (
    QuaProgram,
    QuaProgramScript,
    QuaResultAnalysis,
    QuaProgramAnyStatement,
    QuaProgramVarDeclaration,
    QuaProgramStatementsCollection,
    QuaProgramExternalStreamDeclaration,
)

if TYPE_CHECKING:
    from qm.qua._dsl.external_stream import QuaStreamDirection
    from qm.qua._dsl.stream_processing.stream_processing import ResultStreamSource, _OutputStream

"""
The root level scopes stack. Intended for use exclusively by the base scope classes or the scopes manager.
"""
_scopes_stack: Deque["_BaseScope"] = deque()


class _BaseScope(metaclass=abc.ABCMeta):
    def __init__(self) -> None:
        self._statements: List[QuaProgramAnyStatement] = []

    def __enter__(self) -> None:
        if len(_scopes_stack) == 0 and not isinstance(self, _ProgramScope):
            raise QmQuaException("First scope must be a program scope")

        _scopes_stack.append(self)
        return None

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]
    ) -> Literal[False]:
        # Let original exception propagate
        if exc_type is not None:
            return False

        self._on_clean_exit()
        return False

    def _on_clean_exit(self) -> None:
        _scopes_stack.pop()

    @property
    def statements(self) -> List[QuaProgramAnyStatement]:
        return self._statements

    def append_statement(self, statement: QuaProgramAnyStatement) -> None:
        self._statements.append(statement)


class _ProgramScope(_BaseScope):
    def __init__(self) -> None:
        super().__init__()
        self._program = Program()

        self.var_index = 0
        self.array_index = 0
        self.struct_index = 0
        self.result_index = 0

        self._declared_variables: List[QuaProgramVarDeclaration] = []
        self._declared_streams: Dict[str, "ResultStreamSource"] = {}
        self._declared_input_streams: Set[str] = set()
        self._declared_external_streams: Dict[
            Tuple[int, "QuaStreamDirection"], QuaProgramExternalStreamDeclaration
        ] = {}

        self._used_capabilities: Set[Capability] = set()
        self._result_analysis_scope = _ResultAnalysisScope()

    def __enter__(self) -> Program:  # type: ignore[override]
        super().__enter__()
        self._program._set_in_scope()
        return self._program

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]
    ) -> Literal[False]:
        self._program._set_and_exit(self._generate_pb_qua_program(), self._used_capabilities)
        _scopes_stack.clear()
        return False

    @property
    def declared_streams(self) -> Dict[str, "ResultStreamSource"]:
        return self._declared_streams

    @property
    def declared_input_streams(self) -> Set[str]:
        return self._declared_input_streams

    @property
    def declared_external_streams(self) -> Dict[Tuple[int, "QuaStreamDirection"], QuaProgramExternalStreamDeclaration]:
        return self._declared_external_streams

    @property
    def result_analysis_scope(self) -> "_ResultAnalysisScope":
        return self._result_analysis_scope

    def add_var_declaration(self, declaration: QuaProgramVarDeclaration) -> None:
        self._declared_variables.append(declaration)

    def add_stream_declaration(self, tag: str, stream: "ResultStreamSource") -> None:
        if tag in self._declared_streams:
            raise QmQuaException(f"Stream with tag {tag} already declared")
        self._declared_streams[tag] = stream

    def add_input_stream_declaration(self, var_name: str) -> None:
        self._declared_input_streams.add(var_name)

    def add_external_stream_declaration(
        self,
        stream_identifier: Tuple[int, "QuaStreamDirection"],
        stream_declaration: QuaProgramExternalStreamDeclaration,
    ) -> None:
        self._declared_external_streams[stream_identifier] = stream_declaration

    def add_used_capability(self, capability: Capability) -> None:
        self._used_capabilities.add(capability)

    def _generate_pb_qua_program(self) -> QuaProgram:
        return QuaProgram(
            script=QuaProgramScript(
                variables=self._declared_variables,
                external_streams=list(self._declared_external_streams.values()),
                body=QuaProgramStatementsCollection(statements=self._statements),
            ),
            result_analysis=self._result_analysis_scope.generate_pb_result_analysis(),
        )


class _ResultAnalysisScope:
    def __enter__(self) -> None:
        return None

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]
    ) -> Literal[False]:
        return False

    def __init__(self) -> None:
        self._saves: List[_OutputStream] = []

    def append_output_stream(self, output_stream: "_OutputStream") -> None:
        for _save in self._saves:
            if _save.tag == output_stream.tag:
                raise Exception("can not save two streams with the same tag")
        self._saves.append(output_stream)

    def generate_pb_result_analysis(self) -> QuaResultAnalysis:
        return QuaResultAnalysis(model=[output.to_proto() for output in self._saves])


class _LeadingScope(_BaseScope, metaclass=abc.ABCMeta):
    """
    Represents the first scope in a multi-part control structure.

    Examples include 'if', 'switch', or 'for' statements —
    constructs that initiate a compound control flow block.
    """

    def __init__(self, loc: str) -> None:
        super().__init__()
        self._loc = loc

    def _on_clean_exit(self) -> None:
        """Pops the current scope (created in __enter__) and appends its statement to the previous scope"""
        statement = self._create_statement()
        _scopes_stack.pop()
        _scopes_stack[-1].append_statement(statement)

    @abc.abstractmethod
    def _create_statement(self) -> QuaProgramAnyStatement:
        pass


class _FollowingScope(_BaseScope, metaclass=abc.ABCMeta):
    """
    Represents a scope that follows and complements a LeadingScope.

    Examples include 'else', 'case' —
    constructs that depend on a prior control block to make sense.
    """

    def _on_clean_exit(self) -> None:
        self._add_to_leading_scope()
        return super()._on_clean_exit()

    @abstractmethod
    def _add_to_leading_scope(self) -> None:
        raise NotImplementedError
