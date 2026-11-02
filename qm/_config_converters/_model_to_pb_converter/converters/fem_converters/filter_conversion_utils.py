"""Shared analog-output IIR-filter conversion helpers.

These operate purely on the shared ``QuaConfig.AnalogOutputPortFilter`` proto and
the FEM-agnostic feedback-filter model types, so they are reused by every
OctoDac-style converter (LF-FEM and LF-LN08) without coupling those converters to
each other. Dependencies on converter state (the ``_set_pb_attr_config_v2``
writer, ``capabilities``, ``init_mode``) are passed in explicitly, so nothing
here reaches into a converter instance.
"""

from typing import Callable, Sequence

from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm.api.models.capabilities import QopCaps, ServerCapabilities
from qm.config._ports._analog_output import (
    AnalogOutputFeedbackFilter33,
    AnalogOutputFeedbackFilter35,
    AnalogOutputFeedbackExponential,
)

SetPbAttrConfigV2 = Callable[..., None]


def set_exponential_param(
    item: QuaConfig.AnalogOutputPortFilter,
    exponential: Sequence[tuple[float, float]],
    *,
    set_attr: SetPbAttrConfigV2,
) -> None:
    exponential_serialized = [
        QuaConfig.ExponentialParameters(amplitude=amp, time_constant=tau) for amp, tau in exponential
    ]
    set_attr(item.iir, exponential_serialized, "exponential", "exponential_v2")


def set_high_pass_param(
    item: QuaConfig.AnalogOutputPortFilter,
    data: float | None,
    *,
    set_attr: SetPbAttrConfigV2,
) -> None:
    if data is None:
        return

    set_attr(
        item.iir,
        data,
        "high_pass",
        "high_pass_v2",
        allow_nones=True,
        create_container=QuaConfig.IirFilter.HighPassContainer,
    )


def set_exponential_dc_gain_param(
    item: QuaConfig.AnalogOutputPortFilter,
    data: float | None,
    *,
    capabilities: ServerCapabilities,
    init_mode: bool,
) -> None:
    if (not init_mode) and capabilities.supports(QopCaps.config_v2) and data is None:
        return
    item.iir.exponential_dc_gain.CopyFrom(QuaConfig.IirFilter.ExponentialDcGainContainer(value=data))


def deconvert_feedback_filter(
    output_data: QuaConfig.AnalogOutputPortFilter,
    *,
    capabilities: ServerCapabilities,
) -> "AnalogOutputFeedbackExponential | Sequence[float]":
    if not capabilities.supports(QopCaps.exponential_iir_filter):
        return list(output_data.feedback)

    raw_exponential = (
        output_data.iir.exponential_v2.value
        if capabilities.supports(QopCaps.config_v2)
        else output_data.iir.exponential
    )
    exponential = [(exp_params.amplitude, exp_params.time_constant) for exp_params in raw_exponential]

    if capabilities.supports(QopCaps.config_v2):
        high_pass = output_data.iir.high_pass_v2.value if output_data.iir.HasField("high_pass_v2") else None
    else:
        high_pass = output_data.iir.high_pass if output_data.iir.HasField("high_pass") else None

    if capabilities.supports(QopCaps.exponential_dc_gain_filter):
        exponential_dc_gain = (
            output_data.iir.exponential_dc_gain.value
            if output_data.iir.HasField("exponential_dc_gain") and output_data.iir.exponential_dc_gain.HasField("value")
            else None
        )
        if exponential_dc_gain is None and high_pass is not None:
            return AnalogOutputFeedbackFilter33(exponential, high_pass)
        return AnalogOutputFeedbackFilter35(exponential, exponential_dc_gain)
    return AnalogOutputFeedbackFilter33(exponential, high_pass)
