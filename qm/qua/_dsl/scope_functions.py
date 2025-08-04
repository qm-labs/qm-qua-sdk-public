from typing import List, Tuple, Union
from typing import Iterable as IterableClass
from typing import Optional, Collection, cast

import betterproto

from qm._loc import _get_loc
from qm.type_hinting import NumberT
from qm.exceptions import QmQuaException
from qm.qua._dsl._type_hints import OneOrMore
from qm.qua._dsl.variable_handling import declare
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.grpc.qua import QuaProgramIfStatement, QuaProgramAssignmentStatement
from qm.qua._scope_management._core_scopes import _ProgramScope, _ResultAnalysisScope
from qm.utils import collection_has_type_int, collection_has_type_bool, collection_has_type_float
from qm.qua._expressions import (
    Scalar,
    Vector,
    QuaScalar,
    QuaVariable,
    QuaArrayVariable,
    QuaNumericExpression,
    fixed,
    literal_bool,
    to_scalar_pb_expression,
    create_qua_scalar_expression,
)
from qm.qua._scope_management.scopes import (
    _IfScope,
    _ForScope,
    _CaseScope,
    _ElifScope,
    _ElseScope,
    _SwitchScope,
    _ForEachScope,
    _CaseDefaultScope,
    _StrictTimingScope,
    _PortConditionScope,
)


def program() -> _ProgramScope:
    """Create a QUA program.

    Used within a context manager, the program is defined in the code block
    below ``with`` statement.

    Statements in the code block below are played as soon as possible, meaning that an instruction
    will be played immediately unless it is dependent on a previous instruction.
    Additionally, commands output to the same elements will be played sequentially,
    and to different elements will be played in parallel.
    An exception is that pulses will be implicitly aligned at the end of each [`for_`][qm.qua.for_] loop iteration.

    The generated ``program_name`` object is used as an input to the execution or compilation functions.

    Example:
        ```python
        with program() as program_name:
            play('pulse1', 'element1')
            wait('element1')

        qmm = QuantumMachinesManager(...)
        qm = qmm.open_qm(...)
        qm.execute(program_name)
        ```
    """
    return _ProgramScope()


def switch_(expression: QuaScalar[NumberT], unsafe: bool = False) -> _SwitchScope[NumberT]:
    """Part of the switch-case flow control statement in QUA.

    To be used with a context manager.

    The code block inside should be composed of only ``case_()`` and ``default_()``
    statements, and there should be at least one of them.

    The expression given in the ``switch_()`` statement will be evaluated and compared
    to each of the values in the ``case_()`` statements. The QUA code block following
    the ``case_()`` statement which evaluated to true will be executed. If none of the
    statements evaluated to true, the QUA code block following the ``default_()``
    statement (if given) will be executed.

    Args:
        expression: An expression to evaluate
        unsafe: If set to True, then switch-case would be more efficient
            and would produce fewer gaps. However, if an input which does
            not match a case is given, unexpected behavior will occur.
            Cannot be used with the ``default_()`` statement. Default is
            false, use with care.

    Example:
        ```python
        x=declare(int)
        with switch_(x):
            with case_(1):
                play('first_pulse', 'element')
            with case_(2):
                play('second_pulse', 'element')
            with case_(3):
                play('third_pulse', 'element')
            with default_():
                play('other_pulse', 'element')
        ```
    """
    return _SwitchScope(expression, unsafe, loc=_get_loc())


def case_(case_exp: Scalar[NumberT]) -> _CaseScope[NumberT]:
    """Part of the switch-case flow control statement in QUA.

    To be used with a context manager.

    Must be inside a ``switch_()`` statement.

    The expression given in the ``switch_()`` statement will be evaluated and compared
    to each of the values in the ``case_()`` statements. The QUA code block following
    the ``case_()`` statement which evaluated to true will be executed. If none of the
    statements evaluated to true, the QUA code block following the ``default_()``
    statement (if given) will be executed.

    Args:
        case_exp: A value (or expression) to compare to the expression
            in the ``switch_()`` statement

    Example:
        ```python
        x=declare(int)
        with switch_(x):
            with case_(1):
                play('first_pulse', 'element')
            with case_(2):
                play('second_pulse', 'element')
            with case_(3):
                play('third_pulse', 'element')
            with default_():
                play('other_pulse', 'element')
        ```
    """
    switch = scopes_manager.current_scope
    if not isinstance(switch, _SwitchScope):
        raise QmQuaException("Expecting switch scope. 'case_' can be used only under switch scope.")

    if switch.default:
        raise QmQuaException("All 'case' statements must precede the 'default' statement.")

    return _CaseScope(switch, create_qua_scalar_expression(case_exp))


def default_() -> _CaseDefaultScope:
    """Part of the switch-case flow control statement in QUA.

    To be used with a context manager.

    Must be inside a ``switch_()`` statement, and there can only be one ``default_()``
    statement.

    The expression given in the ``switch_()`` statement will be evaluated and compared
    to each of the values in the ``case_()`` statements. The QUA code block following
    the ``case_()`` statement which evaluated to true will be executed. If none of the
    statements evaluated to true, the QUA code block following the ``default_()``
    statement (if given) will be executed.

    Example:
        ```python
        x=declare(int)
        with switch_(x):
            with case_(1):
                play('first_pulse', 'element')
            with case_(2):
                play('second_pulse', 'element')
            with case_(3):
                play('third_pulse', 'element')
            with default_():
                play('other_pulse', 'element')
        ```
    """
    switch = scopes_manager.current_scope
    if not isinstance(switch, _SwitchScope):
        raise QmQuaException("Expecting switch scope. 'default_' can be used only under switch scope.")

    if not switch.cases:
        raise QmQuaException("must specify at least one case before 'default'.")

    if switch.default:
        raise QmQuaException("only a single 'default' statement can follow a 'switch' statement")

    return _CaseDefaultScope(switch)


def if_(expression: Scalar[bool], unsafe: bool = False) -> _IfScope:
    """If flow control statement in QUA.

    To be used with a context manager.

    The QUA code block following the statement will be
    executed only if the expression given evaluates to true.

    Args:
        expression: A boolean expression to evaluate

    Example:
        ```python
        x=declare(int)
        with if_(x>0):
            play('pulse', 'element')
        ```
    """
    return _IfScope(expression, unsafe, loc=_get_loc())


def elif_(expression: Scalar[bool]) -> _ElifScope:
    """Else-If flow control statement in QUA.

    To be used with a context manager.

    Must appear after an ``if_()`` statement.

    The QUA code block following the statement will be executed only if the expressions
    in the preceding ``if_()`` and ``elif_()`` statements evaluates to false and if the
    expression given in this ``elif_()`` evaluates to true.

    Args:
        expression: A boolean expression to evaluate

    Example:
        ```python
        x=declare(int)
        with if_(x>2):
            play('pulse', 'element')
        with elif_(x>-2):
            play('other_pulse', 'element')
        with else_():
            play('third_pulse', 'element')
        ```
    """
    scope = scopes_manager.current_scope
    if not scope.statements:
        raise QmQuaException(
            "'elif' statement must directly follow 'if' statement - Please make sure it is aligned with the corresponding if statement."
        )
    _, if_statement = betterproto.which_one_of(scope.statements[-1], "statement_oneof")
    if not isinstance(if_statement, QuaProgramIfStatement):
        raise QmQuaException(
            "'elif' statement must directly follow 'if' statement - Please make sure it is aligned with the corresponding if statement."
        )

    if betterproto.serialized_on_wire(if_statement.else_):
        raise QmQuaException("'elif' must come before 'else' statement")

    return _ElifScope(condition=expression, if_statement=if_statement, loc=if_statement.loc)


def else_() -> _ElseScope:
    """Else flow control statement in QUA.

    To be used with a context manager.

    Must appear after an ``if_()`` statement.

    The QUA code block following the statement will be executed only if the expressions
    in the preceding ``if_()`` and ``elif_()`` statements evaluates to false.

    Example:
        ```python
        x=declare(int)
        with if_(x>0):
            play('pulse', 'element')
        with else_():
            play('other_pulse', 'element')
        ```
    """
    scope = scopes_manager.current_scope
    if not scope.statements:
        raise QmQuaException(
            "'else' statement must directly follow 'if' statement - "
            "Please make sure it is aligned with the corresponding if statement."
        )
    _, if_statement = betterproto.which_one_of(scope.statements[-1], "statement_oneof")
    if not isinstance(if_statement, QuaProgramIfStatement):
        raise QmQuaException(
            "'else' statement must directly follow 'if' statement - "
            "Please make sure it is aligned with the corresponding if statement."
        )

    if betterproto.serialized_on_wire(if_statement.else_):
        raise QmQuaException("only a single 'else' statement can follow an 'if' statement")

    return _ElseScope(if_statement)


def while_(cond: Optional[QuaScalar[bool]] = None) -> _ForScope:
    """While loop flow control statement in QUA.

    To be used with a context manager.

    Args:
        cond (QUA expression): an expression which evaluates to a
            boolean variable, determines if to continue to next loop
            iteration

    Example:
        ```python
        x = declare(int)
        assign(x, 0)
        with while_(x<=30):
            play('pulse', 'element')
            assign(x, x+1)
        ```
    """
    return for_(None, None, cond, None)


def for_(
    var: Optional[QuaVariable[NumberT]] = None,
    init: Optional[Scalar[NumberT]] = None,
    cond: Optional[QuaScalar[bool]] = None,
    update: Optional[QuaScalar[NumberT]] = None,
) -> _ForScope:
    """For loop flow control statement in QUA.

    To be used with a context manager.

    Args:
        var (QUA variable): QUA variable used as iteration variable
        init (QUA expression): an expression which sets the initial
            value of the iteration variable
        cond (QUA expression): an expression which evaluates to a
            boolean variable, determines if to continue to next loop
            iteration
        update (QUA expression): an expression to add to ``var`` with
            each loop iteration

    Example:
        ```python
        x = declare(fixed)
        with for_(var=x, init=0, cond=x<=1, update=x+0.1):
            play('pulse', 'element')
        ```
    """
    init_statement = None
    cond_expression = None
    update_statement = None

    if var is not None and init is not None:
        init_statement = QuaProgramAssignmentStatement(
            target=var.assignment_statement,
            expression=to_scalar_pb_expression(init),
            loc=_get_loc(),
        )
    if var is not None and update is not None:
        update_statement = QuaProgramAssignmentStatement(
            target=var.assignment_statement, expression=to_scalar_pb_expression(update), loc=_get_loc()
        )
    if cond is not None:
        cond_expression = to_scalar_pb_expression(cond)
    return _ForScope(init_statement, cond_expression, update_statement, loc=_get_loc())


def for_each_(var: OneOrMore[QuaVariable[NumberT]], values: OneOrMore[Vector[NumberT]]) -> _ForEachScope:
    """Flow control: Iterate over array elements in QUA.

    It is possible to either loop over one variable, or over a tuple of variables,
    similar to the `zip` style iteration in python.

    To be used with a context manager.

    Args:
        var (Union[QUA variable, tuple of QUA variables]): The iteration
            variable
        values (Union[list of literals, tuple of lists of literals, QUA array, tuple of QUA arrays]):
            A list of values to iterate over or a QUA array.

    Example:
        ```python
        x=declare(fixed)
        y=declare(fixed)
        with for_each_(x, [0.1, 0.4, 0.6]):
            play('pulse' * amp(x), 'element')
        with for_each_((x, y), ([0.1, 0.4, 0.6], [0.3, -0.2, 0.1])):
            play('pulse1' * amp(x), 'element')
            play('pulse2' * amp(y), 'element')
        ```

    Warning:

        This behavior is not exactly consistent with python `zip`.
        Instead of sending a list of tuple as values, the function expects a tuple of
        lists.
        The first list containing the values for the first variable, and so on.
    """
    if not isinstance(var, IterableClass):
        var = (var,)

    for i, v in enumerate(var):
        if not isinstance(v, QuaVariable):
            raise QmQuaException(f"for_each_ var {i} must be a variable")

    qua_expression_cond = isinstance(values, QuaNumericExpression)
    not_iterable_cond = not isinstance(values, (IterableClass, QuaArrayVariable))
    tuple_of_non_iterables_cond = not isinstance(values[0], (IterableClass, QuaArrayVariable))
    if qua_expression_cond or not_iterable_cond or tuple_of_non_iterables_cond:
        values = (cast(QuaArrayVariable[NumberT], values),)
    values = cast(Tuple[QuaArrayVariable[NumberT], ...], values)

    if isinstance(values, Collection) and len(values) < 1:
        raise QmQuaException("values cannot be empty")

    if len(var) != len(values):
        raise QmQuaException("number of variables does not match number of array values")

    arrays: List[Union[QuaArrayVariable[bool], QuaArrayVariable[int], QuaArrayVariable[float]]] = []
    for value in values:
        if isinstance(value, QuaArrayVariable):
            arrays.append(value)
        elif isinstance(value, Collection):
            has_bool = collection_has_type_bool(value)
            has_int = collection_has_type_int(value)
            has_float = collection_has_type_float(value)

            if has_bool:
                if has_int or has_float:
                    raise QmQuaException("values can not contain both bool and number values")
                # Only booleans
                arrays.append(declare(bool, value=[bool(x) for x in value]))
            else:
                if has_float:
                    # All will be considered as fixed
                    arrays.append(declare(fixed, value=[float(x) for x in value]))
                else:
                    # Only ints
                    arrays.append(declare(int, value=[int(x) for x in value]))
        else:
            raise QmQuaException("value is not a QUA array neither iterable")

    unwrapped_vars = [v.unwrapped.variable for v in var]
    unwrapped_arrays = [a.unwrapped for a in arrays]

    iterators = [(unwrapped_vars[i], ar) for i, ar in enumerate(unwrapped_arrays)]

    return _ForEachScope(iterators, loc=_get_loc())


def infinite_loop_() -> _ForScope:
    """Infinite loop flow control statement in QUA.

    To be used with a context manager.

    Optimized for zero latency between iterations,
    provided that no more than a single element appears in the loop.

    Note:
        In case multiple elements need to be used in an infinite loop, it is possible to add several loops
        in parallel (see example).
        Two infinite loops cannot share an element nor can they share variables.

    Example:
        ```python
        with infinite_loop_():
            play('pulse1', 'element1')
        with infinite_loop_():
            play('pulse2', 'element2')
        ```
    """
    return _ForScope(None, literal_bool(True), None, loc=_get_loc())


def port_condition(condition: Scalar[bool]) -> _PortConditionScope:
    """
    A context manager for a faster conditional play mechanism. Will operate on all the elements inside the context manager.
    Note that elements sharing a port with an element inside the context manager cannot be played in parallel to the context manager.

    -- Available for MW-FEM Only --

    Args:
        condition (A logical expression to evaluate): Will play the operation only if the condition is true.
            The play command will take the same amount of time regardless of the condition (If false, would wait instead).

    Example:
        ```python
        with port_condition(x > 0):
            play('pulse', 'element')
        ```
    """
    return _PortConditionScope(expression=to_scalar_pb_expression(condition))


def stream_processing() -> _ResultAnalysisScope:
    """A context manager for the creation of [Stream processing pipelines](../../Guides/stream_proc.md#overview)

    Each pipeline defines an analysis process that is applied to every stream item.
    A pipeline must be terminated with a save/save_all terminal, and then can be retrieved with
    [QmJob.result_handles][qm.jobs.running_qm_job.RunningQmJob.result_handles].

    There are two save options: ``save_all`` will save every stream item, ``save`` will save only last item.

    A pipeline can be assigned to python variable, and then reused on other pipelines. It is ensured that the
    common part of the pipeline is processed only once.

    ??? example "Creating a result analysis object"
        ```python
        with stream_processing():
            a.save("tag")
            a.save_all("another tag")
        ```

    ??? example "Retrieving saved result"
        ```python
        QmJob.result_handles.get("tag")
        ```
    """
    scope = scopes_manager.program_scope
    return scope.result_analysis_scope


def strict_timing_() -> _StrictTimingScope:
    """Any QUA command written within the strict timing block will be required to play without gaps.

    See [the documentation](../../Guides/timing_in_qua.md#strict-timing) for further information and examples.

    To be used with a context manager.

    -- Available from QOP 2.0 --
    """
    return _StrictTimingScope(loc=_get_loc())
