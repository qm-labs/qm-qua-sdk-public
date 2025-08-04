import uuid
import numbers
import warnings
from copy import copy
from typing import Any, Dict, List, Type, Tuple, Union, Mapping, TypeVar, Optional, Collection, cast

import betterproto
from betterproto.lib.google.protobuf import Empty
from dependency_injector.wiring import Provide, inject

from qm.utils import deprecation_message
from qm.utils.list_compression_utils import split_list_to_chunks
from qm.containers.capabilities_container import CapabilitiesContainer
from qm.api.models.capabilities import OPX_FEM_IDX, QopCaps, ServerCapabilities
from qm.utils.config_utils import get_logical_pb_config, get_fem_config_instance, get_controller_pb_config
from qm.program._validate_config_schema import (
    validate_oscillator,
    validate_output_tof,
    validate_used_inputs,
    validate_output_smearing,
    validate_sticky_duration,
    validate_arbitrary_waveform,
)
from qm.exceptions import (
    InvalidOctaveParameter,
    NoInputsOrOutputsError,
    ConfigValidationException,
    OctaveConnectionAmbiguity,
    OctaveUnsupportedOnUpdate,
    ConfigurationLockedByOctave,
    CapabilitiesNotInitializedError,
    ElementInputConnectionAmbiguity,
    ElementOutputConnectionAmbiguity,
)
from qm.type_hinting.config_types import (
    LoopbackType,
    StandardPort,
    FullQuaConfig,
    LfFemConfigType,
    MixerConfigType,
    MwFemConfigType,
    PulseConfigType,
    LogicalQuaConfig,
    OctaveConfigType,
    ElementConfigType,
    PortReferenceType,
    ControllerQuaConfig,
    ControllerConfigType,
    OscillatorConfigType,
    DigitalInputConfigType,
    MwUpconverterConfigType,
    OctaveRFInputConfigType,
    WaveformArrayConfigType,
    OctaveRFOutputConfigType,
    AnalogInputPortConfigType,
    DigitalWaveformConfigType,
    OctaveIfOutputsConfigType,
    AnalogOutputPortConfigType,
    ConstantWaveformConfigType,
    DigitalInputPortConfigType,
    ArbitraryWaveformConfigType,
    DigitalOutputPortConfigType,
    IntegrationWeightConfigType,
    OPX1000ControllerConfigType,
    AnalogOutputFilterConfigType,
    MwFemAnalogInputPortConfigType,
    OctaveSingleIfOutputConfigType,
    MwFemAnalogOutputPortConfigType,
    TimeTaggingParametersConfigType,
    AnalogOutputFilterConfigTypeQop33,
    AnalogOutputFilterConfigTypeQop35,
    AnalogOutputPortConfigTypeOctoDac,
)
from qm.grpc.qua_config import (
    QuaConfig,
    QuaConfigMatrix,
    QuaConfigSticky,
    QuaConfigFemTypes,
    QuaConfigMixerDec,
    QuaConfigMixerRef,
    QuaConfigPulseDec,
    QuaConfigDeviceDec,
    QuaConfigMixInputs,
    QuaConfigElementDec,
    QuaConfigHoldOffset,
    QuaConfigOscillator,
    QuaConfigQuaConfigV1,
    QuaConfigQuaConfigV2,
    QuaConfigSingleInput,
    QuaConfigWaveformDec,
    QuaConfigOctaveConfig,
    QuaConfigOctaveIfMode,
    QuaConfigVoltageLevel,
    QuaConfigControllerDec,
    QuaConfigElementThread,
    QuaConfigLogicalConfig,
    QuaConfigOctoDacFemDec,
    QuaConfigPortReference,
    QuaConfigMultipleInputs,
    QuaConfigOctaveLoopback,
    QuaConfigCorrectionEntry,
    QuaConfigMicrowaveFemDec,
    QuaConfigMultipleOutputs,
    QuaConfigWaveformSamples,
    QuaConfigAdcPortReference,
    QuaConfigControllerConfig,
    QuaConfigDacPortReference,
    QuaConfigWaveformArrayDec,
    QuaConfigPulseDecOperation,
    QuaConfigAnalogInputPortDec,
    QuaConfigDigitalWaveformDec,
    QuaConfigAnalogOutputPortDec,
    QuaConfigConstantWaveformDec,
    QuaConfigDigitalInputPortDec,
    QuaConfigOctaveLoopbackInput,
    QuaConfigOctaveLoSourceInput,
    QuaConfigOctaveRfInputConfig,
    QuaConfigArbitraryWaveformDec,
    QuaConfigDigitalOutputPortDec,
    QuaConfigGeneralPortReference,
    QuaConfigIntegrationWeightDec,
    QuaConfigOctaveRfOutputConfig,
    QuaConfigUpConverterConfigDec,
    QuaConfigDigitalWaveformSample,
    QuaConfigExponentialParameters,
    QuaConfigOctaveIfOutputsConfig,
    QuaConfigOctaveSynthesizerPort,
    QuaConfigOutputPulseParameters,
    QuaConfigSingleInputCollection,
    QuaConfigAnalogOutputPortFilter,
    QuaConfigIntegrationWeightSample,
    QuaConfigOctaveOutputSwitchState,
    QuaConfigDigitalInputPortReference,
    QuaConfigDigitalOutputPortReference,
    QuaConfigIirFilterHighPassContainer,
    QuaConfigOctaveSingleIfOutputConfig,
    QuaConfigOctoDacAnalogOutputPortDec,
    QuaConfigDigitalInputPortDecPolarity,
    QuaConfigMicrowaveAnalogInputPortDec,
    QuaConfigMicrowaveInputPortReference,
    QuaConfigOctaveDownconverterRfSource,
    QuaConfigOctaveSynthesizerOutputName,
    QuaConfigMicrowaveAnalogOutputPortDec,
    QuaConfigMicrowaveOutputPortReference,
    QuaConfigOutputPulseParametersPolarity,
    QuaConfigIirFilterExponentialDcGainContainer,
    QuaConfigOctoDacAnalogOutputPortDecOutputMode,
    QuaConfigOctoDacAnalogOutputPortDecSamplingRate,
    QuaConfigOctoDacAnalogOutputPortDecSamplingRateMode,
)

ALLOWED_GAINES = {x / 2 for x in range(-40, 41)}
DEFAULT_DUC_IDX = 1

# No option to bound to TypedDict
T = TypeVar("T", bound=Mapping[str, Any])


@inject
def _apply_defaults(
    config: T,
    default_schema: T,
    init_mode: bool,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> T:
    """
    Merge default values into the configuration dictionary, if applicable.

    If `init_mode` is True, missing keys from `config` will be filled in using `default_schema`.
    If `init_mode` is False and the server supports `config_v2`, the original `config` is returned unchanged (in
    config_v1 defaults will always be applied).

    Args:
        config (T): A user-defined config, possibly missing some keys.
        default_schema (T): Schema with default values for keys (possibly missing some keys).
        init_mode (bool): Whether to apply defaults (`True`) or skip (`False`).

    Returns:
        A new config dictionary with defaults applied, or the original config.
    """

    if not init_mode and capabilities.supports(QopCaps.config_v2):
        return config

    # The casting is that mypy will allow the update method
    new_config = cast(Dict[Any, Any], copy(default_schema))
    new_config.update(config)
    return cast(T, new_config)


def _validate_required_fields(config: Mapping[str, Any], fields: List[str], parent_field: str) -> None:
    for field in fields:
        if field not in config:
            raise ConfigValidationException(f"{field} should be declared when initializing a {parent_field}")


@inject
def _set_pb_attr_config_v2(
    item: betterproto.Message,
    value: Any,
    v1_attr: str,
    v2_attr: str,
    allow_nones: bool = False,
    create_container: Optional[Type[betterproto.Message]] = None,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> None:
    if not hasattr(item, v1_attr) or not hasattr(item, v2_attr):
        raise AttributeError(f"Either {v1_attr} or {v2_attr} do not exist in {item}")

    if value is None and not allow_nones:
        return

    if capabilities.supports(QopCaps.config_v2):
        container_message = getattr(item, v2_attr)

        if container_message is None and create_container:
            container_message = create_container()
            setattr(item, v2_attr, container_message)

        if not hasattr(container_message, "value"):
            raise AttributeError(f"{v2_attr} does not have a 'value' attribute")

        container_message.value = value
    else:
        setattr(item, v1_attr, value)


def analog_input_port_to_pb(data: AnalogInputPortConfigType, init_mode: bool) -> QuaConfigAnalogInputPortDec:
    default_schema: AnalogInputPortConfigType = {"offset": 0.0, "shareable": False, "gain_db": 0, "sampling_rate": 1e9}
    data_with_defaults = _apply_defaults(
        data,
        default_schema=default_schema,
        init_mode=init_mode,
    )
    analog_input = QuaConfigAnalogInputPortDec(
        offset=data_with_defaults.get("offset"),
        shareable=data_with_defaults.get("shareable"),
        gain_db=data_with_defaults.get("gain_db"),
        sampling_rate=data_with_defaults.get("sampling_rate"),
    )
    return analog_input


def mw_fem_analog_input_port_to_pb(
    data: MwFemAnalogInputPortConfigType, init_mode: bool
) -> QuaConfigMicrowaveAnalogInputPortDec:
    if init_mode:
        _validate_required_fields(data, ["band", "downconverter_frequency"], "microwave analog input port")

    default_schema: MwFemAnalogInputPortConfigType = {"sampling_rate": 1e9, "gain_db": 0, "shareable": False}
    data_with_defaults = _apply_defaults(data, default_schema, init_mode=init_mode)

    analog_input = QuaConfigMicrowaveAnalogInputPortDec(
        sampling_rate=data_with_defaults.get("sampling_rate"),
        gain_db=data_with_defaults.get("gain_db"),
        shareable=data_with_defaults.get("shareable"),
        band=data_with_defaults.get("band"),
    )
    if "downconverter_frequency" in data_with_defaults:
        analog_input.downconverter.frequency = data_with_defaults["downconverter_frequency"]

    return analog_input


def _get_port_reference_with_fem(reference: PortReferenceType) -> StandardPort:
    if len(reference) == 2:
        return reference[0], OPX_FEM_IDX, reference[1]
    else:
        return reference


def _validate_unsupported_params(
    data: Collection[str],
    unsupported_params: Collection[str],
    supported_params: Collection[str],
    supported_from: Optional[str] = None,
    supported_until: Optional[str] = None,
) -> None:
    if set(data) & set(unsupported_params):
        if supported_from:
            unsupported_message = f"supported only from QOP {supported_from} and later"
        elif supported_until:
            unsupported_message = f"supported only until QOP {supported_until}"
        else:
            raise ValueError("Either 'supported_from' or 'supported_until' must be provided.")

        raise ConfigValidationException(
            f"The configuration keys {unsupported_params} are {unsupported_message}. "
            f"Use the keys {supported_params} instead."
        )


def _validate_high_pass_param_in_qop35(data: AnalogOutputFilterConfigTypeQop35) -> None:
    if data.get("high_pass") is not None and data.get("exponential_dc_gain") is None:
        value = cast(AnalogOutputFilterConfigTypeQop33, data)["high_pass"]
        warnings.warn(
            f"Setting the `high_pass` to {value} is equivalent to setting the `exponential_dc_gain` field to {value}/0.5e9 and adding an exponential filter of (1-{value}/0.5e9, {value}).",
        )


def _set_exponential_param(
    item: QuaConfigAnalogOutputPortFilter,
    data_with_defaults: Union[AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigTypeQop35],
) -> None:
    if "exponential" in data_with_defaults:
        exponential = [
            QuaConfigExponentialParameters(amplitude=exp_params[0], time_constant=exp_params[1])
            for exp_params in data_with_defaults["exponential"]
        ]
        _set_pb_attr_config_v2(item.iir, exponential, "exponential", "exponential_v2")


def _set_high_pass_param(
    item: QuaConfigAnalogOutputPortFilter,
    data_with_defaults: AnalogOutputFilterConfigTypeQop33,
) -> None:
    if "high_pass" in data_with_defaults:
        _set_pb_attr_config_v2(
            item.iir,
            data_with_defaults["high_pass"],
            "high_pass",
            "high_pass_v2",
            allow_nones=True,
            create_container=QuaConfigIirFilterHighPassContainer,
        )


def _set_exponential_dc_gain_param(
    item: QuaConfigAnalogOutputPortFilter,
    data_with_defaults: AnalogOutputFilterConfigTypeQop35,
) -> None:
    if "exponential_dc_gain" in data_with_defaults:
        item.iir.exponential_dc_gain = QuaConfigIirFilterExponentialDcGainContainer(
            data_with_defaults["exponential_dc_gain"]
        )


@inject
def _analog_output_port_filters_qop33_to_pb(
    data: Union[AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigTypeQop35],
    init_mode: bool,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> QuaConfigAnalogOutputPortFilter:
    default_schema: AnalogOutputFilterConfigTypeQop33 = {"feedforward": [], "exponential": [], "high_pass": None}
    data_with_defaults = _apply_defaults(
        cast(AnalogOutputFilterConfigTypeQop33, data), default_schema=default_schema, init_mode=init_mode
    )

    item = QuaConfigAnalogOutputPortFilter()

    _set_pb_attr_config_v2(item, data_with_defaults.get("feedforward"), "feedforward", "feedforward_v2")
    _set_exponential_param(item, data_with_defaults)
    _set_high_pass_param(item, data_with_defaults)

    if capabilities.supports(QopCaps.exponential_dc_gain_filter):
        data_with_defaults_35 = _apply_defaults(
            cast(AnalogOutputFilterConfigTypeQop35, data_with_defaults),
            default_schema={"exponential_dc_gain": None},
            init_mode=init_mode,
        )
        data_with_defaults_35 = cast(  # For mypy, we already did cast in the previous line
            AnalogOutputFilterConfigTypeQop35, data_with_defaults_35
        )
        _validate_high_pass_param_in_qop35(data_with_defaults_35)
        _set_exponential_dc_gain_param(item, data_with_defaults_35)
    else:
        _validate_unsupported_params(
            data_with_defaults,
            unsupported_params=["exponential_dc_gain"],
            supported_params=["high_pass"],
            supported_from=QopCaps.exponential_dc_gain_filter.from_qop_version,
        )

    return item


@inject
def _analog_output_port_filters_to_pb(
    data: Union[AnalogOutputFilterConfigType, AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigTypeQop35],
    init_mode: bool,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> QuaConfigAnalogOutputPortFilter:

    if capabilities.supports(QopCaps.exponential_iir_filter):
        _validate_unsupported_params(
            data,
            unsupported_params=["feedback"],
            supported_params=["high_pass", "exponential"],
            supported_until=QopCaps.exponential_iir_filter.from_qop_version,
        )
        return _analog_output_port_filters_qop33_to_pb(cast(AnalogOutputFilterConfigTypeQop33, data), init_mode)
    else:
        _validate_unsupported_params(
            data,
            unsupported_params=["exponential", "high_pass"],
            supported_params=["feedback"],
            supported_from=QopCaps.exponential_iir_filter.from_qop_version,
        )

        data = cast(AnalogOutputFilterConfigType, data)
        return QuaConfigAnalogOutputPortFilter(
            feedforward=data.get("feedforward", []), feedback=data.get("feedback", [])
        )


AnalogOutputType = TypeVar("AnalogOutputType", QuaConfigAnalogOutputPortDec, QuaConfigOctoDacAnalogOutputPortDec)


@inject
def analog_output_port_to_pb(
    data: AnalogOutputPortConfigType,
    output_type: Type[AnalogOutputType],
    init_mode: bool,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> AnalogOutputType:
    default_schema: AnalogOutputPortConfigType = {"shareable": False, "offset": 0.0, "delay": 0}
    data_with_defaults = _apply_defaults(data, default_schema, init_mode=init_mode)

    analog_output = output_type(shareable=data_with_defaults.get("shareable"), offset=data_with_defaults.get("offset"))

    delay = data_with_defaults.get("delay")
    if delay is not None and delay < 0:
        raise ConfigValidationException(f"analog output delay cannot be a negative value, given value: {delay}")
    analog_output.delay = delay

    if "filter" in data_with_defaults:
        analog_output.filter = _analog_output_port_filters_to_pb(data_with_defaults["filter"], init_mode)

    if "crosstalk" in data_with_defaults:
        if capabilities.supports(QopCaps.config_v2) and isinstance(analog_output, QuaConfigOctoDacAnalogOutputPortDec):
            crosstalk_in_pb = analog_output.crosstalk_v2.value
        else:
            crosstalk_in_pb = analog_output.crosstalk

        for k, v in data_with_defaults["crosstalk"].items():
            crosstalk_in_pb[int(k)] = v

    return analog_output


def _validate_invalid_sampling_rate_and_upsampling_mode(
    data: AnalogOutputPortConfigTypeOctoDac, init_mode: bool
) -> None:
    # We check that a user explicitly tried to put upsampling mode (not the default value) with a non-compatible sampling rate
    if "upsampling_mode" in data and "sampling_rate" in data and data["sampling_rate"] != 1e9:
        raise ConfigValidationException("'upsampling_mode' is only relevant for 'sampling_rate' of 1GHz.")

    # A sampling rate of 1GHZ goes hand in hand with an upsampling mode, so when updating one of these values,
    # it has to be compatible with the other.
    if not init_mode:
        if "sampling_rate" in data and data["sampling_rate"] == 1e9 and "upsampling_mode" not in data:
            raise ConfigValidationException(
                "'upsampling_mode' should be provided when updating 'sampling_rate' to 1GHZ."
            )

        if "upsampling_mode" in data and "sampling_rate" not in data:
            raise ConfigValidationException(
                "'sampling_rate' of 1GHZ should be provided when updating 'upsampling_mode'."
            )


def update_sampling_rate_enum(
    item: QuaConfigOctoDacAnalogOutputPortDec, data_with_defaults: AnalogOutputPortConfigTypeOctoDac
) -> None:
    """Also update the upsampling mode, as its value is tightly correlated to the sampling rate."""
    sampling_rate = data_with_defaults.get("sampling_rate")
    if sampling_rate is not None:
        if sampling_rate == 1e9:
            item.sampling_rate = QuaConfigOctoDacAnalogOutputPortDecSamplingRate.GSPS1  # type: ignore[assignment]
            item.upsampling_mode = QuaConfigOctoDacAnalogOutputPortDecSamplingRateMode[
                data_with_defaults["upsampling_mode"]
            ]

        elif sampling_rate == 2e9:
            item.sampling_rate = QuaConfigOctoDacAnalogOutputPortDecSamplingRate.GSPS2  # type: ignore[assignment]
            item.upsampling_mode = QuaConfigOctoDacAnalogOutputPortDecSamplingRateMode.unset  # type: ignore[assignment]

        else:
            raise ValueError("Sampling rate should be either 1e9 or 2e9")


def opx_1000_analog_output_port_to_pb(
    data: AnalogOutputPortConfigTypeOctoDac,
    init_mode: bool,
) -> QuaConfigOctoDacAnalogOutputPortDec:
    item = analog_output_port_to_pb(data, output_type=QuaConfigOctoDacAnalogOutputPortDec, init_mode=init_mode)
    _validate_invalid_sampling_rate_and_upsampling_mode(data, init_mode)

    default_schema: AnalogOutputPortConfigTypeOctoDac = {
        "sampling_rate": 1e9,
        "upsampling_mode": "mw",
        "output_mode": "direct",
    }
    data_with_defaults = _apply_defaults(data, default_schema, init_mode=init_mode)

    update_sampling_rate_enum(item, data_with_defaults)

    if "output_mode" in data_with_defaults:
        item.output_mode = QuaConfigOctoDacAnalogOutputPortDecOutputMode[data_with_defaults.get("output_mode")]

    return item


def upconverter_config_dec_to_pb(
    data: Union[MwUpconverterConfigType, QuaConfigUpConverterConfigDec]
) -> QuaConfigUpConverterConfigDec:
    if isinstance(data, QuaConfigUpConverterConfigDec):
        return data
    return QuaConfigUpConverterConfigDec(frequency=data["frequency"])


def get_upconverters(
    data: MwFemAnalogOutputPortConfigType, data_with_defaults: MwFemAnalogOutputPortConfigType, init_mode: bool
) -> Union[None, Dict[int, QuaConfigUpConverterConfigDec]]:
    upconverters = cast(Dict[int, QuaConfigUpConverterConfigDec], data_with_defaults.get("upconverters"))
    if "upconverter_frequency" in data and "upconverters" in data:
        raise ConfigValidationException("Use either 'upconverter_frequency' or 'upconverters' but not both")
    if "upconverter_frequency" in data:
        upconverters = {DEFAULT_DUC_IDX: QuaConfigUpConverterConfigDec(data["upconverter_frequency"])}
    else:
        if upconverters is not None:
            upconverters = {k: upconverter_config_dec_to_pb(v) for k, v in upconverters.items()}
        elif upconverters is None and init_mode:
            raise ConfigValidationException("You should declare at least one upconverter.")

    return cast(Union[None, Dict[int, QuaConfigUpConverterConfigDec]], upconverters)


def mw_fem_analog_output_to_pb(
    data: MwFemAnalogOutputPortConfigType,
    init_mode: bool,
) -> QuaConfigMicrowaveAnalogOutputPortDec:
    if init_mode:
        _validate_required_fields(data, ["band"], "microwave analog output port")

    default_schema: MwFemAnalogOutputPortConfigType = {
        "sampling_rate": 1e9,
        "full_scale_power_dbm": -11,
        "delay": 0,
        "shareable": False,
        "upconverters": {},
    }
    data_with_defaults = _apply_defaults(data, default_schema, init_mode=init_mode)

    item = QuaConfigMicrowaveAnalogOutputPortDec(
        sampling_rate=data_with_defaults.get("sampling_rate"),
        full_scale_power_dbm=data_with_defaults.get("full_scale_power_dbm"),
        band=data_with_defaults.get("band"),
        delay=data_with_defaults.get("delay"),
        shareable=data_with_defaults.get("shareable"),
    )

    upconverters = get_upconverters(data, data_with_defaults, init_mode)
    _set_pb_attr_config_v2(item, upconverters, "upconverters", "upconverters_v2")

    return item


def digital_output_port_to_pb(data: DigitalOutputPortConfigType, init_mode: bool) -> QuaConfigDigitalOutputPortDec:
    default_schema: DigitalOutputPortConfigType = {"shareable": False, "inverted": False}
    data_with_defaults = _apply_defaults(data, default_schema, init_mode=init_mode)

    digital_output = QuaConfigDigitalOutputPortDec(
        shareable=data_with_defaults.get("shareable"),
        inverted=data_with_defaults.get("inverted"),
        # The only currently supported level is LVTTL, so we set it always
        level=QuaConfigVoltageLevel.LVTTL,  # type: ignore[arg-type]
    )

    return digital_output


def digital_input_port_to_pb(data: DigitalInputPortConfigType, init_mode: bool) -> QuaConfigDigitalInputPortDec:
    if init_mode:
        _validate_required_fields(data, ["threshold", "polarity", "deadtime"], "digital input port")

    default_schema: DigitalInputPortConfigType = {"shareable": False}
    data_with_defaults = _apply_defaults(data, default_schema=default_schema, init_mode=init_mode)

    digital_input = QuaConfigDigitalInputPortDec(
        shareable=data_with_defaults.get("shareable"),
        threshold=data_with_defaults.get("threshold"),
        level=QuaConfigVoltageLevel.LVTTL,  # type: ignore[arg-type]
        # The user is not supposed to edit this anymore, it should always be LVTTL. Up until now the gateway just always
        # put LVTTL here, but we are moving it here because the SDK is in charge of supplying defaults.
    )

    if "polarity" in data_with_defaults:
        if data_with_defaults["polarity"].upper() == "RISING":
            digital_input.polarity = QuaConfigDigitalInputPortDecPolarity.RISING  # type: ignore[assignment]
        elif data_with_defaults["polarity"].upper() == "FALLING":
            digital_input.polarity = QuaConfigDigitalInputPortDecPolarity.FALLING  # type: ignore[assignment]
        else:
            raise ConfigValidationException(f"Invalid polarity: {data_with_defaults['polarity']}")

    if "deadtime" in data_with_defaults:
        digital_input.deadtime = data_with_defaults["deadtime"]

    return digital_input


def controlling_devices_to_pb(
    data: Union[ControllerConfigType, OPX1000ControllerConfigType], init_mode: bool
) -> QuaConfigDeviceDec:
    fems: Dict[int, QuaConfigFemTypes] = {}

    if "fems" in data:
        data = cast(OPX1000ControllerConfigType, data)
        # Here we assume that we don't declare OPX as FEM
        if set(data) & {"analog", "analog_outputs", "digital_outputs", "digital_inputs"}:
            raise Exception(
                "'analog', 'analog_outputs', 'digital_outputs' and 'digital_inputs' are not allowed when 'fems' is present"
            )
        for k, v in data["fems"].items():
            if v.get("type") == "MW":
                fems[int(k)] = _mw_fem_to_pb(cast(MwFemConfigType, v), init_mode)
            else:
                fems[int(k)] = _fem_to_pb(cast(LfFemConfigType, v), init_mode)

    else:
        data = cast(ControllerConfigType, data)
        fems[OPX_FEM_IDX] = _controller_to_pb(data, init_mode)

    item = QuaConfigDeviceDec(fems=fems)
    return item


def _controller_to_pb(data: ControllerConfigType, init_mode: bool) -> QuaConfigFemTypes:
    cont = QuaConfigControllerDec(type=data.get("type", "opx1"))
    cont = _set_ports_in_config(cont, data, init_mode)
    return QuaConfigFemTypes(opx=cont)


def _fem_to_pb(data: LfFemConfigType, init_mode: bool) -> QuaConfigFemTypes:
    cont = QuaConfigOctoDacFemDec()
    cont = _set_ports_in_config(cont, data, init_mode)
    return QuaConfigFemTypes(octo_dac=cont)


def _mw_fem_to_pb(data: MwFemConfigType, init_mode: bool) -> QuaConfigFemTypes:
    cont = QuaConfigMicrowaveFemDec()
    cont = _set_ports_in_config(cont, data, init_mode)
    return QuaConfigFemTypes(microwave=cont)


ControllerConfigTypeVar = TypeVar(
    "ControllerConfigTypeVar", QuaConfigOctoDacFemDec, QuaConfigControllerDec, QuaConfigMicrowaveFemDec
)


def _set_ports_in_config(
    config: ControllerConfigTypeVar,
    data: Union[ControllerConfigType, LfFemConfigType, MwFemConfigType],
    init_mode: bool,
) -> ControllerConfigTypeVar:
    if "analog_outputs" in data:
        for analog_output_idx, analog_output_data in data["analog_outputs"].items():
            int_k = int(analog_output_idx)
            if isinstance(config, QuaConfigControllerDec):
                analog_output_data = cast(AnalogOutputPortConfigType, analog_output_data)
                config.analog_outputs[int_k] = analog_output_port_to_pb(
                    analog_output_data,
                    output_type=QuaConfigAnalogOutputPortDec,
                    init_mode=init_mode,
                )
            elif isinstance(config, QuaConfigOctoDacFemDec):
                analog_output_data = cast(AnalogOutputPortConfigTypeOctoDac, analog_output_data)
                config.analog_outputs[int_k] = opx_1000_analog_output_port_to_pb(analog_output_data, init_mode)
            elif isinstance(config, QuaConfigMicrowaveFemDec):
                analog_output_data = cast(MwFemAnalogOutputPortConfigType, analog_output_data)
                config.analog_outputs[int_k] = mw_fem_analog_output_to_pb(analog_output_data, init_mode)
            else:
                raise ValueError(f"Unknown config type {type(config)}")

    if "analog_inputs" in data:
        if isinstance(config, (QuaConfigControllerDec, QuaConfigOctoDacFemDec)):
            for analog_input_idx, analog_input_data in data["analog_inputs"].items():
                analog_input_data = cast(AnalogInputPortConfigType, analog_input_data)
                config.analog_inputs[int(analog_input_idx)] = analog_input_port_to_pb(analog_input_data, init_mode)
                if isinstance(config, QuaConfigControllerDec):
                    sampling_rate = config.analog_inputs[int(analog_input_idx)].sampling_rate
                    if sampling_rate != 1e9:
                        raise ConfigValidationException(f"Sampling rate of {sampling_rate} is not supported for OPX")
        elif isinstance(config, QuaConfigMicrowaveFemDec):
            for analog_input_idx, analog_input_data_mw in data["analog_inputs"].items():
                analog_input_data_mw = cast(MwFemAnalogInputPortConfigType, analog_input_data_mw)
                config.analog_inputs[int(analog_input_idx)] = mw_fem_analog_input_port_to_pb(
                    analog_input_data_mw, init_mode
                )
        else:
            raise ValueError(f"Unknown config type {type(config)}")

    if "digital_outputs" in data:
        for digital_output_idx, digital_output_data in data["digital_outputs"].items():
            config.digital_outputs[int(digital_output_idx)] = digital_output_port_to_pb(digital_output_data, init_mode)

    if "digital_inputs" in data:
        for digital_input_idx, digital_input_data in data["digital_inputs"].items():
            config.digital_inputs[int(digital_input_idx)] = digital_input_port_to_pb(digital_input_data, init_mode)

    return config


def get_octave_loopbacks(data: List[LoopbackType]) -> List[QuaConfigOctaveLoopback]:
    loopbacks = [
        QuaConfigOctaveLoopback(
            lo_source_input=QuaConfigOctaveLoopbackInput[loopback[1]],
            lo_source_generator=QuaConfigOctaveSynthesizerPort(
                device_name=loopback[0][0],
                port_name=QuaConfigOctaveSynthesizerOutputName[loopback[0][1].lower()],
            ),
        )
        for loopback in data
    ]
    return loopbacks


def octave_to_pb(data: OctaveConfigType) -> QuaConfigOctaveConfig:
    connectivity = data.get("connectivity", None)
    if isinstance(connectivity, str):
        connectivity = (connectivity, OPX_FEM_IDX)
    loopbacks = get_octave_loopbacks(data.get("loopbacks", []))
    rf_modules = {
        k: rf_module_to_pb(standardize_connectivity_for_if_in(v, connectivity, k))
        for k, v in data.get("RF_outputs", {}).items()
    }
    rf_inputs = {k: rf_input_to_pb(v, k) for k, v in data.get("RF_inputs", {}).items()}
    if_outputs = _octave_if_outputs_to_pb(standardize_connectivity_for_if_out(data.get("IF_outputs", {}), connectivity))
    return QuaConfigOctaveConfig(
        loopbacks=loopbacks,
        rf_outputs=rf_modules,
        rf_inputs=rf_inputs,
        if_outputs=if_outputs,
    )


def standardize_connectivity_for_if_in(
    data: OctaveRFOutputConfigType, controller_connectivity: Optional[Tuple[str, int]], module_number: int
) -> OctaveRFOutputConfigType:
    if controller_connectivity is not None:
        if ("I_connection" in data) or ("Q_connection" in data):
            raise OctaveConnectionAmbiguity()

        data["I_connection"] = controller_connectivity + (2 * module_number - 1,)
        data["Q_connection"] = controller_connectivity + (2 * module_number,)
    return data


IF_OUT1_DEFAULT = "out1"
IF_OUT2_DEFAULT = "out2"


def standardize_connectivity_for_if_out(
    data: OctaveIfOutputsConfigType, controller_connectivity: Optional[Tuple[str, int]]
) -> OctaveIfOutputsConfigType:
    if controller_connectivity is not None:
        if "IF_out1" not in data:
            data["IF_out1"] = {"name": IF_OUT1_DEFAULT}
        if "IF_out2" not in data:
            data["IF_out2"] = {"name": IF_OUT2_DEFAULT}
        if ("port" in data["IF_out1"]) or ("port" in data["IF_out2"]):
            raise OctaveConnectionAmbiguity()
        data["IF_out1"]["port"] = controller_connectivity + (1,)
        data["IF_out2"]["port"] = controller_connectivity + (2,)
    return data


def _get_lo_frequency(data: Union[OctaveRFOutputConfigType, OctaveRFInputConfigType]) -> float:
    if "LO_frequency" not in data:
        raise ConfigValidationException("No LO frequency was set for upconverter")
    lo_freq = data["LO_frequency"]
    if not 2e9 <= lo_freq <= 18e9:
        raise ConfigValidationException(f"LO frequency {lo_freq} is out of range")
    return lo_freq


def rf_module_to_pb(data: OctaveRFOutputConfigType) -> QuaConfigOctaveRfOutputConfig:
    input_attenuators = data.get("input_attenuators", "OFF").upper()
    if input_attenuators not in {"ON", "OFF"}:
        raise ConfigValidationException("input_attenuators must be either ON or OFF")
    if "gain" not in data:
        raise ConfigValidationException("No gain was set for upconverter")
    gain = float(data["gain"])
    if gain not in ALLOWED_GAINES:
        raise ConfigValidationException(f"Gain should be an integer or half-integer between -20 and 20, got {gain})")
    to_return = QuaConfigOctaveRfOutputConfig(
        lo_frequency=_get_lo_frequency(data),
        lo_source=QuaConfigOctaveLoSourceInput[data.get("LO_source", "internal").lower()],
        output_mode=QuaConfigOctaveOutputSwitchState[data.get("output_mode", "always_off").lower()],
        gain=gain,
        input_attenuators=input_attenuators == "ON",
    )
    if "I_connection" in data:
        to_return.i_connection = dac_port_ref_to_pb(*_get_port_reference_with_fem(data["I_connection"]))
    if "Q_connection" in data:
        to_return.q_connection = dac_port_ref_to_pb(*_get_port_reference_with_fem(data["Q_connection"]))
    return to_return


def rf_input_to_pb(data: OctaveRFInputConfigType, input_idx: int = 0) -> QuaConfigOctaveRfInputConfig:
    input_idx_to_default_lo_source = {0: "not_set", 1: "internal", 2: "external"}  # 0 here is just for the default
    rf_source = QuaConfigOctaveDownconverterRfSource[data.get("RF_source", "RF_in").lower()]  # type: ignore[valid-type]
    if input_idx == 1 and rf_source != QuaConfigOctaveDownconverterRfSource.rf_in:
        raise InvalidOctaveParameter("Downconverter 1 must be connected to RF-in")

    lo_source = QuaConfigOctaveLoSourceInput[data.get("LO_source", input_idx_to_default_lo_source[input_idx]).lower()]  # type: ignore[valid-type]
    if input_idx == 2 and lo_source == QuaConfigOctaveLoSourceInput.internal:
        raise InvalidOctaveParameter("Downconverter 2 does not have internal LO")

    to_return = QuaConfigOctaveRfInputConfig(
        rf_source=rf_source,
        lo_frequency=_get_lo_frequency(data),
        lo_source=lo_source,
        if_mode_i=QuaConfigOctaveIfMode[data.get("IF_mode_I", "direct").lower()],
        if_mode_q=QuaConfigOctaveIfMode[data.get("IF_mode_Q", "direct").lower()],
    )
    return to_return


def single_if_output_to_pb(data: OctaveSingleIfOutputConfigType) -> QuaConfigOctaveSingleIfOutputConfig:
    controller, fem, number = _get_port_reference_with_fem(data["port"])
    return QuaConfigOctaveSingleIfOutputConfig(
        port=QuaConfigAdcPortReference(controller=controller, fem=fem, number=number), name=data["name"]
    )


def _octave_if_outputs_to_pb(data: OctaveIfOutputsConfigType) -> QuaConfigOctaveIfOutputsConfig:
    inst = QuaConfigOctaveIfOutputsConfig()
    if "IF_out1" in data:
        inst.if_out1 = single_if_output_to_pb(data["IF_out1"])
    if "IF_out2" in data:
        inst.if_out2 = single_if_output_to_pb(data["IF_out2"])
    return inst


@inject
def mixer_ref_to_pb(
    name: str,
    lo_frequency: int,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> QuaConfigMixerRef:
    item = QuaConfigMixerRef(mixer=name, lo_frequency=int(lo_frequency))
    if capabilities.supports_double_frequency:
        item.lo_frequency_double = float(lo_frequency)
    return item


@inject
def oscillator_to_pb(
    data: OscillatorConfigType, capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities]
) -> QuaConfigOscillator:
    oscillator = QuaConfigOscillator()
    if "intermediate_frequency" in data:
        oscillator.intermediate_frequency = int(data["intermediate_frequency"])
        if capabilities.supports_double_frequency:
            oscillator.intermediate_frequency_double = float(data["intermediate_frequency"])

    if "mixer" in data:
        oscillator.mixer = QuaConfigMixerRef(mixer=data["mixer"])
        oscillator.mixer.lo_frequency = int(data.get("lo_frequency", 0))
        if capabilities.supports_double_frequency:
            oscillator.mixer.lo_frequency_double = float(data.get("lo_frequency", 0.0))

    return oscillator


@inject
def create_correction_entry(
    mixer_data: MixerConfigType,
    init_mode: bool,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> QuaConfigCorrectionEntry:
    # Correction entries are stored in a list (refer to the function call). Unlike other values in the controller config,
    # lists do not support the 'upsert' operation. When a list is updated, it fully replaces the one set during init mode.
    # Therefore, the fields of QuaConfigCorrectionEntry can not be optional, as 'upsert' is not supported, only full replacement.

    default_schema: MixerConfigType = {"intermediate_frequency": 0, "lo_frequency": 0}
    data_with_defaults = _apply_defaults(mixer_data, default_schema=default_schema, init_mode=init_mode)

    # In "correction entry", all fields must be explicitly provided by the user in update mode. In init mode,
    # the correction field is mandatory, while the frequency parameters are assigned default values if not specified.
    # Therefore, after applying default values, all three fields should always be set.
    _validate_required_fields(
        data_with_defaults, ["intermediate_frequency", "lo_frequency", "correction"], "mixer correction entry"
    )

    correction = QuaConfigCorrectionEntry()

    correction.correction = QuaConfigMatrix(
        v00=data_with_defaults["correction"][0],
        v01=data_with_defaults["correction"][1],
        v10=data_with_defaults["correction"][2],
        v11=data_with_defaults["correction"][3],
    )

    correction.frequency_negative = data_with_defaults["intermediate_frequency"] < 0
    correction.frequency = abs(int(data_with_defaults["intermediate_frequency"]))
    if capabilities.supports_double_frequency:
        correction.frequency_double = abs(float(data_with_defaults["intermediate_frequency"]))

    correction.lo_frequency = int(data_with_defaults["lo_frequency"])
    if capabilities.supports_double_frequency:
        correction.lo_frequency_double = float(data_with_defaults["lo_frequency"])

    return correction


def mixer_to_pb(data: List[MixerConfigType], init_mode: bool) -> QuaConfigMixerDec:
    return QuaConfigMixerDec(correction=[create_correction_entry(mixer, init_mode) for mixer in data])


def element_thread_to_pb(name: str) -> QuaConfigElementThread:
    return QuaConfigElementThread(thread_name=name)


def dac_port_ref_to_pb(controller: str, fem: int, number: int) -> QuaConfigDacPortReference:
    return QuaConfigDacPortReference(controller=controller, fem=fem, number=number)


def single_input_to_pb(controller: str, fem: int, number: int) -> QuaConfigSingleInput:
    return QuaConfigSingleInput(port=dac_port_ref_to_pb(controller, fem, number))


def adc_port_ref_to_pb(controller: str, fem: int, number: int) -> QuaConfigAdcPortReference:
    return QuaConfigAdcPortReference(controller=controller, fem=fem, number=number)


def port_ref_to_pb(controller: str, fem: int, number: int) -> QuaConfigPortReference:
    return QuaConfigPortReference(controller=controller, fem=fem, number=number)


def digital_input_port_ref_to_pb(data: DigitalInputConfigType) -> QuaConfigDigitalInputPortReference:
    digital_input = QuaConfigDigitalInputPortReference(
        delay=int(data["delay"]),
        buffer=int(data["buffer"]),
    )
    if "port" in data:
        digital_input.port = port_ref_to_pb(*_get_port_reference_with_fem(data["port"]))

    return digital_input


def digital_output_port_ref_to_pb(data: PortReferenceType) -> QuaConfigDigitalOutputPortReference:
    return QuaConfigDigitalOutputPortReference(port=port_ref_to_pb(*_get_port_reference_with_fem(data)))


def create_time_tagging_parameters(data: TimeTaggingParametersConfigType) -> QuaConfigOutputPulseParameters:
    return QuaConfigOutputPulseParameters(
        signal_threshold=data["signalThreshold"],
        signal_polarity=_create_signal_polarity(data["signalPolarity"]),
        derivative_threshold=data["derivativeThreshold"],
        derivative_polarity=_create_signal_polarity(data["derivativePolarity"]),
    )


def _create_signal_polarity(polarity: str) -> QuaConfigOutputPulseParametersPolarity:
    polarity = polarity.upper()
    if polarity in {"ABOVE", "ASCENDING"}:
        if polarity == "ASCENDING":
            warnings.warn(deprecation_message("ASCENDING", "1.2.2", "1.3.0", "Use 'ABOVE' instead"), DeprecationWarning)
        return QuaConfigOutputPulseParametersPolarity.ASCENDING  # type: ignore[return-value]
    elif polarity in {"BELOW", "DESCENDING"}:
        if polarity == "DESCENDING":
            warnings.warn(
                deprecation_message("DESCENDING", "1.2.2", "1.3.0", "Use 'BELOW' instead"), DeprecationWarning
            )
        return QuaConfigOutputPulseParametersPolarity.DESCENDING  # type: ignore[return-value]
    else:
        raise ConfigValidationException(f"Invalid signal polarity: {polarity}")


@inject
def element_to_pb(
    element_name: str,
    data: ElementConfigType,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> QuaConfigElementDec:
    validate_oscillator(data)
    validate_output_smearing(data)
    validate_output_tof(data)
    validate_used_inputs(data)

    element = QuaConfigElementDec()

    if "time_of_flight" in data:
        element.time_of_flight = int(data["time_of_flight"])

    if "smearing" in data:
        element.smearing = int(data["smearing"])

    if "intermediate_frequency" in data:
        element.intermediate_frequency = abs(int(data["intermediate_frequency"]))
        element.intermediate_frequency_oscillator = int(data["intermediate_frequency"])
        if capabilities.supports_double_frequency:
            element.intermediate_frequency_double = abs(float(data["intermediate_frequency"]))
            element.intermediate_frequency_oscillator_double = float(data["intermediate_frequency"])

        element.intermediate_frequency_negative = data["intermediate_frequency"] < 0

    if "thread" in data:
        warnings.warn(
            deprecation_message("thread", "1.2.0", "1.3.0", "Use 'core' instead"),
            DeprecationWarning,
        )
        element.thread = element_thread_to_pb(data["thread"])
    if "core" in data:
        element.thread = element_thread_to_pb(data["core"])

    if "outputs" in data:
        for k, v in data["outputs"].items():
            element.outputs[k] = adc_port_ref_to_pb(*_get_port_reference_with_fem(v))
        element.multiple_outputs = QuaConfigMultipleOutputs(port_references=element.outputs)

    if "digitalInputs" in data:
        for digital_input_k, digital_input_v in data["digitalInputs"].items():
            element.digital_inputs[digital_input_k] = digital_input_port_ref_to_pb(digital_input_v)

    if "digitalOutputs" in data:
        for digital_output_k, digital_output_v in data["digitalOutputs"].items():
            element.digital_outputs[digital_output_k] = digital_output_port_ref_to_pb(digital_output_v)

    if "operations" in data:
        for op_name, op_value in data["operations"].items():
            element.operations[op_name] = op_value

    if "singleInput" in data:
        port_ref = _get_port_reference_with_fem(data["singleInput"]["port"])
        element.single_input = single_input_to_pb(*port_ref)

    if "mixInputs" in data:
        mix_inputs = data["mixInputs"]
        element.mix_inputs = QuaConfigMixInputs(
            i=dac_port_ref_to_pb(*_get_port_reference_with_fem(mix_inputs["I"])),
            q=dac_port_ref_to_pb(*_get_port_reference_with_fem(mix_inputs["Q"])),
            mixer=mix_inputs.get("mixer", ""),
        )

        lo_frequency = mix_inputs.get("lo_frequency", 0)
        element.mix_inputs.lo_frequency = int(lo_frequency)
        if capabilities.supports_double_frequency:
            element.mix_inputs.lo_frequency_double = float(lo_frequency)

    if "singleInputCollection" in data:
        element.single_input_collection = QuaConfigSingleInputCollection(
            inputs={
                k: dac_port_ref_to_pb(*_get_port_reference_with_fem(v))
                for k, v in data["singleInputCollection"]["inputs"].items()
            }
        )

    if "multipleInputs" in data:
        element.multiple_inputs = QuaConfigMultipleInputs(
            inputs={
                k: dac_port_ref_to_pb(*_get_port_reference_with_fem(v))
                for k, v in data["multipleInputs"]["inputs"].items()
            }
        )

    if "MWInput" in data:
        element.microwave_input = QuaConfigMicrowaveInputPortReference(
            port=dac_port_ref_to_pb(*_get_port_reference_with_fem(data["MWInput"]["port"])),
            upconverter=data["MWInput"].get("upconverter", DEFAULT_DUC_IDX),
        )
    if "MWOutput" in data:
        mw_output = data["MWOutput"]
        element.microwave_output = QuaConfigMicrowaveOutputPortReference(
            port=adc_port_ref_to_pb(*_get_port_reference_with_fem(mw_output["port"])),
        )

    if "oscillator" in data:
        element.named_oscillator = data["oscillator"]
    elif "intermediate_frequency" not in data:
        element.no_oscillator = Empty()

    if "sticky" in data:
        if "duration" in data["sticky"]:
            validate_sticky_duration(data["sticky"]["duration"])
        if capabilities.supports_sticky_elements:
            element.sticky = QuaConfigSticky(
                analog=data["sticky"].get("analog", True),
                digital=data["sticky"].get("digital", False),
                duration=int(data["sticky"].get("duration", 4) / 4),
            )
        else:
            if "digital" in data["sticky"] and data["sticky"]["digital"]:
                raise ConfigValidationException(
                    f"Server does not support digital sticky used in element " f"'{element_name}'"
                )
            element.hold_offset = QuaConfigHoldOffset(duration=int(data["sticky"].get("duration", 4) / 4))

    elif "hold_offset" in data:
        if capabilities.supports_sticky_elements:
            element.sticky = QuaConfigSticky(
                analog=True,
                digital=False,
                duration=data["hold_offset"].get("duration", 1),
            )
        else:
            element.hold_offset = QuaConfigHoldOffset(duration=data["hold_offset"]["duration"])

    if "outputPulseParameters" in data:
        warnings.warn(
            deprecation_message("outputPulseParameters", "1.2.0", "1.3.0" "Use timeTaggingParameters instead"),
            DeprecationWarning,
        )
        element.output_pulse_parameters = create_time_tagging_parameters(data["outputPulseParameters"])
    if "timeTaggingParameters" in data:
        element.output_pulse_parameters = create_time_tagging_parameters(data["timeTaggingParameters"])

    rf_inputs = data.get("RF_inputs", {})
    for k, (device, port) in rf_inputs.items():
        element.rf_inputs[k] = QuaConfigGeneralPortReference(device_name=device, port=port)

    rf_outputs = data.get("RF_outputs", {})
    for k, (device, port) in rf_outputs.items():
        element.rf_outputs[k] = QuaConfigGeneralPortReference(device_name=device, port=port)
    return element


def constant_waveform_to_protobuf(data: ConstantWaveformConfigType) -> QuaConfigWaveformDec:
    return QuaConfigWaveformDec(constant=QuaConfigConstantWaveformDec(sample=data["sample"]))


def arbitrary_waveform_to_protobuf(data: ArbitraryWaveformConfigType) -> QuaConfigWaveformDec:
    wf = QuaConfigWaveformDec()

    is_overridable = data.get("is_overridable", False)
    has_max_allowed_error = "max_allowed_error" in data
    has_sampling_rate = "sampling_rate" in data
    validate_arbitrary_waveform(is_overridable, has_max_allowed_error, has_sampling_rate)

    wf.arbitrary = QuaConfigArbitraryWaveformDec(samples=data["samples"], is_overridable=is_overridable)

    if has_max_allowed_error:
        wf.arbitrary.max_allowed_error = data["max_allowed_error"]
    elif has_sampling_rate:
        wf.arbitrary.sampling_rate = data["sampling_rate"]
    elif not is_overridable:
        wf.arbitrary.max_allowed_error = 1e-4
    return wf


@inject
def waveform_array_to_protobuf(
    data: WaveformArrayConfigType, server_capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities]
) -> QuaConfigWaveformDec:
    server_capabilities.validate({QopCaps.waveform_array})

    return QuaConfigWaveformDec(
        array=QuaConfigWaveformArrayDec(
            samples_array=[QuaConfigWaveformSamples(list(samples)) for samples in data["samples_array"]]
        )
    )


def digital_waveform_to_pb(data: DigitalWaveformConfigType) -> QuaConfigDigitalWaveformDec:
    return QuaConfigDigitalWaveformDec(
        samples=[QuaConfigDigitalWaveformSample(value=bool(s[0]), length=s[1]) for s in data["samples"]]
    )


def pulse_to_pb(data: PulseConfigType) -> QuaConfigPulseDec:
    pulse = QuaConfigPulseDec()

    if "length" in data:
        pulse.length = int(data["length"])

    if data["operation"] == "control":
        pulse.operation = QuaConfigPulseDecOperation.CONTROL
    elif data["operation"] == "measurement":
        pulse.operation = QuaConfigPulseDecOperation.MEASUREMENT
    else:
        raise ConfigValidationException(f"Invalid operation {data['operation']}")

    if "digital_marker" in data:
        pulse.digital_marker = data["digital_marker"]

    if "integration_weights" in data:
        for k, v in data["integration_weights"].items():
            pulse.integration_weights[k] = v

    if "waveforms" in data:
        pulse.waveforms = {k_: str(v_) for k_, v_ in data["waveforms"].items()}
    return pulse


def _standardize_iw_data(data: Union[List[Tuple[float, int]], List[float]]) -> List[Tuple[float, int]]:
    if len(data) == 0 or isinstance(data[0], (tuple, list)):
        to_return = []
        for x in data:
            x = cast(Tuple[float, int], x)
            to_return.append((x[0], x[1]))
        return to_return

    if isinstance(data[0], numbers.Number):
        if len(data) == 2:
            d0, d1 = cast(Tuple[float, int], data)
            return [(float(d0), int(d1))]

        data = cast(List[float], data)
        chunks = split_list_to_chunks([round(2**-15 * round(s * 2**15), 20) for s in data])
        new_data: List[Tuple[float, int]] = []
        for chunk in chunks:
            if chunk.accepts_different:
                new_data.extend([(float(u), 4) for u in chunk.data])
            else:
                new_data.append((chunk.first, 4 * len(chunk)))
        return new_data

    raise ConfigValidationException(f"Invalid IW data, data must be a list of numbers or 2-tuples, got {data}.")


def build_iw_sample(data: Union[List[Tuple[float, int]], List[float]]) -> List[QuaConfigIntegrationWeightSample]:
    clean_data = _standardize_iw_data(data)
    return [QuaConfigIntegrationWeightSample(value=s[0], length=int(s[1])) for s in clean_data]


def integration_weights_to_pb(data: IntegrationWeightConfigType) -> QuaConfigIntegrationWeightDec:
    iw = QuaConfigIntegrationWeightDec(cosine=build_iw_sample(data["cosine"]), sine=build_iw_sample(data["sine"]))
    return iw


def _all_controllers_are_opx(control_devices: Dict[str, QuaConfigDeviceDec]) -> bool:
    for device_config in control_devices.values():
        for fem_config in device_config.fems.values():
            _, controller_inst = betterproto.which_one_of(fem_config, "fem_type_one_of")
            if not isinstance(controller_inst, QuaConfigControllerDec):
                return False
    return True


def set_octave_upconverter_connection_to_elements(pb_config: QuaConfig) -> None:
    octaves_config = get_controller_pb_config(pb_config).octaves
    elements_config = get_logical_pb_config(pb_config).elements

    for element in elements_config.values():
        for rf_input in element.rf_inputs.values():
            if rf_input.device_name in octaves_config:
                if rf_input.port in octaves_config[rf_input.device_name].rf_outputs:
                    _, element_input = betterproto.which_one_of(element, "element_inputs_one_of")
                    if element_input is not None:
                        raise ElementInputConnectionAmbiguity("Ambiguous definition of element input")

                    upconverter_config = octaves_config[rf_input.device_name].rf_outputs[rf_input.port]
                    element.mix_inputs = QuaConfigMixInputs(
                        i=upconverter_config.i_connection, q=upconverter_config.q_connection
                    )


def _get_rf_output_for_octave(
    element: QuaConfigElementDec, octaves: Dict[str, QuaConfigOctaveConfig]
) -> Optional[QuaConfigOctaveRfOutputConfig]:
    if element.rf_inputs:
        element_rf_input = list(element.rf_inputs.values())[0]
        octave_config = octaves[element_rf_input.device_name]
        return octave_config.rf_outputs[element_rf_input.port]

    # This part is for users that do not use the rf_inputs  for connecting the octave
    element_input = element.mix_inputs
    for octave in octaves.values():
        for rf_output in octave.rf_outputs.values():
            if all(
                [
                    (rf_output.i_connection.controller == element_input.i.controller),
                    (rf_output.i_connection.fem == element_input.i.fem),
                    (rf_output.i_connection.number == element_input.i.number),
                    (rf_output.q_connection.controller == element_input.q.controller),
                    (rf_output.q_connection.fem == element_input.q.fem),
                    (rf_output.q_connection.number == element_input.q.number),
                ]
            ):
                return rf_output
    return None


@inject
def set_lo_frequency_to_mix_input_elements_that_are_connected_to_octave(
    pb_config: QuaConfig, capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities]
) -> None:
    octaves_config = get_controller_pb_config(pb_config).octaves
    elements_config = get_logical_pb_config(pb_config).elements

    for element in elements_config.values():
        _, element_input = betterproto.which_one_of(element, "element_inputs_one_of")
        if isinstance(element_input, QuaConfigMixInputs):
            rf_output = _get_rf_output_for_octave(element, octaves_config)
            if rf_output is None:
                continue

            if element_input.lo_frequency not in {0, int(rf_output.lo_frequency)}:
                raise ConfigValidationException(
                    "LO frequency mismatch. The frequency stated in the element is different from "
                    "the one stated in the Octave, remove the one in the element."
                )
            element_input.lo_frequency = int(rf_output.lo_frequency)
            if capabilities.supports_double_frequency:
                element_input.lo_frequency_double = rf_output.lo_frequency


I_IN_PORT = "I"
Q_IN_PORT = "Q"


def set_octave_downconverter_connection_to_elements(pb_config: QuaConfig) -> None:
    octaves_config = get_controller_pb_config(pb_config).octaves
    elements_config = get_logical_pb_config(pb_config).elements

    for element in elements_config.values():
        for _, rf_output in element.rf_outputs.items():
            if rf_output.device_name in octaves_config:
                if rf_output.port in octaves_config[rf_output.device_name].rf_inputs:
                    downconverter_config = octaves_config[rf_output.device_name].if_outputs
                    outputs_form_octave = {
                        downconverter_config.if_out1.name: downconverter_config.if_out1.port,
                        downconverter_config.if_out2.name: downconverter_config.if_out2.port,
                    }
                    for k, v in outputs_form_octave.items():
                        if k in element.outputs:
                            if v != element.outputs[k]:
                                raise ElementOutputConnectionAmbiguity(
                                    f"Output {k} is connected to {element.outputs[k]} but the octave "
                                    f"downconverter is connected to {v}"
                                )
                        else:
                            element.outputs[k] = v
                            _, element_outputs = betterproto.which_one_of(element, "element_outputs_one_of")
                            if isinstance(element_outputs, QuaConfigMicrowaveOutputPortReference):
                                raise ConfigValidationException("Cannot connect octave to microwave output")
                            elif isinstance(element_outputs, QuaConfigMultipleOutputs):
                                element_outputs.port_references[k] = v
                            else:
                                element.multiple_outputs = QuaConfigMultipleOutputs(port_references={k: v})


def set_non_existing_mixers_in_mix_input_elements(pb_config: QuaConfig) -> None:
    mixers_config = get_controller_pb_config(pb_config).mixers
    elements_config = get_logical_pb_config(pb_config).elements

    for element_name, element in elements_config.items():
        _, element_input = betterproto.which_one_of(element, "element_inputs_one_of")
        if isinstance(element_input, QuaConfigMixInputs):
            if (
                element.intermediate_frequency
            ):  # This is here because in validation I saw that we can set an element without IF
                if not element_input.mixer:
                    element_input.mixer = f"{element_name}_mixer_{uuid.uuid4().hex[:3]}"
                    # The uuid is just to make sure the mixer doesn't exist
                if element_input.mixer not in mixers_config:
                    mixers_config[element_input.mixer] = QuaConfigMixerDec(
                        correction=[
                            QuaConfigCorrectionEntry(
                                frequency=element.intermediate_frequency,
                                frequency_negative=element.intermediate_frequency_negative,
                                frequency_double=element.intermediate_frequency_double,
                                lo_frequency=element_input.lo_frequency,
                                lo_frequency_double=element_input.lo_frequency_double,
                                correction=QuaConfigMatrix(v00=1, v01=0, v10=0, v11=1),
                            )
                        ]
                    )


def validate_inputs_or_outputs_exist(pb_config: QuaConfig) -> None:
    elements_config = get_logical_pb_config(pb_config).elements

    for element in elements_config.values():
        _, element_input = betterproto.which_one_of(element, "element_inputs_one_of")
        _, element_outputs = betterproto.which_one_of(element, "element_outputs_one_of")
        if (
            element_input is None
            and element_outputs is None
            and not bool(element.outputs)  # this is for backward compatibility
            and not bool(element.digital_outputs)
            and not bool(element.digital_inputs)
        ):
            raise NoInputsOrOutputsError


def run_preload_validations(
    capabilities: ServerCapabilities,
    init_mode: bool,
    octave_in_current_config: bool,
    octave_already_configured: bool = False,
) -> None:
    # When the capabilities aren't initialized, the capabilities argument is of type 'Provide' instead of 'ServerCapabilities'
    if not isinstance(capabilities, ServerCapabilities):
        raise CapabilitiesNotInitializedError

    if not init_mode:
        # With these two validations, we ensure any configuration that relates to Octave is done in init mode.
        # Or in other words, Octave doesn't support 'send program with config'.

        if octave_in_current_config:
            raise OctaveUnsupportedOnUpdate("Octaves are not supported in non-init mode")

        if octave_already_configured:
            # If Octaves were already configured, we cannot change the configuration anymore, because it may override
            # automatic configurations that were done for Octave, like the ones in "apply_post_load_setters()".
            raise ConfigurationLockedByOctave(
                "Since Octaves were used in the initial configuration, no further modifications to the configuration are allowed — whether related to Octaves or not. "
                "To resolve this, either avoid using Octaves, or ensure all configuration - both controller and logical - is completed when opening the QM."
            )


def set_config_wrapper(capabilities: ServerCapabilities) -> QuaConfig:
    pb_config = QuaConfig()

    if capabilities.supports(QopCaps.config_v2):
        pb_config.v2 = QuaConfigQuaConfigV2(
            controller_config=QuaConfigControllerConfig(), logical_config=QuaConfigLogicalConfig()
        )
    else:
        pb_config.v1_beta = QuaConfigQuaConfigV1()

    return pb_config


def apply_post_load_setters(pb_config: QuaConfig, capabilities: ServerCapabilities) -> None:
    set_octave_upconverter_connection_to_elements(pb_config)
    set_lo_frequency_to_mix_input_elements_that_are_connected_to_octave(pb_config)
    set_octave_downconverter_connection_to_elements(pb_config)

    # In config_v2, elements can be defined independently of mixers.
    # This breaks the existing logic, which automatically assigns default mixers based on the elements.
    # As a result, users of config_v2 must manually specify the mixers—otherwise, the gateway will raise a clear exception.
    # The long-term goal is to move this logic into the gateway itself. For more details, see: https://quantum-machines.atlassian.net/browse/OPXK-25086
    if not capabilities.supports(QopCaps.config_v2):
        set_non_existing_mixers_in_mix_input_elements(pb_config)


@inject
def load_config_pb(
    config: Union[FullQuaConfig, ControllerQuaConfig, LogicalQuaConfig],
    init_mode: bool = True,
    octave_already_configured: bool = False,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> QuaConfig:

    run_preload_validations(
        capabilities,
        init_mode,
        "octaves" in config,
        octave_already_configured,
    )

    pb_config = set_config_wrapper(capabilities)
    controller_config = get_controller_pb_config(pb_config)
    logical_config = get_logical_pb_config(pb_config)

    def set_controllers() -> None:
        for k, v in config["controllers"].items():  # type: ignore[typeddict-item]
            controller_config.control_devices[k] = controlling_devices_to_pb(v, init_mode)
        # Controllers attribute is supported only in config v1
        if _all_controllers_are_opx(controller_config.control_devices) and isinstance(
            controller_config, QuaConfigQuaConfigV1
        ):
            for _k, _v in controller_config.control_devices.items():
                controller_inst = get_fem_config_instance(_v.fems[OPX_FEM_IDX])
                if not isinstance(controller_inst, QuaConfigControllerDec):
                    raise ValueError("This should not happen")
                controller_config.controllers[_k] = controller_inst

    def set_octaves() -> None:
        for k, v in config.get("octaves", {}).items():  # type: ignore[attr-defined]
            controller_config.octaves[k] = octave_to_pb(v)

    def set_elements() -> None:
        for k, v in config["elements"].items():  # type: ignore[typeddict-item]
            logical_config.elements[k] = element_to_pb(k, v)

    def set_pulses() -> None:
        for k, v in config["pulses"].items():  # type: ignore[typeddict-item]
            logical_config.pulses[k] = pulse_to_pb(v)

    def set_waveforms() -> None:
        for k, v in config["waveforms"].items():  # type: ignore[typeddict-item]
            if v["type"] == "constant":
                logical_config.waveforms[k] = constant_waveform_to_protobuf(cast(ConstantWaveformConfigType, v))
            elif v["type"] == "arbitrary":
                logical_config.waveforms[k] = arbitrary_waveform_to_protobuf(cast(ArbitraryWaveformConfigType, v))
            elif v["type"] == "array":
                logical_config.waveforms[k] = waveform_array_to_protobuf(cast(WaveformArrayConfigType, v))
            else:
                raise ValueError("Unknown waveform type")

    def set_digital_waveforms() -> None:
        for k, v in config["digital_waveforms"].items():  # type: ignore[typeddict-item]
            logical_config.digital_waveforms[k] = digital_waveform_to_pb(v)

    def set_integration_weights() -> None:
        for k, v in config["integration_weights"].items():  # type: ignore[typeddict-item]
            logical_config.integration_weights[k] = integration_weights_to_pb(v)

    def set_mixers() -> None:
        for k, v in config["mixers"].items():  # type: ignore[typeddict-item]
            controller_config.mixers[k] = mixer_to_pb(list(v), init_mode)

    def set_oscillators() -> None:
        for k, v in config["oscillators"].items():  # type: ignore[typeddict-item]
            logical_config.oscillators[k] = oscillator_to_pb(v)

    key_to_action = {
        "version": lambda: None,
        "controllers": set_controllers,
        "elements": set_elements,
        "pulses": set_pulses,
        "waveforms": set_waveforms,
        "digital_waveforms": set_digital_waveforms,
        "integration_weights": set_integration_weights,
        "mixers": set_mixers,
        "oscillators": set_oscillators,
        "octaves": set_octaves,
    }

    if "version" in config:
        warnings.warn(
            deprecation_message("version", "1.2.2", "1.3.0", "Please remove it from the QUA config."),
            DeprecationWarning,
        )

    for key in config:
        key_to_action[key]()

    apply_post_load_setters(pb_config, capabilities)

    return pb_config
