from typing import TYPE_CHECKING, Optional, cast

from qm.exceptions import QmQuaException, NoScopeFoundException
from qm.grpc.qua import QuaProgramAnyStatement, QuaProgramAnyScalarExpression
from qm.qua._scope_management._core_scopes import _BaseScope, _ProgramScope, _scopes_stack

if TYPE_CHECKING:
    from qm.qua._dsl.stream_processing.stream_processing import _OutputStream


class _ScopesStackManager:
    """
    Provides higher-level access to the scopes stack, used by DSL functions and, optionally, by the scope classes.
    We do not want the scopes stack to be exposed to the DSL functions, so we provide this manager.
    """

    def __init__(self) -> None:
        self._port_condition: Optional[QuaProgramAnyScalarExpression] = None

    @property
    def program_scope(self) -> _ProgramScope:
        if len(_scopes_stack) == 0:
            raise NoScopeFoundException("No program scope found")
        return cast(_ProgramScope, _scopes_stack[0])

    @property
    def current_scope(self) -> _BaseScope:
        if len(_scopes_stack) == 0:
            raise NoScopeFoundException("No scope found")
        return _scopes_stack[-1]

    def append_statement(self, statement: QuaProgramAnyStatement) -> None:
        self.current_scope.append_statement(statement)

    def append_output_stream(self, stream: "_OutputStream") -> None:
        self.program_scope.result_analysis_scope.append_output_stream(stream)

    # The function is private since it should only be used by the PortConditionScope, and should not be used by the DSL functions.
    def _set_port_condition(self, condition: QuaProgramAnyScalarExpression) -> None:
        if len(_scopes_stack) == 0:
            raise NoScopeFoundException("No program scope found")
        if self._port_condition is not None:
            raise QmQuaException("port_condition already set")
        self._port_condition = condition

    # The function is private since it should only be used by the PortConditionScope, and should not be used by the DSL functions.
    def _unset_port_condition(self) -> None:
        self._port_condition = None

    @property
    def port_condition(self) -> Optional[QuaProgramAnyScalarExpression]:
        return self._port_condition


scopes_manager = _ScopesStackManager()
