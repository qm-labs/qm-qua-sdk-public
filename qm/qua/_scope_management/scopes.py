from types import TracebackType
from dataclasses import dataclass
from typing import Any, List, Type, Tuple, Generic, Literal, Optional, Sequence

from betterproto.lib.google.protobuf import Any as BetterAny

from qm.type_hinting import NumberT
from qm.exceptions import QmQuaException
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._expressions import Scalar, QuaScalar, to_scalar_pb_expression
from qm.qua._scope_management._core_scopes import _LeadingScope, _FollowingScope
from qm.grpc.qua import (
    QuaProgramElseIf,
    QuaProgramIfStatement,
    QuaProgramAnyStatement,
    QuaProgramForStatement,
    QuaProgramForEachStatement,
    QuaProgramVarRefExpression,
    QuaProgramAnyScalarExpression,
    QuaProgramAssignmentStatement,
    QuaProgramStatementsCollection,
    QuaProgramArrayVarRefExpression,
    QuaProgramStrictTimingStatement,
    QuaProgramArbitraryContextStatement,
    QuaProgramForEachStatementVariableWithValues,
)


class _ForScope(_LeadingScope):
    def __init__(
        self,
        init: Optional[QuaProgramAssignmentStatement],
        condition: Optional[QuaProgramAnyScalarExpression],
        update: Optional[QuaProgramAssignmentStatement],
        loc: str,
    ):
        super().__init__(loc)
        self._init = init
        self._condition = condition
        self._update = update

    def _create_statement(self) -> QuaProgramAnyStatement:
        init = [QuaProgramAnyStatement(assign=self._init)] if self._init else []
        update = [QuaProgramAnyStatement(assign=self._update)] if self._update else []
        statement = QuaProgramForStatement(
            init=QuaProgramStatementsCollection(statements=init),
            update=QuaProgramStatementsCollection(statements=update),
            body=QuaProgramStatementsCollection(statements=self._statements),
        )
        if self._condition:
            statement.condition = self._condition
        return QuaProgramAnyStatement(for_=statement)


class _ForEachScope(_LeadingScope):
    def __init__(
        self,
        iterators: Sequence[Tuple[QuaProgramVarRefExpression, QuaProgramArrayVarRefExpression]],
        loc: str,
    ) -> None:
        super().__init__(loc)
        self._iterators = iterators

    def _create_statement(self) -> QuaProgramAnyStatement:
        statement = QuaProgramForEachStatement(
            iterator=[
                QuaProgramForEachStatementVariableWithValues(variable=var, array=arr) for var, arr in self._iterators
            ],
            body=QuaProgramStatementsCollection(statements=self._statements),
            loc=self._loc,
        )
        return QuaProgramAnyStatement(for_each=statement)


class _IfScope(_LeadingScope):
    def __init__(self, condition: Scalar[bool], unsafe: bool, loc: str):
        super().__init__(loc)
        self._condition = condition
        self._unsafe = unsafe

    def _create_statement(self) -> QuaProgramAnyStatement:
        statement = QuaProgramIfStatement(
            condition=to_scalar_pb_expression(self._condition),
            unsafe=self._unsafe,
            body=QuaProgramStatementsCollection(statements=self._statements),
            loc=self._loc,
        )
        return QuaProgramAnyStatement(if_=statement)


class _ElifScope(_FollowingScope):
    def __init__(self, condition: Scalar[bool], if_statement: QuaProgramIfStatement, loc: str):
        super().__init__()
        self._condition = condition
        self._if_statement = if_statement
        self._loc = loc

    def _add_to_leading_scope(self) -> None:
        self._if_statement.elseifs.append(self._create_elif_statement())

    def _create_elif_statement(self) -> QuaProgramElseIf:
        return QuaProgramElseIf(
            loc=self._loc,
            condition=to_scalar_pb_expression(self._condition),
            body=QuaProgramStatementsCollection(statements=self._statements),
        )


class _ElseScope(_FollowingScope):
    def __init__(self, if_statement: QuaProgramIfStatement):
        super().__init__()
        self._if_statement = if_statement

    def _add_to_leading_scope(self) -> None:
        self._if_statement.else_ = QuaProgramStatementsCollection(statements=self._statements)


class _StrictTimingScope(_LeadingScope):
    def _create_statement(self) -> QuaProgramAnyStatement:
        statement = QuaProgramStrictTimingStatement(
            body=QuaProgramStatementsCollection(statements=self._statements),
            loc=self._loc,
        )
        return QuaProgramAnyStatement(strict_timing=statement)


class _SwitchScope(_LeadingScope, Generic[NumberT]):
    """Switch scope does not hold statements"""

    def __init__(self, expression: QuaScalar[NumberT], unsafe: bool, loc: str):
        super().__init__(loc)
        self._expression: QuaScalar[NumberT] = expression
        self._unsafe = unsafe
        self.cases: List[_CaseData[NumberT]] = []
        self.default: List[QuaProgramAnyStatement] = []

    def _create_statement(self) -> QuaProgramAnyStatement:
        if not self.cases:
            raise QmQuaException(
                "Expecting scope with body. Expecting switch scope with body. "
                "This switch scope does not have any cases"
            )

        conditions = [(self._expression.__eq__(case.value)).unwrapped for case in self.cases]

        first_case = self.cases[0]
        first_condition = conditions[0]

        else_ifs = [
            QuaProgramElseIf(
                condition=cond,
                body=QuaProgramStatementsCollection(statements=case.statements),
                loc=self._loc,
            )
            for cond, case in zip(conditions[1:], self.cases[1:])
        ]
        statement = QuaProgramIfStatement(
            condition=first_condition,
            body=QuaProgramStatementsCollection(statements=first_case.statements),
            unsafe=self._unsafe,
            elseifs=else_ifs,
            else_=QuaProgramStatementsCollection(statements=self.default),
            loc=self._loc,
        )
        return QuaProgramAnyStatement(if_=statement)

    def append_statement(self, statement: QuaProgramAnyStatement) -> None:
        raise QmQuaException(
            "Switch scope can only contain 'case' and 'default' blocks. Direct statements are not allowed (Expecting scope with body.)."
        )


@dataclass
class _CaseData(Generic[NumberT]):
    value: QuaScalar[NumberT]
    statements: List[QuaProgramAnyStatement]


class _CaseScope(_FollowingScope, Generic[NumberT]):
    def __init__(self, switch_scope: "_SwitchScope[NumberT]", value: QuaScalar[NumberT]):
        super().__init__()
        self._switch_scope: "_SwitchScope[NumberT]" = switch_scope
        self._value: QuaScalar[NumberT] = value

    def _add_to_leading_scope(self) -> None:
        data = _CaseData(value=self._value, statements=self._statements)
        self._switch_scope.cases.append(data)


class _CaseDefaultScope(_FollowingScope):
    def __init__(self, switch_scope: "_SwitchScope[Any]"):
        super().__init__()
        self._switch_scope: "_SwitchScope[Any]" = switch_scope

    def _add_to_leading_scope(self) -> None:
        self._switch_scope.default = self._statements


class _PortConditionScope:
    """
    Not a "real" scope, since it doesn't inherit from _BaseScope and therefore is not added to the scopes stack.
    Unlike other scopes where the scopes_manager accesses them through the scopes stack, this scope updates the
    scope manager through dedicated 'set' functions.
    """

    def __init__(self, expression: QuaProgramAnyScalarExpression):
        self._expression = expression

    def __enter__(self) -> None:
        scopes_manager._set_port_condition(self._expression)

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]
    ) -> Literal[False]:
        scopes_manager._unset_port_condition()
        return False


class _ArbitraryScope(_LeadingScope):
    def __init__(
        self,
        loc: str,
        name: str,
        data: Optional[BetterAny],
    ):
        super().__init__(loc)
        self._name = name
        self._data = data

    def _create_statement(self) -> QuaProgramAnyStatement:
        statement = QuaProgramArbitraryContextStatement(
            loc=self._loc,
            name=self._name,
            data=self._data,
            body=QuaProgramStatementsCollection(statements=self._statements),
        )
        return QuaProgramAnyStatement(arbitrary_context=statement)
