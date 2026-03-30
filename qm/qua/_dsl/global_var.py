from qm._loc import _get_loc
from qm.grpc.qm.pb import inc_qua_pb2
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._expressions import QuaVariable, QuaGlobalVarXor, QuaGlobalVarRead


def global_var_xor(*bits: int) -> QuaGlobalVarXor:
    return QuaGlobalVarXor(bits)


def global_var_read(*bits: int, shift: bool = False) -> QuaGlobalVarRead:
    return QuaGlobalVarRead(bits, shift)


def assign_global_var(*variables: QuaVariable[bool]) -> None:
    statement = inc_qua_pb2.QuaProgram.AnyStatement(
        globalVariableAssignment=inc_qua_pb2.QuaProgram.GlobalVariableAssignmentStatement(
            loc=_get_loc(), variables=[v.unwrapped_scalar for v in variables]
        )
    )
    scopes_manager.append_statement(statement)
