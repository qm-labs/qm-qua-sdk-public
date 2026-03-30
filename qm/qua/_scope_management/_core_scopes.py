import abc
import threading
from collections import deque
from abc import abstractmethod
from types import TracebackType
from typing import TYPE_CHECKING, Set, Dict, List, Type, Deque, Tuple, Literal, Optional, cast

from qm.grpc.qm.pb import inc_qua_pb2
from qm.program.program import Program
from qm.exceptions import QmQuaException
from qm.api.models.capabilities import Capability

if TYPE_CHECKING:
    from qm.qua._dsl.streams.external_streams import QuaStreamDirection
    from qm.qua._dsl.stream_processing.stream_processing import ResultStreamSource, _OutputStream
    from qm.qua._dsl.stream_processing.direct_stream_processing_interface import DirectStreamSourceInterface

# The root level scopes stack. Intended for use exclusively by _get_scopes_stack().
# It is a thread-local stack - each thread gets its own stack, so it is safe for multi-threaded use.
_thread_local = threading.local()


def _get_scopes_stack() -> Deque["_BaseScope"]:
    """
    Get the scopes stack (thread-local), creates it if necessary.
    Intended for use exclusively by the base scope classes or the scopes manager.
    """
    if not hasattr(_thread_local, "scopes_stack"):
        _thread_local.scopes_stack = deque()
    return cast(Deque["_BaseScope"], _thread_local.scopes_stack)


class _BaseScope(abc.ABC):
    def __init__(self) -> None:
        self._statements: List[inc_qua_pb2.QuaProgram.AnyStatement] = []

    def __enter__(self) -> None:
        scopes_stack = _get_scopes_stack()
        if len(scopes_stack) == 0 and not isinstance(self, _ProgramScope):
            raise QmQuaException("First scope must be a program scope")

        scopes_stack.append(self)
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
        scopes_stack = _get_scopes_stack()
        scopes_stack.pop()

    @property
    def statements(self) -> List[inc_qua_pb2.QuaProgram.AnyStatement]:
        return self._statements

    def append_statement(self, statement: inc_qua_pb2.QuaProgram.AnyStatement) -> None:
        self._statements.append(statement)


class _ProgramScope(_BaseScope):
    def __init__(self) -> None:
        super().__init__()
        self._program = Program()

        self.var_index = 0
        self.array_index = 0
        self.struct_index = 0
        self.result_index = 0

        self._declared_variables: List[inc_qua_pb2.QuaProgram.VarDeclaration] = []
        self._declared_streams: Dict[str, "ResultStreamSource"] = {}
        self._auto_processing_streams: List["DirectStreamSourceInterface"] = []  # type: ignore[type-arg]
        self._declared_input_streams: Set[str] = set()
        self._declared_external_streams: Dict[
            Tuple[int, "QuaStreamDirection"], inc_qua_pb2.QuaProgram.ExternalStreamDeclaration
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
        self.auto_stream_processing()
        self._program._set_and_exit(self._generate_pb_qua_program(), self._used_capabilities)
        scopes_stack = _get_scopes_stack()
        scopes_stack.clear()
        return False

    @property
    def declared_streams(self) -> Dict[str, "ResultStreamSource"]:
        return self._declared_streams

    @property
    def declared_input_streams(self) -> Set[str]:
        return self._declared_input_streams

    @property
    def declared_external_streams(
        self,
    ) -> Dict[Tuple[int, "QuaStreamDirection"], inc_qua_pb2.QuaProgram.ExternalStreamDeclaration]:
        return self._declared_external_streams

    @property
    def result_analysis_scope(self) -> "_ResultAnalysisScope":
        return self._result_analysis_scope

    def add_var_declaration(self, declaration: inc_qua_pb2.QuaProgram.VarDeclaration) -> None:
        self._declared_variables.append(declaration)

    def add_stream_declaration(self, tag: str, stream: "ResultStreamSource") -> None:
        if tag in self._declared_streams:
            raise QmQuaException(f"Stream with tag {tag} already declared")
        self._declared_streams[tag] = stream

    def auto_stream_processing(self) -> None:
        """Process all auto-processing streams added to the program scope."""
        # to avoid calling similar stream processing multiple times in case of code duplication because of native loops
        current_processed_streams: set[str] = set()
        for stream in self._auto_processing_streams:
            stream.stream_processing(current_processed_streams)

    @property
    def auto_processing_streams(self) -> List["DirectStreamSourceInterface"]:  # type: ignore[type-arg]
        return self._auto_processing_streams

    def add_auto_processing_stream(self, stream: "DirectStreamSourceInterface") -> None:  # type: ignore[type-arg]
        self._auto_processing_streams.append(stream)

    def add_input_stream_declaration(self, var_name: str) -> None:
        self._declared_input_streams.add(var_name)

    def add_external_stream_declaration(
        self,
        stream_identifier: Tuple[int, "QuaStreamDirection"],
        stream_declaration: inc_qua_pb2.QuaProgram.ExternalStreamDeclaration,
    ) -> None:
        self._declared_external_streams[stream_identifier] = stream_declaration

    def add_used_capability(self, capability: Capability) -> None:
        self._used_capabilities.add(capability)

    def _generate_pb_qua_program(self) -> inc_qua_pb2.QuaProgram:
        return inc_qua_pb2.QuaProgram(
            script=inc_qua_pb2.QuaProgram.Script(
                variables=self._declared_variables,
                externalStreams=list(self._declared_external_streams.values()),
                body=inc_qua_pb2.QuaProgram.StatementsCollection(statements=self._statements),
            ),
            resultAnalysis=self._result_analysis_scope.generate_pb_result_analysis(),
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

    def generate_pb_result_analysis(self) -> inc_qua_pb2.QuaResultAnalysis:
        return inc_qua_pb2.QuaResultAnalysis(model=[output.to_proto() for output in self._saves])


class _LeadingScope(_BaseScope, abc.ABC):
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
        scopes_stack = _get_scopes_stack()
        scopes_stack.pop()
        scopes_stack[-1].append_statement(statement)

    @abc.abstractmethod
    def _create_statement(self) -> inc_qua_pb2.QuaProgram.AnyStatement:
        pass


class _FollowingScope(_BaseScope, abc.ABC):
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


class _LoopScope(_LeadingScope, abc.ABC):
    """Base class for loop scopes, providing common properties like name and size."""

    def __init__(self, loc: str) -> None:
        super().__init__(loc)
        self._name: Optional[str] = None
        self._size: Optional[int] = None
        self._averaged_streams: set[str] = set()

    @property
    def name(self) -> Optional[str]:
        return self._name

    @property
    def size(self) -> Optional[int]:
        return self._size

    def set_scope_metadata(self, name: str, size: int) -> None:
        self._name = name
        self._size = size

    def add_averaged_stream(self, stream_name: str) -> None:
        self._averaged_streams.add(stream_name)

    def averaged_streams(self) -> frozenset[str]:
        return frozenset(self._averaged_streams)


class _PythonNativeScope(_LoopScope):
    def __init__(self, loc: str) -> None:
        super().__init__(loc)
        self._current_value_idx: Optional[str] = None

    def _create_statement(self) -> inc_qua_pb2.QuaProgram.AnyStatement:
        raise QmQuaException("Native Python loops do not generate Qua statements")

    def _on_clean_exit(self) -> None:
        scopes_stack = _get_scopes_stack()
        scopes_stack.pop()
        for statement in self._statements:
            scopes_stack[-1].append_statement(statement)

    @property
    def current_value_name(self) -> str:
        if self._current_value_idx is None:
            raise QmQuaException("Current value name is not set for the native Python loop scope")
        return self._current_value_idx

    def set_current_iteration_number(self, idx: int) -> None:
        self._current_value_idx = str(idx)
