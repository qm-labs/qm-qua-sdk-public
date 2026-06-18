from typing import Iterable
from typing import Optional
from typing import Iterable as IterableClass
from typing import Tuple, Union, Literal, Mapping

from qm._loc import _get_loc
from qm.type_hinting import NumberT
from qm.grpc.qm.pb import inc_qua_pb2
from qm.exceptions import QmQuaException
from qm.qua._dsl.variable_handling import declare
from qm.qua._dsl.measure.measure import MeasurePulseType
from qm.qua._dsl._utils import _standardize_timestamp_label
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._dsl.stream_processing.stream_processing import StreamType
from qm.qua._expressions import Scalar, QuaArrayVariable, to_scalar_pb_expression, create_qua_scalar_expression

PlayPulseType = Union[MeasurePulseType, inc_qua_pb2.QuaProgram.RampPulse]

ChirpUnits = Literal[
    "Hz/nsec",
    "GHz/sec",
    "mHz/nsec",
    "MHz/sec",
    "uHz/nsec",
    "KHz/sec",
    "nHz/nsec",
    "Hz/sec",
    "pHz/nsec",
    "mHz/sec",
]
ChirpType = Union[
    Tuple[Union[Iterable[int], QuaArrayVariable[int], Scalar[int]], ChirpUnits],
    Tuple[Iterable[int], Iterable[int], ChirpUnits],
]
"""A type for performing piecewise linear sweep of the element’s intermediate frequency in time.
A tuple, with the 1st element being a list of rates and the second should be a string with the unit type.
See the ChirpUnits type for the complete list of supported units.
"""


def play(
    pulse: PlayPulseType,
    element: str,
    duration: Optional[Scalar[int]] = None,
    condition: Optional[Scalar[bool]] = None,
    chirp: Optional[ChirpType] = None,
    truncate: Optional[Scalar[int]] = None,
    timestamp_stream: Optional[StreamType] = None,
    continue_chirp: bool = False,
    target: str = "",
) -> None:
    r"""Play a `pulse` based on an 'operation' defined in `element`.

    The pulse will be modified according to the properties of the element
    (see detailed explanation about pulse modifications below),
    and then played to the OPX output(s) defined to be connected
    to the input(s) of the element in the configuration.

    Args:
        pulse (str): The name of an `operation` to be performed, as
            defined in the element in the quantum machine configuration.
            Can also be a [ramp][qm.qua.ramp] function or be multiplied by an
            [ramp][qm.qua.ramp].
        element (str): The name of the element, as defined in the
            quantum machine configuration.
        duration (Union[int,QUA variable of type int]): The time to play
            this pulse in units of the clock cycle (4ns). If not
            provided, the default pulse duration will be used. It is
            possible to dynamically change the duration of both constant
            and arbitrary pulses. Arbitrary pulses can only be stretched,
            not compressed.
        chirp (ChirpType): Allows to perform piecewise linear sweep
            of the element’s intermediate frequency in time. Input
            should be a tuple, with the 1st element being a list of
            rates and the second should be a string with the units.
            The units can be either: ‘Hz/nsec’, ’mHz/nsec’, ’uHz/nsec’,
            ’pHz/nsec’ or ‘GHz/sec’, ’MHz/sec’, ’KHz/sec’, ’Hz/sec’, ’mHz/sec’.
        truncate (Union[int, QUA variable of type int]): Allows playing
            only part of the pulse, truncating the end. If provided,
            will play only up to the given time in units of the clock
            cycle (4ns).
        condition (A logical expression to evaluate.): Will play the operation only if the condition is true.
            The play command will take the same amount of time regardless of the condition (If false, would wait instead).
            Prior to QOP 2.2, only the analog part was conditioned, i.e., any digital pulses associated
            with the operation would always play.
        timestamp_stream (Union[str, ResultStreamSource]): (Supported from
            QOP 2.2) Adding a `timestamp_stream` argument will save the
            time at which the operation occurred to a stream. If the
            `timestamp_stream` is a string ``label``, then the timestamp
            handle can be retrieved with
            [`JobResults.get`][qm.StreamsManager.get] with the same
            ``label``.
        continue_chirp (bool): When performing a chirp, passing `True` will make the chirp continue until a new chirp command is given. Defaults to `False`. Not available in OPX1.0.
        target (str): Allows to select a specific input of the element to play the pulse on. Only allowed (and required) when the element is defined with `singleInputCollection`.

    Note:
        Arbitrary waveforms cannot be compressed and can only be expanded up to
        $2^{24}-1$ clock cycles (67ms). Unexpected output will occur if a duration
        outside the range is given.
        See [Dynamic pulse duration](../../Guides/features.md#dynamic-pulse-duration)
        in the documentation for further information.

    Note:
        When using chirp, it is possible to add a flag "continue_chirp=True" to the play command.
        When this flag is set, the internal oscillator will continue the chirp even after the play command had ended.
        See the `chirp documentation [chirp documentation](../../Guides/features.md#frequency-chirp)
        for more information.

    Example:
        ```python
        with program() as prog:
            v1 = declare(fixed)
            assign(v1, 0.3)
            play('pulse1', 'element1')
            play('pulse1' * amp(0.5), 'element1')
            play('pulse1' * amp(v1), 'element1')
            play('pulse1' * amp(0.9, v1, -v1, 0.9), 'element_iq_pair')
            time_stream = declare_output_stream()
            # Supported on QOP2.2+
            play('pulse1', 'element1', duration=16, timestamp_stream='t1')
            play('pulse1', 'element1', duration=16, timestamp_stream=time_stream)
            with stream_processing():
                stream.buffer(10).save_all('t2')
        ```
    """
    condition_ = to_scalar_pb_expression(condition) if condition is not None else None
    duration_ = to_scalar_pb_expression(duration) if duration is not None else None
    chirp_ = _standardize_chirp(chirp, continue_chirp)
    truncate_ = to_scalar_pb_expression(truncate) if truncate is not None else None
    timestamp_label = _standardize_timestamp_label(timestamp_stream)

    amp = None
    if isinstance(pulse, tuple):
        pulse, amp = pulse

    loc = _get_loc()
    play_statement = inc_qua_pb2.QuaProgram.PlayStatement(
        loc=loc,
        qe=inc_qua_pb2.QuaProgram.QuantumElementReference(name=element, loc=loc),
        targetInput=target,
    )
    if isinstance(pulse, inc_qua_pb2.QuaProgram.RampPulse):
        play_statement.rampPulse.CopyFrom(pulse)
    else:
        play_statement.namedPulse.CopyFrom(inc_qua_pb2.QuaProgram.PulseReference(name=pulse, loc=loc))

    if duration_ is not None:
        play_statement.duration.CopyFrom(duration_)
    if condition_ is not None:
        play_statement.condition.CopyFrom(condition_)
    if chirp_ is not None:
        play_statement.chirp.CopyFrom(chirp_)
        play_statement.chirp.loc = loc
    if amp is not None:
        play_statement.amp.CopyFrom(inc_qua_pb2.QuaProgram.AmpMultiplier(loc=loc, v0=amp[0]))
        for i in range(1, 4, 1):
            if amp[i] is not None:
                getattr(play_statement.amp, "v" + str(i)).CopyFrom(amp[i])
    if truncate_ is not None:
        play_statement.truncate.CopyFrom(truncate_)
    if timestamp_label is not None:
        play_statement.timestampLabel = timestamp_label
    _port_condition = scopes_manager.port_condition
    if _port_condition is not None:
        play_statement.port_condition.CopyFrom(_port_condition)

    scopes_manager.append_statement(inc_qua_pb2.QuaProgram.AnyStatement(play=play_statement))


def _standardize_chirp(chirp: Optional[ChirpType], continue_chirp: bool) -> Optional[inc_qua_pb2.QuaProgram.Chirp]:
    if chirp is None:
        return None

    if len(chirp) == 2:
        chirp_var, chirp_units = chirp
        chirp_times = None
    elif len(chirp) == 3:
        chirp_var, chirp_times, chirp_units = chirp
    else:
        raise QmQuaException("chirp must be tuple of 2 or 3 values")
    chirp_times_list = [int(x) for x in chirp_times] if chirp_times is not None else None
    if isinstance(chirp_var, IterableClass):
        chirp_var = [int(x) for x in chirp_var]
        chirp_var = declare(int, value=chirp_var)

    chirp_obj = inc_qua_pb2.QuaProgram.Chirp()
    chirp_obj.continueChirp = continue_chirp
    if chirp_times_list is not None:
        chirp_obj.times.extend(chirp_times_list)
    if isinstance(chirp_var, QuaArrayVariable):
        chirp_obj.arrayRate.CopyFrom(chirp_var.unwrapped)
    else:
        chirp_obj.scalarRate.CopyFrom(to_scalar_pb_expression(chirp_var))

    units_mapping: Mapping[ChirpUnits, int] = {
        "Hz/nsec": inc_qua_pb2.QuaProgram.Chirp.Units.HzPerNanoSec,
        "GHz/sec": inc_qua_pb2.QuaProgram.Chirp.Units.HzPerNanoSec,
        "mHz/nsec": inc_qua_pb2.QuaProgram.Chirp.Units.mHzPerNanoSec,
        "MHz/sec": inc_qua_pb2.QuaProgram.Chirp.Units.mHzPerNanoSec,
        "uHz/nsec": inc_qua_pb2.QuaProgram.Chirp.Units.uHzPerNanoSec,
        "KHz/sec": inc_qua_pb2.QuaProgram.Chirp.Units.uHzPerNanoSec,
        "nHz/nsec": inc_qua_pb2.QuaProgram.Chirp.Units.nHzPerNanoSec,
        "Hz/sec": inc_qua_pb2.QuaProgram.Chirp.Units.nHzPerNanoSec,
        "pHz/nsec": inc_qua_pb2.QuaProgram.Chirp.Units.pHzPerNanoSec,
        "mHz/sec": inc_qua_pb2.QuaProgram.Chirp.Units.pHzPerNanoSec,
    }

    if chirp_units in units_mapping:
        chirp_obj.units = units_mapping[chirp_units]  # type: ignore[assignment]
    else:
        raise QmQuaException(f'unknown units "{chirp_units}"')
    return chirp_obj


def ramp(v: Scalar[NumberT]) -> inc_qua_pb2.QuaProgram.RampPulse:
    """To be used only within a [`play`][qm.qua.play] command, instead of the `operation`.

    It’s possible to generate a voltage ramp by using the `ramp(slope)` command.
    The slope argument is specified in units of `V/ns`. Usage of this feature is as follows:

    ``play(ramp(0.0001), 'qe1', duration=1000)``

    note:
        The pulse duration must be specified if the ramp feature is used.

    Args:
        v: The slope in units of `V/ns`
    """
    value = create_qua_scalar_expression(v)
    result = inc_qua_pb2.QuaProgram.RampPulse(value=value.unwrapped)
    return result
