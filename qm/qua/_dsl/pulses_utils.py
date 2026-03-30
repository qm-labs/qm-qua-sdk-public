from typing import Optional

from google.protobuf.wrappers_pb2 import UInt32Value

from qm._loc import _get_loc
from qm.grpc.qm.pb import inc_qua_pb2
from qm.api.models.capabilities import QopCaps
from qm.qua._expressions import Scalar, to_scalar_pb_expression
from qm.qua._scope_management.scopes_manager import scopes_manager


def ramp_to_zero(element: str, duration: Optional[int] = None) -> None:
    r"""Starting from the last DC value, gradually lowers the DC to zero for `duration` *4nsec

    If `duration` is None, the duration is taken from the element's config

    Warning:
        This feature does not protect from voltage jumps. Those can still occur, i.e. when the data sent to the
        analog output is outside the range -0.5 to $0.5 - 2^{16}$ and thus will have an overflow.

    Args:
        element (str): element for ramp to zero
        duration (Union[int,None]): time , `in multiples of 4nsec`.
            Range: [4, $2^{24}$] in steps of 1, or `None` to take
            value from config
    """
    duration = duration if duration is None else int(duration)
    loc = _get_loc()
    duration_val = UInt32Value(value=duration) if duration else None
    statement = inc_qua_pb2.QuaProgram.RampToZeroStatement(
        loc=loc,
        qe=inc_qua_pb2.QuaProgram.QuantumElementReference(name=element, loc=loc),
        duration=duration_val,
    )
    scopes_manager.append_statement(inc_qua_pb2.QuaProgram.AnyStatement(rampToZero=statement))


def load_waveform(
    pulse: str,
    waveform_index: Scalar[int],
    element: str,
) -> None:
    """
    Load a waveform from the waveform array to be used in a pulse.

    Args:
        pulse (str): The name of an `operation` to be performed, as defined in the element in the quantum machine
            configuration.
        waveform_index (int, QUA int): The index of the waveform to be loaded from the waveform_array that was
            configured for the pulse.
        element (str): The name of the element, as defined in the quantum machine configuration.
    """
    loc = _get_loc()
    scopes_manager.program_scope.add_used_capability(QopCaps.waveform_array)
    statement = inc_qua_pb2.QuaProgram.AnyStatement(
        loadWaveform=inc_qua_pb2.QuaProgram.LoadWaveformStatement(
            loc=loc,
            pulse=inc_qua_pb2.QuaProgram.PulseReference(name=pulse, loc=loc),
            qe=inc_qua_pb2.QuaProgram.QuantumElementReference(name=element, loc=loc),
            waveform_index=to_scalar_pb_expression(waveform_index),
        )
    )
    scopes_manager.append_statement(statement)
