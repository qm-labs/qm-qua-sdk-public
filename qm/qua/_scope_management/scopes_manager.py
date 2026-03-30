from typing import TYPE_CHECKING, Optional, Sequence, cast

from qm.grpc.qm.pb import inc_qua_pb2
from qm.exceptions import QmQuaException, NoScopeFoundException
from qm.qua._scope_management._core_scopes import _BaseScope, _ProgramScope, _get_scopes_stack

if TYPE_CHECKING:
    from qm.qua._dsl.stream_processing.stream_processing import _OutputStream


class _ScopesStackManager:
    """
    Provides higher-level access to the scopes stack, used by DSL functions and, optionally, by the scope classes.
    We do not want the scopes stack to be exposed to the DSL functions, so we provide this manager.
    """

    def __init__(self) -> None:
        self._port_condition: Optional[inc_qua_pb2.QuaProgram.AnyScalarExpression] = None

    @property
    def program_scope(self) -> _ProgramScope:
        scopes_stack = _get_scopes_stack()
        if len(scopes_stack) == 0:
            raise NoScopeFoundException("No program scope found")
        return cast(_ProgramScope, scopes_stack[0])

    @property
    def current_scope(self) -> _BaseScope:
        scopes_stack = _get_scopes_stack()
        if len(scopes_stack) == 0:
            raise NoScopeFoundException("No scope found")
        return scopes_stack[-1]

    @property
    def scope_stack(self) -> Sequence[_BaseScope]:
        return tuple(_get_scopes_stack())

    def append_statement(self, statement: inc_qua_pb2.QuaProgram.AnyStatement) -> None:
        self.current_scope.append_statement(statement)

    def append_output_stream(self, stream: "_OutputStream") -> None:
        self.program_scope.result_analysis_scope.append_output_stream(stream)

    # The function is private since it should only be used by the PortConditionScope, and should not be used by the DSL functions.
    def _set_port_condition(self, condition: inc_qua_pb2.QuaProgram.AnyScalarExpression) -> None:
        scopes_stack = _get_scopes_stack()
        if len(scopes_stack) == 0:
            raise NoScopeFoundException("No program scope found")
        if self._port_condition is not None:
            raise QmQuaException("port_condition already set")
        self._port_condition = condition

    # The function is private since it should only be used by the PortConditionScope, and should not be used by the DSL functions.
    def _unset_port_condition(self) -> None:
        self._port_condition = None

    @property
    def port_condition(self) -> Optional[inc_qua_pb2.QuaProgram.AnyScalarExpression]:
        return self._port_condition


scopes_manager = _ScopesStackManager()
