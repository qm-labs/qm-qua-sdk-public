import logging
import warnings
from typing import (
    Any,
    Dict,
    List,
    Tuple,
    Union,
    Mapping,
    TypeVar,
    Callable,
    Optional,
    Sequence,
    TypedDict,
    Collection,
    cast,
    overload,
)

import betterproto
from betterproto.lib.google.protobuf import Empty
from dependency_injector.wiring import Provide, inject
from marshmallow_polyfield import PolyField  # type: ignore[import-untyped]
from marshmallow import Schema, ValidationError, fields, validate, post_load, validates_schema

from qm.utils import deprecation_message
from qm.containers.capabilities_container import CapabilitiesContainer
from qm.api.models.capabilities import OPX_FEM_IDX, QopCaps, ServerCapabilities
from qm.program._dict_to_pb_converter.main_config_converter import DictToQuaConfigConverter
from qm.program._dict_to_pb_converter.converters.integration_weights_converter import build_iw_sample
from qm.program._dict_to_pb_converter.converters.element_converter import DEFAULT_DUC_IDX, element_thread_to_pb
from qm.utils.config_utils import FemTypes, get_logical_pb_config, get_fem_config_instance, get_controller_pb_config
from qm.program._dict_to_pb_converter.converters.octave_converter import (
    IF_OUT1_DEFAULT,
    IF_OUT2_DEFAULT,
    dac_port_ref_to_pb,
    _get_port_reference_with_fem,
)
from qm.program._validate_config_schema import (
    validate_oscillator,
    validate_output_tof,
    validate_used_inputs,
    validate_output_smearing,
    validate_sticky_duration,
)
from qm.exceptions import (
    ConfigSchemaError,
    InvalidOctaveParameter,
    NoInputsOrOutputsError,
    ConfigValidationException,
    OctaveConnectionAmbiguity,
    CapabilitiesNotInitializedError,
)
from qm.type_hinting.config_types import (
    LoopbackType,
    FullQuaConfig,
    LfFemConfigType,
    MixerConfigType,
    MwFemConfigType,
    PulseConfigType,
    LogicalQuaConfig,
    StickyConfigType,
    ElementConfigType,
    MwInputConfigType,
    PortReferenceType,
    MixInputConfigType,
    ControllerQuaConfig,
    HoldOffsetConfigType,
    OscillatorConfigType,
    SingleInputConfigType,
    DigitalInputConfigType,
    MwUpconverterConfigType,
    OctaveRFInputConfigType,
    WaveformArrayConfigType,
    OctaveRFOutputConfigType,
    AnalogInputPortConfigType,
    DigitalWaveformConfigType,
    InputCollectionConfigType,
    AnalogOutputPortConfigType,
    ConstantWaveformConfigType,
    DigitalInputPortConfigType,
    ArbitraryWaveformConfigType,
    DigitalOutputPortConfigType,
    IntegrationWeightConfigType,
    MwFemAnalogInputPortConfigType,
    OctaveSingleIfOutputConfigType,
    MwFemAnalogOutputPortConfigType,
    TimeTaggingParametersConfigType,
    AnalogOutputPortConfigTypeOctoDac,
)
from qm.grpc.qua_config import (
    QuaConfig,
    QuaConfigSticky,
    QuaConfigFemTypes,
    QuaConfigMixerDec,
    QuaConfigPulseDec,
    QuaConfigDeviceDec,
    QuaConfigMixInputs,
    QuaConfigElementDec,
    QuaConfigHoldOffset,
    QuaConfigOscillator,
    QuaConfigQuaConfigV1,
    QuaConfigSingleInput,
    QuaConfigWaveformDec,
    QuaConfigOctaveConfig,
    QuaConfigControllerDec,
    QuaConfigOctoDacFemDec,
    QuaConfigPortReference,
    QuaConfigMultipleInputs,
    QuaConfigCorrectionEntry,
    QuaConfigMicrowaveFemDec,
    QuaConfigMultipleOutputs,
    QuaConfigAdcPortReference,
    QuaConfigDacPortReference,
    QuaConfigPulseDecOperation,
    QuaConfigAnalogInputPortDec,
    QuaConfigDigitalWaveformDec,
    QuaConfigAnalogOutputPortDec,
    QuaConfigDigitalInputPortDec,
    QuaConfigOctaveLoSourceInput,
    QuaConfigOctaveRfInputConfig,
    QuaConfigDigitalOutputPortDec,
    QuaConfigGeneralPortReference,
    QuaConfigIntegrationWeightDec,
    QuaConfigOctaveRfOutputConfig,
    QuaConfigUpConverterConfigDec,
    QuaConfigDigitalWaveformSample,
    QuaConfigOctaveIfOutputsConfig,
    QuaConfigOutputPulseParameters,
    QuaConfigSingleInputCollection,
    QuaConfigDigitalInputPortReference,
    QuaConfigDigitalOutputPortReference,
    QuaConfigOctaveSingleIfOutputConfig,
    QuaConfigOctoDacAnalogOutputPortDec,
    QuaConfigMicrowaveAnalogInputPortDec,
    QuaConfigMicrowaveInputPortReference,
    QuaConfigOctaveDownconverterRfSource,
    QuaConfigMicrowaveAnalogOutputPortDec,
    QuaConfigMicrowaveOutputPortReference,
)

logger = logging.getLogger(__name__)

INIT_MODE_KEY = "init_mode"
OCTAVE_ALREADY_CONFIGURED_KEY = "octave_already_configured"
FEM_NAME_ERROR = "FEM name error - "
CAPABILITIES_KEY = "capabilities"
CONVERTER_KEY = "converter"


def _get_port_address(controller_name: str, fem_idx: Optional[int], port_id: int) -> str:
    if fem_idx is not None:
        return f"controller: {controller_name}, fem: {fem_idx}, port: {port_id}"
    return f"controller: {controller_name}, port: {port_id}"


def _validate_no_inverted_port(
    controller: FemTypes,
    controller_name: str,
    fem_idx: int,
) -> None:
    for port_id, port in controller.digital_outputs.items():
        if port.inverted:
            address = _get_port_address(controller_name, fem_idx, port_id)
            raise ConfigValidationException(f"Server does not support inverted digital output used in {address}")


def _validate_no_analog_delay(
    controller: FemTypes,
    controller_name: str,
    fem_idx: int,
) -> None:
    for port_id, port in controller.analog_outputs.items():
        if port.delay != 0:
            address = _get_port_address(controller_name, fem_idx, port_id)
            raise ConfigValidationException(f"Server does not support analog delay used in {address}")


def validate_no_crosstalk(
    controller: FemTypes,
    controller_name: str,
    fem_idx: int,
) -> None:
    if isinstance(controller, QuaConfigMicrowaveFemDec):
        return
    for port_id, port in controller.analog_outputs.items():
        if len(port.crosstalk) > 0:
            address = _get_port_address(controller_name, fem_idx, port_id)
            raise ConfigValidationException(f"Server does not support channel weights used in {address}")


def validate_config_capabilities(pb_config: QuaConfig, server_capabilities: ServerCapabilities) -> None:
    controller_config = get_controller_pb_config(pb_config)
    logical_config = get_logical_pb_config(pb_config)

    if not server_capabilities.supports(QopCaps.inverted_digital_output):
        for con_name, con in controller_config.control_devices.items():
            for fem_name, fem in con.fems.items():
                fem_config = get_fem_config_instance(fem)
                if isinstance(fem_config, (QuaConfigControllerDec, QuaConfigOctoDacFemDec)):
                    _validate_no_inverted_port(fem_config, controller_name=con_name, fem_idx=fem_name)

    if not server_capabilities.supports(QopCaps.multiple_inputs_for_element):
        for el_name, el in logical_config.elements.items():
            if el is not None and isinstance(
                betterproto.which_one_of(el, "element_inputs_one_of")[1], QuaConfigMultipleInputs
            ):
                raise ConfigValidationException(
                    f"Server does not support multiple inputs for elements used in '{el_name}'"
                )

    if not server_capabilities.supports(QopCaps.analog_delay):
        for con_name, con in controller_config.control_devices.items():
            for fem_idx, fem in con.fems.items():
                fem_config = get_fem_config_instance(fem)

                _validate_no_analog_delay(fem_config, controller_name=con_name, fem_idx=fem_idx)

    if not server_capabilities.supports(QopCaps.shared_oscillators):
        for el_name, el in logical_config.elements.items():
            if el is not None and betterproto.which_one_of(el, "oscillator_one_of")[0] == "named_oscillator":
                raise ConfigValidationException(
                    f"Server does not support shared oscillators for elements used in " f"'{el_name}'"
                )

    if not server_capabilities.supports(QopCaps.crosstalk):
        for con_name, con in controller_config.control_devices.items():
            for fem_idx, fem in con.fems.items():
                fem_config = get_fem_config_instance(fem)
                validate_no_crosstalk(fem_config, controller_name=con_name, fem_idx=fem_idx)

    if not server_capabilities.supports(QopCaps.shared_ports):
        shared_ports_by_controller = {}
        for con_name, con in controller_config.control_devices.items():
            for _, fem in con.fems.items():
                fem_config = get_fem_config_instance(fem)
                shared_ports_by_type = {}
                analog_outputs = [port_id for port_id, port in fem_config.analog_outputs.items() if port.shareable]
                analog_inputs = [port_id for port_id, port in fem_config.analog_inputs.items() if port.shareable]
                digital_outputs = [port_id for port_id, port in fem_config.digital_outputs.items() if port.shareable]
                digital_inputs = [port_id for port_id, port in fem_config.digital_inputs.items() if port.shareable]
                if len(analog_outputs):
                    shared_ports_by_type["analog_outputs"] = analog_outputs
                if len(analog_inputs):
                    shared_ports_by_type["analog_inputs"] = analog_inputs
                if len(digital_outputs):
                    shared_ports_by_type["digital_outputs"] = digital_outputs
                if len(digital_inputs):
                    shared_ports_by_type["digital_inputs"] = digital_inputs
                if len(shared_ports_by_type):
                    shared_ports_by_controller[con_name] = shared_ports_by_type

        if len(shared_ports_by_controller) > 0:
            error_message = "Server does not support shareable ports." + "\n".join(
                [
                    f"Controller: {con_name}\n{shared_ports_list}"
                    for con_name, shared_ports_list in shared_ports_by_controller.items()
                ]
            )
            raise ConfigValidationException(error_message)
    if not server_capabilities.supports_double_frequency:
        message_template = (
            "Server does not support float frequency. "
            "Element: {element_name}: {frequency_type}={float_value} "
            "will be casted to {int_value}."
        )
        for el_name, el in list(logical_config.elements.items()):
            if el.intermediate_frequency_double and el.intermediate_frequency_double != el.intermediate_frequency:
                logger.warning(
                    message_template.format(
                        element_name=el_name,
                        frequency_type="intermediate_frequency",
                        float_value=el.intermediate_frequency_double,
                        int_value=el.intermediate_frequency,
                    )
                )
            if (
                isinstance(betterproto.which_one_of(el, "element_inputs_one_of"), QuaConfigMixInputs)
                and el.mix_inputs.lo_frequency_double
                and el.mix_inputs.lo_frequency != el.mix_inputs.lo_frequency_double
            ):
                logger.warning(
                    message_template.format(
                        element_name=el_name,
                        frequency_type="lo_frequency",
                        float_value=el.mix_inputs.lo_frequency_double,
                        int_value=el.mix_inputs.lo_frequency,
                    )
                )


@inject
def load_config(
    config: Union[FullQuaConfig, ControllerQuaConfig, LogicalQuaConfig],
    init_mode: bool = True,
    octave_already_configured: bool = False,
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> QuaConfig:
    # When the capabilities aren't initialized, the capabilities argument is of type 'Provide' instead of 'ServerCapabilities'
    if not isinstance(capabilities, ServerCapabilities):
        raise CapabilitiesNotInitializedError
    try:
        return cast(
            QuaConfig,
            QuaConfigSchema(
                context={
                    INIT_MODE_KEY: init_mode,
                    OCTAVE_ALREADY_CONFIGURED_KEY: octave_already_configured,
                    CAPABILITIES_KEY: capabilities,
                    CONVERTER_KEY: DictToQuaConfigConverter(capabilities, init_mode),
                }
            ).load(config),
        )
    except ValidationError as validation_error:
        raise ConfigSchemaError(validation_error) from validation_error


def _create_tuple_field(tuple_fields: List[fields.Field], description: Optional[str] = None) -> fields.Tuple:
    """This function allows us to ignore the [no-untyped-call] just once."""
    metadata = {"description": description} if description is not None else None
    return fields.Tuple(tuple_fields, metadata=metadata)  # type: ignore[no-untyped-call]


class UnionField(fields.Field):
    """Field that deserializes multi-type input data to app-level objects."""

    def __init__(self, val_types: List[fields.Field], **kwargs: Any):
        self.valid_types = val_types
        super().__init__(**kwargs)

    def _deserialize(
        self, value: Any, attr: Optional[str] = None, data: Optional[Mapping[str, Any]] = None, **kwargs: Any
    ) -> Any:
        """
        _deserialize defines a custom Marshmallow Schema Field that takes in
        multi-type input data to app-level objects.

        Parameters
        ----------
        value : {Any}
            The value to be deserialized.

        Keyword Parameters
        ----------
        attr : {str} [Optional]
            The attribute/key in data to be deserialized. (default: {None})
        data : {Optional[Mapping[str, Any]]}
            The raw input data passed to the Schema.load. (default: {None})

        Raises
        ----------
        ValidationError : Exception
            Raised when the validation fails on a field or schema.
        """
        errors = []
        # iterate through the types being passed into UnionField via val_types
        for field in self.valid_types:
            try:
                # inherit deserialize method from Fields class
                return field.deserialize(value, attr, data, **kwargs)
            # if error, add error message to error list
            except ValidationError as error:
                errors.append(error)

        if _there_was_no_mistake_in_fem_name(errors):
            _raise_right_fem_error(errors)

        raise ValidationError([error.messages for error in errors])


def _there_was_no_mistake_in_fem_name(errors: List[ValidationError]) -> bool:
    if len(errors) <= 1:
        return False

    type_error_counter = 0
    for error in errors:
        if _error_has_fem_name_error(error):
            type_error_counter += 1

    return type_error_counter == len(errors) - 1


def _raise_right_fem_error(errors: List[ValidationError]) -> None:
    for error in errors:
        if _error_has_fem_name_error(error):
            continue
        raise error


def _error_has_fem_name_error(error: ValidationError) -> bool:
    return (
        isinstance(error.messages, dict)
        and "type" in error.messages
        and any(x.startswith(FEM_NAME_ERROR) for x in error.messages["type"])
    )


PortReferenceSchema = UnionField(
    [
        _create_tuple_field(
            [fields.String(), fields.Int()],
            description="Controller port to use. " "Tuple of: ([str] controller name, [int] controller port)",
        ),
        _create_tuple_field(
            [fields.String(), fields.Int(), fields.Int()],
            description="Controller port to use. Tuple of: ([str] controller name, [int] fem index, [int] controller port)",
        ),
    ]
)


def validate_string_is_one_of(valid_values: Collection[str]) -> Callable[[str], None]:
    valid_values = {value.lower() for value in valid_values}

    def _validate(string: str) -> None:
        if not string.lower() in valid_values:
            raise ValidationError(f"Value '{string}' is not one of the valid values: {valid_values}")

    return _validate


class AnalogOutputFilterDefSchema(Schema):
    feedforward = fields.List(
        fields.Float(),
        metadata={"description": "Feedforward taps for the analog output filter. List of double"},
    )
    feedback = fields.List(
        fields.Float(),
        metadata={
            "description": "Feedback taps for the analog output filter. List of double. IIR filtering approach "
            "prior to QOP 3.3"
        },
    )
    exponential = fields.List(
        _create_tuple_field(
            [
                fields.Float(metadata={"description": "Amplitude of the exponential filter."}),
                fields.Float(metadata={"description": "Time constant of the exponential filter."}),
            ]
        ),
        metadata={"description": "Exponential filter parameters. IIR filtering approach since QOP 3.3."},
    )
    high_pass = fields.Float(
        allow_none=True,
        metadata={
            "description": "High-pass compensation filter, used to compensate for the low-frequency cutoff of "
            "the signal. IIR filtering approach since QOP 3.3"
        },
    )
    exponential_dc_gain = fields.Float(
        allow_none=True, metadata={"description": "DC gain of the IIR filters, supported since QOP 3.5."}
    )


class AnalogOutputPortDefSchema(Schema):
    grpc_class = QuaConfigAnalogOutputPortDec
    offset = fields.Float(
        metadata={"description": "DC offset to the output." "Will be applied while quantum machine is open."},
    )
    filter = fields.Nested(AnalogOutputFilterDefSchema)
    delay = fields.Int(metadata={"description": "Output's delay, in units of ns."})
    crosstalk = fields.Dict(
        keys=fields.Int(), values=fields.Float(), metadata={"description": ""}
    )  # TODO: add description
    shareable = fields.Bool(
        metadata={"description": "Whether the port is shareable with other QM instances"},
    )

    class Meta:
        title = "Analog output port"
        description = "The specifications and properties of an analog output port of the controller."

    @post_load(pass_many=False)
    def build(self, data: AnalogOutputPortConfigType, **kwargs: Any) -> QuaConfigAnalogOutputPortDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.control_device_converter.analog_output_port_to_pb(data, output_type=self.grpc_class)


class MwUpconverterSchema(Schema):
    frequency = fields.Float()

    @post_load(pass_many=False)
    def build(self, data: MwUpconverterConfigType, **kwargs: Any) -> QuaConfigUpConverterConfigDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.control_device_converter.upconverter_config_dec_to_pb(data)


class AnalogOutputPortDefSchemaMwFem(Schema):
    sampling_rate = fields.Float(
        metadata={"description": "Sampling rate of the port."},
    )
    full_scale_power_dbm = fields.Int(
        strict=True,
        metadata={
            "description": "The power in dBm of the full scale of the output, "
            "should be an integer between -41 and 10 in steps of 3"
        },
    )
    band = fields.Int(
        metadata={"description": "The frequency band of the oscillator, can be 1, 2 or 3"},
    )

    delay = fields.Int(metadata={"description": "Output's delay, in units of ns."})
    shareable = fields.Bool(
        dump_default=False,
        metadata={"description": "Whether the port is shareable with other QM instances"},
    )
    upconverters = fields.Dict(
        keys=fields.Int(),
        values=fields.Nested(MwUpconverterSchema),
        metadata={"description": "A mapping between the upconverters and their frequencies"},
    )
    upconverter_frequency = fields.Float(metadata={"description": "A short for using only one upconverter (1)"})

    class Meta:
        title = "Analog output port of the MW-FEM"
        description = "The specifications and properties of an analog output port of the MW-FEM controller."

    @post_load(pass_many=False)
    def build(self, data: MwFemAnalogOutputPortConfigType, **kwargs: Any) -> QuaConfigMicrowaveAnalogOutputPortDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.control_device_converter.mw_fem_analog_output_to_pb(data)


class AnalogInputPortDefSchemaMwFem(Schema):
    sampling_rate = fields.Float(
        metadata={"description": "Sampling rate of the port."},
    )
    gain_db = fields.Int(
        strict=True,
        metadata={"description": "Gain of the pre-ADC amplifier, in dB. Accepts integers."},
    )
    shareable = fields.Bool(
        dump_default=False,
        metadata={"description": "Whether the port is shareable with other QM instances"},
    )
    band = fields.Int(
        metadata={"description": "The frequency band of the oscillator, can be 1, 2 or 3"},
    )
    downconverter_frequency = fields.Float(
        metadata={"description": "The frequency of the downconverter attached to this port"}
    )

    class Meta:
        title = "Analog input port of the MW-FEM"
        description = "The specifications and properties of an analog input port of the MW-FEM controller."

    @post_load(pass_many=False)
    def build(self, data: MwFemAnalogInputPortConfigType, **kwargs: Any) -> QuaConfigMicrowaveAnalogInputPortDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.control_device_converter.mw_fem_analog_input_port_to_pb(data)


class AnalogOutputPortDefSchemaOPX1000(AnalogOutputPortDefSchema):
    grpc_class = QuaConfigOctoDacAnalogOutputPortDec  # type: ignore[assignment]

    sampling_rate = fields.Float(
        metadata={"description": "Sampling rate of the port."},
    )
    upsampling_mode = fields.String(
        metadata={"description": "Mode of sampling rate, can be mw (default) or pulse"},
        validate=validate_string_is_one_of({"mw", "pulse"}),
    )
    output_mode = fields.String(
        metadata={"description": "Mode of the port, can be direct (default) or amplified"},
        validate=validate_string_is_one_of({"direct", "amplified"}),
    )

    @post_load(pass_many=False)
    def build(self, data: AnalogOutputPortConfigTypeOctoDac, **kwargs: Any) -> QuaConfigOctoDacAnalogOutputPortDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.control_device_converter.opx_1000_analog_output_port_to_pb(data)


class AnalogInputPortDefSchema(Schema):
    offset = fields.Float(
        metadata={"description": "DC offset to the input."},
    )

    gain_db = fields.Int(
        strict=True,
        metadata={"description": "Gain of the pre-ADC amplifier, in dB. Accepts integers."},
    )

    shareable = fields.Bool(
        metadata={"description": "Whether the port is shareable with other QM instances"},
    )

    sampling_rate = fields.Float(
        strict=True,
        metadata={"description": "Sampling rate for this port."},
    )

    class Meta:
        title = "Analog input port"
        description = "The specifications and properties of an analog input port of the controller."

    @post_load(pass_many=False)
    def build(self, data: AnalogInputPortConfigType, **kwargs: Any) -> QuaConfigAnalogInputPortDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.control_device_converter.analog_input_port_to_pb(data)


class DigitalOutputPortDefSchema(Schema):
    shareable = fields.Bool(
        dump_default=False,
        metadata={"description": "Whether the port is shareable with other QM instances"},
    )
    inverted = fields.Bool(
        dump_default=False,
        metadata={"description": "Whether the port is inverted. " "If True, the output will be inverted."},
    )
    level = fields.String(
        metadata={
            "description": "The voltage level of the digital output, can be TTL or LVTTL (default). "
            "Currently, only LVTTL is supported."
        },
    )

    class Meta:
        title = "Digital port"
        description = "The specifications and properties of a digital output port of the controller."

    @post_load(pass_many=False)
    def build(self, data: DigitalOutputPortConfigType, **kwargs: Any) -> QuaConfigDigitalOutputPortDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.control_device_converter.digital_output_port_to_pb(data)


class DigitalInputPortDefSchema(Schema):
    deadtime = fields.Int(metadata={"description": "The minimal time between pulses, in ns."})
    polarity = fields.String(
        metadata={"description": "The Detection edge - Whether to trigger in the rising or falling edge of the pulse"},
    )
    threshold = fields.Float(metadata={"description": "The minimum voltage to trigger when a pulse arrives"})
    shareable = fields.Bool(
        metadata={"description": "Whether the port is shareable with other QM instances"},
    )

    class Meta:
        title = "Digital input port"
        description = "The specifications and properties of a digital input " "port of the controller."

    @post_load(pass_many=False)
    def build(self, data: DigitalInputPortConfigType, **kwargs: Any) -> QuaConfigDigitalInputPortDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.control_device_converter.digital_input_port_to_pb(data)


class OctaveRFOutputSchema(Schema):
    LO_frequency = fields.Float(metadata={"description": "The frequency of the LO in Hz"})
    LO_source = fields.String(
        metadata={"description": "The source of the LO}, e.g. 'internal' or 'external'"},
        validate=validate_string_is_one_of({"internal", "external"}),
    )
    output_mode = fields.String(
        metadata={"description": "The output mode of the RF output"},
        validate=validate_string_is_one_of({"always_on", "always_off", "triggered", "triggered_reversed"}),
    )
    gain = fields.Float(metadata={"description": "The gain of the RF output in dB"})
    input_attenuators = fields.String(
        metadata={"description": "The attenuators of the I and Q inputs"},
        validate=validate_string_is_one_of({"on", "off"}),
    )
    I_connection = PortReferenceSchema
    Q_connection = PortReferenceSchema

    @post_load(pass_many=False)
    def build(self, data: OctaveRFOutputConfigType, **kwargs: Any) -> QuaConfigOctaveRfOutputConfig:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.octave_converter.rf_module_to_pb(data)


class OctaveRFInputSchema(Schema):
    RF_source = fields.String()
    LO_frequency = fields.Float()
    LO_source = fields.String()
    IF_mode_I = fields.String()
    IF_mode_Q = fields.String()

    @post_load(pass_many=False)
    def build(self, data: OctaveRFInputConfigType, **kwargs: Any) -> QuaConfigOctaveRfInputConfig:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.octave_converter.rf_input_to_pb(data)


class SingleIFOutputSchema(Schema):
    port = PortReferenceSchema
    name = fields.String()

    @post_load(pass_many=False)
    def build(self, data: OctaveSingleIfOutputConfigType, **kwargs: Any) -> QuaConfigOctaveSingleIfOutputConfig:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.octave_converter.single_if_output_to_pb(data)


class _SemiBuiltIFOutputsConfig(TypedDict, total=False):
    IF_out1: QuaConfigOctaveSingleIfOutputConfig
    IF_out2: QuaConfigOctaveSingleIfOutputConfig


class IFOutputsSchema(Schema):
    IF_out1 = fields.Nested(SingleIFOutputSchema)
    IF_out2 = fields.Nested(SingleIFOutputSchema)

    @post_load(pass_many=False)
    def build(self, data: _SemiBuiltIFOutputsConfig, **kwargs: Any) -> QuaConfigOctaveIfOutputsConfig:
        to_return = QuaConfigOctaveIfOutputsConfig()
        if "IF_out1" in data:
            to_return.if_out1 = data["IF_out1"]
        if "IF_out2" in data:
            to_return.if_out2 = data["IF_out2"]
        return to_return


class _SemiBuiltOctaveConfig(TypedDict, total=False):
    loopbacks: List[LoopbackType]
    RF_outputs: Dict[int, QuaConfigOctaveRfOutputConfig]
    RF_inputs: Dict[int, QuaConfigOctaveRfInputConfig]
    IF_outputs: QuaConfigOctaveIfOutputsConfig
    connectivity: Union[str, Tuple[str, int]]


class OctaveSchema(Schema):
    loopbacks = fields.List(
        _create_tuple_field([_create_tuple_field([fields.String(), fields.String()]), fields.String()]),
        metadata={
            "description": "List of loopbacks that connected to this octave, Each loopback is "
            "in the form of ((octave_name, octave_port), target_port)"
        },
    )
    RF_outputs = fields.Dict(
        keys=fields.Int(),
        values=fields.Nested(OctaveRFOutputSchema),
        metadata={"description": "The RF outputs and their properties."},
    )
    RF_inputs = fields.Dict(
        keys=fields.Int(),
        values=fields.Nested(OctaveRFInputSchema),
        metadata={"description": "The RF inputs and their properties."},
    )
    IF_outputs = fields.Nested(IFOutputsSchema)
    connectivity = UnionField(
        [fields.String(), _create_tuple_field([fields.String(), fields.Int()])],
        metadata={"description": "Sets the default connectivity for all RF outputs and inputs in the octave."},
    )

    @post_load(pass_many=False)
    def build(self, data: _SemiBuiltOctaveConfig, **kwargs: Any) -> QuaConfigOctaveConfig:
        converter: DictToQuaConfigConverter = self.context["converter"]

        to_return = QuaConfigOctaveConfig(
            loopbacks=converter.octave_converter.get_octave_loopbacks(data.get("loopbacks", [])),
            rf_outputs=data.get("RF_outputs", {}),
            rf_inputs=data.get("RF_inputs", {}),
        )
        for input_idx, input_config in to_return.rf_inputs.items():
            if input_config.lo_source == QuaConfigOctaveLoSourceInput.not_set:
                input_config.lo_source = (
                    QuaConfigOctaveLoSourceInput.internal if input_idx == 1 else QuaConfigOctaveLoSourceInput.external  # type: ignore[assignment]
                )
            if input_idx == 1 and input_config.rf_source != QuaConfigOctaveDownconverterRfSource.rf_in:
                raise InvalidOctaveParameter("Downconverter 1 must be connected to RF-in")

        if "IF_outputs" in data:
            to_return.if_outputs = data["IF_outputs"]

        if "connectivity" in data:
            connectivity = data["connectivity"]
            if isinstance(connectivity, str):
                controller_name, fem_idx = connectivity, OPX_FEM_IDX
            else:
                controller_name, fem_idx = connectivity
            for upconverter_idx, upconverter in to_return.rf_outputs.items():
                if betterproto.serialized_on_wire(upconverter.i_connection) or betterproto.serialized_on_wire(
                    upconverter.q_connection
                ):
                    raise OctaveConnectionAmbiguity
                upconverter.i_connection = dac_port_ref_to_pb(controller_name, fem_idx, 2 * upconverter_idx - 1)
                upconverter.q_connection = dac_port_ref_to_pb(controller_name, fem_idx, 2 * upconverter_idx)

            if betterproto.serialized_on_wire(to_return.if_outputs):
                raise OctaveConnectionAmbiguity
            to_return.if_outputs.if_out1 = QuaConfigOctaveSingleIfOutputConfig(
                port=QuaConfigAdcPortReference(controller=controller_name, fem=fem_idx, number=1),
                name=IF_OUT1_DEFAULT,
            )
            to_return.if_outputs.if_out2 = QuaConfigOctaveSingleIfOutputConfig(
                port=QuaConfigAdcPortReference(controller=controller_name, fem=fem_idx, number=2),
                name=IF_OUT2_DEFAULT,
            )
        return to_return


class _SemiBuiltControllerConfig(TypedDict, total=False):
    type: str
    analog_outputs: Dict[int, QuaConfigAnalogOutputPortDec]
    analog_inputs: Dict[int, QuaConfigAnalogInputPortDec]
    digital_outputs: Dict[int, QuaConfigDigitalOutputPortDec]
    digital_inputs: Dict[int, QuaConfigDigitalInputPortDec]


class _SemiBuiltOctoDacConfig(TypedDict, total=False):
    type: str
    analog_outputs: Dict[int, QuaConfigOctoDacAnalogOutputPortDec]
    analog_inputs: Dict[int, QuaConfigAnalogInputPortDec]
    digital_outputs: Dict[int, QuaConfigDigitalOutputPortDec]
    digital_inputs: Dict[int, QuaConfigDigitalInputPortDec]


class _SemiBuiltMwFemConfig(TypedDict, total=False):
    analog_outputs: Dict[int, QuaConfigMicrowaveAnalogOutputPortDec]
    analog_inputs: Dict[int, QuaConfigMicrowaveAnalogInputPortDec]
    digital_outputs: Dict[int, QuaConfigDigitalOutputPortDec]
    digital_inputs: Dict[int, QuaConfigDigitalInputPortDec]


ControllerType = TypeVar("ControllerType", QuaConfigControllerDec, QuaConfigOctoDacFemDec, QuaConfigMicrowaveFemDec)
_SemiBuiltControllerType = TypeVar(
    "_SemiBuiltControllerType", _SemiBuiltControllerConfig, _SemiBuiltOctoDacConfig, _SemiBuiltMwFemConfig
)


@overload
def _append_data_to_controller(
    data: _SemiBuiltControllerConfig, controller: QuaConfigControllerDec
) -> QuaConfigControllerDec:
    pass


@overload
def _append_data_to_controller(
    data: _SemiBuiltOctoDacConfig, controller: QuaConfigOctoDacFemDec
) -> QuaConfigOctoDacFemDec:
    pass


@overload
def _append_data_to_controller(
    data: _SemiBuiltMwFemConfig, controller: QuaConfigMicrowaveFemDec
) -> QuaConfigMicrowaveFemDec:
    pass


def _append_data_to_controller(data: _SemiBuiltControllerType, controller: ControllerType) -> ControllerType:
    if "analog_outputs" in data:
        for analog_output_name, analog_output in data["analog_outputs"].items():
            if (
                (
                    isinstance(controller, QuaConfigControllerDec)
                    and isinstance(analog_output, QuaConfigAnalogOutputPortDec)
                )
                or (
                    isinstance(controller, QuaConfigOctoDacFemDec)
                    and isinstance(analog_output, QuaConfigOctoDacAnalogOutputPortDec)
                )
                or (
                    isinstance(controller, QuaConfigMicrowaveFemDec)
                    and isinstance(analog_output, QuaConfigMicrowaveAnalogOutputPortDec)
                )
            ):
                controller.analog_outputs[analog_output_name] = analog_output
            else:
                raise ValidationError("Inconsistent types of analog outputs")

    if "analog_inputs" in data:
        for analog_input_name, analog_input in data["analog_inputs"].items():
            if (
                isinstance(controller, (QuaConfigControllerDec, QuaConfigOctoDacFemDec))
                and isinstance(analog_input, QuaConfigAnalogInputPortDec)
            ) or (
                isinstance(controller, QuaConfigMicrowaveFemDec)
                and isinstance(analog_input, QuaConfigMicrowaveAnalogInputPortDec)
            ):
                controller.analog_inputs[analog_input_name] = analog_input
            else:
                raise ValidationError("Inconsistent types of analog inputs")

    if "digital_outputs" in data:
        controller.digital_outputs = data["digital_outputs"]

    if "digital_inputs" in data:
        controller.digital_inputs = data["digital_inputs"]

    return controller


class FemSchema(Schema):
    pass


class OctoDacControllerSchema(FemSchema):
    type = fields.String(description="controller type", validate=validate_string_is_one_of({"LF"}), required=True)
    analog_outputs = fields.Dict(
        fields.Int(),
        fields.Nested(AnalogOutputPortDefSchemaOPX1000),
        description="The analog output ports and their properties.",
    )
    analog_inputs = fields.Dict(
        fields.Int(),
        fields.Nested(AnalogInputPortDefSchema),
        description="The analog input ports and their properties.",
    )
    digital_outputs = fields.Dict(
        fields.Int(),
        fields.Nested(DigitalOutputPortDefSchema),
        description="The digital output ports and their properties.",
    )
    digital_inputs = fields.Dict(
        fields.Int(),
        fields.Nested(DigitalInputPortDefSchema),
        description="The digital inputs ports and their properties.",
    )

    class Meta:
        title = "LF-FEM"
        description = "The specification of a single LF-FEM and its properties."

    @post_load(pass_many=False)
    def build(self, data: _SemiBuiltOctoDacConfig, **kwargs: Any) -> QuaConfigOctoDacFemDec:
        controller = QuaConfigOctoDacFemDec()
        return _append_data_to_controller(data, controller)


class MwFemSchema(FemSchema):
    type = fields.String(
        strict=True,
        description="controller type",
        validate=validate_string_is_one_of({"MW"}),
        required=True,
    )
    analog_outputs = fields.Dict(
        fields.Int(),
        fields.Nested(AnalogOutputPortDefSchemaMwFem),
        description="The analog output ports and their properties.",
    )
    analog_inputs = fields.Dict(
        fields.Int(),
        fields.Nested(AnalogInputPortDefSchemaMwFem),
        description="The analog input ports and their properties.",
    )
    digital_outputs = fields.Dict(
        fields.Int(),
        fields.Nested(DigitalOutputPortDefSchema),
        description="The digital output ports and their properties.",
    )
    digital_inputs = fields.Dict(
        fields.Int(),
        fields.Nested(DigitalInputPortDefSchema),
        description="The digital inputs ports and their properties.",
    )

    class Meta:
        title = "MW-FEM"
        description = "The specification of a single MW-FEM and its properties."

    @post_load(pass_many=False)
    def build(self, data: _SemiBuiltMwFemConfig, **kwargs: Any) -> QuaConfigMicrowaveFemDec:
        controller = QuaConfigMicrowaveFemDec()
        return _append_data_to_controller(data, controller)


class SemiBuiltControllerConfig(TypedDict, total=False):
    type: str
    fems: Dict[int, Union[QuaConfigOctoDacFemDec, QuaConfigControllerDec, QuaConfigMicrowaveFemDec]]
    analog_outputs: Dict[int, QuaConfigAnalogOutputPortDec]
    analog_inputs: Dict[int, QuaConfigAnalogInputPortDec]
    digital_outputs: Dict[int, QuaConfigDigitalOutputPortDec]
    digital_inputs: Dict[int, QuaConfigDigitalInputPortDec]


def _fem_schema_deserialization_disambiguation(
    object_dict: Union[LfFemConfigType, MwFemConfigType], data: Any
) -> FemSchema:
    type_to_schema = {
        "LF": OctoDacControllerSchema,
        "MW": MwFemSchema,
    }
    try:
        return type_to_schema[object_dict["type"].upper()]()
    except KeyError:
        raise ValidationError("Could not detect FEM type, please specify the type you are using (LF or MW).")


_fem_poly_field = PolyField(
    deserialization_schema_selector=_fem_schema_deserialization_disambiguation,
    required=True,
)


class ControllerSchema(Schema):
    type = fields.String(description="controller type")
    analog_outputs = fields.Dict(
        fields.Int(),
        fields.Nested(AnalogOutputPortDefSchema),
        metadata={"description": "The analog output ports and their properties."},
    )
    analog_inputs = fields.Dict(
        fields.Int(),
        fields.Nested(AnalogInputPortDefSchema),
        metadata={"description": "The analog input ports and their properties."},
    )
    digital_outputs = fields.Dict(
        fields.Int(),
        fields.Nested(DigitalOutputPortDefSchema),
        metadata={"description": "The digital output ports and their properties."},
    )
    digital_inputs = fields.Dict(
        fields.Int(),
        fields.Nested(DigitalInputPortDefSchema),
        metadata={"description": "The digital inputs ports and their properties."},
    )
    fems = fields.Dict(
        fields.Int(),
        _fem_poly_field,
        metadata={"description": """The Front-End-Modules (FEMs) in the controller."""},
    )

    class Meta:
        title = "controller"
        description = "The specification of a single controller and its properties."

    @post_load(pass_many=False)
    def build(self, data: SemiBuiltControllerConfig, **kwargs: Any) -> QuaConfigDeviceDec:
        item = QuaConfigDeviceDec()

        if "fems" in data:
            # Here we assume that configuration of the OPX is as before
            if set(data) & {"analog", "analog_outputs", "digital_outputs", "digital_inputs"}:
                raise ValidationError(
                    "'analog', 'analog_outputs', 'digital_outputs' and 'digital_inputs' are not allowed when 'fems' is present"
                )
            else:
                for k, v in data["fems"].items():
                    if isinstance(v, QuaConfigMicrowaveFemDec):
                        item.fems[k] = QuaConfigFemTypes(microwave=v)
                    elif isinstance(v, QuaConfigOctoDacFemDec):
                        item.fems[k] = QuaConfigFemTypes(octo_dac=v)
                    else:
                        for analog_input in v.analog_inputs.values():
                            if analog_input.sampling_rate != 1e9:
                                raise ValidationError(
                                    f"Sampling rate of {analog_input.sampling_rate} is not supported for OPX"
                                )
                        item.fems[k] = QuaConfigFemTypes(opx=v)

        else:
            controller = QuaConfigControllerDec(type=data.get("type", "opx1"))
            item.fems[OPX_FEM_IDX] = QuaConfigFemTypes(opx=_append_data_to_controller(data, controller))
            for analog_input in item.fems[OPX_FEM_IDX].opx.analog_inputs.values():
                if analog_input.sampling_rate != 1e9:
                    raise ValidationError(f"Sampling rate of {analog_input.sampling_rate} is not supported for OPX")

        return item


class DigitalInputSchema(Schema):
    delay = fields.Int(
        metadata={
            "description": "The delay to apply to the digital pulses. In ns. "
            "An intrinsic negative delay exists by default"
        }
    )
    buffer = fields.Int(
        metadata={
            "description": "Digital pulses played to this element will be convolved with a digital "
            "pulse of value 1 with this length [ns]"
        }
    )
    port = PortReferenceSchema

    class Meta:
        title = "Digital input"
        description = "The specification of the digital input of an element"

    @post_load(pass_many=False)
    def build(self, data: DigitalInputConfigType, **kwargs: Any) -> QuaConfigDigitalInputPortReference:
        item = QuaConfigDigitalInputPortReference(delay=data["delay"], buffer=data["buffer"])
        if "port" in data:
            port_ref = _get_port_reference_with_fem(data["port"])
            item.port = QuaConfigPortReference(
                controller=port_ref[0],
                fem=port_ref[1],
                number=port_ref[2],
            )
        return item


class IntegrationWeightSchema(Schema):
    cosine = UnionField(
        [
            fields.List(_create_tuple_field([fields.Float(), fields.Int()])),
            fields.List(fields.Float()),
        ],
        metadata={
            "description": "The integration weights for the cosine. Given as a list of tuples, "
            "each tuple in the format of: ([double] weight, [int] duration). "
            "weight range: [-2048, 2048] in steps of 2**-15. duration is in ns "
            "and must be a multiple of 4."
        },
    )
    sine = UnionField(
        [
            fields.List(_create_tuple_field([fields.Float(), fields.Int()])),
            fields.List(fields.Float()),
        ],
        metadata={
            "description": "The integration weights for the sine. Given as a list of tuples, "
            "each tuple in the format of: ([double] weight, [int] duration). "
            "weight range: [-2048, 2048] in steps of 2**-15. duration is in ns "
            "and must be a multiple of 4."
        },
    )

    class Meta:
        title = "Integration weights"
        description = "The specification of measurements' integration weights."

    @post_load(pass_many=False)
    def build(self, data: IntegrationWeightConfigType, **kwargs: Any) -> QuaConfigIntegrationWeightDec:
        item = QuaConfigIntegrationWeightDec()
        if "cosine" in data:
            item.cosine.extend(build_iw_sample(data["cosine"]))
        if "sine" in data:
            item.sine.extend(build_iw_sample(data["sine"]))
        return item


class WaveformSchema(Schema):
    pass


class ConstantWaveformSchema(WaveformSchema):
    type = fields.String(metadata={"description": '"constant"'}, validate=validate.Equal("constant"))
    sample = fields.Float(
        metadata={"description": "Waveform amplitude"},
        required=True,
    )

    class Meta:
        title = "Constant waveform"
        description = "A waveform with a constant amplitude"

    @post_load(pass_many=False)
    def build(self, data: ConstantWaveformConfigType, **kwargs: Any) -> QuaConfigWaveformDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.waveform_converter.constant_waveform_to_protobuf(data)


class ArbitraryWaveformSchema(WaveformSchema):
    type = fields.String(metadata={"description": '"arbitrary"'}, validate=validate.Equal("arbitrary"))
    samples = fields.List(
        fields.Float(),
        metadata={"description": "list of values of an arbitrary waveforms."},
        required=True,
    )
    max_allowed_error = fields.Float(metadata={"description": '"Maximum allowed error for automatic compression"'})
    sampling_rate = fields.Float(
        metadata={
            "description": "Sampling rate to use in units of S/s (samples per second). "
            "Default is 1e9. Cannot be set when is_overridable=True"
        }
    )
    is_overridable = fields.Bool(
        dump_default=False,
        metadata={
            "description": "Allows overriding the waveform after compilation. "
            "Cannot use with the non-default sampling_rate"
        },
    )

    class Meta:
        title = "Arbitrary waveform"
        description = "The modulating envelope of an arbitrary waveform"

    @post_load(pass_many=False)
    def build(self, data: ArbitraryWaveformConfigType, **kwargs: Any) -> QuaConfigWaveformDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.waveform_converter.arbitrary_waveform_to_protobuf(data)


class WaveformArraySchema(WaveformSchema):
    type = fields.String(metadata={"description": '"array"'}, validate=validate.Equal("array"))
    samples_array = fields.List(
        fields.List(fields.Float()),
        metadata={"description": "Arrays of samples, each samples array contains values of an arbitrary waveform."},
        required=True,
    )

    class Meta:
        title = "Waveform array"
        description = "A waveform which consists of multiple arrays of arbitrary samples"

    @post_load(pass_many=False)
    def build(self, data: WaveformArrayConfigType, **kwargs: Any) -> QuaConfigWaveformDec:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.waveform_converter.waveform_array_to_protobuf(data)


def _waveform_schema_deserialization_disambiguation(
    object_dict: Union[ConstantWaveformConfigType, ArbitraryWaveformConfigType], data: Any
) -> WaveformSchema:
    type_to_schema = {
        "constant": ConstantWaveformSchema,
        "arbitrary": ArbitraryWaveformSchema,
        "array": WaveformArraySchema,
    }
    try:
        return type_to_schema[object_dict["type"]]()
    except KeyError:
        raise ValidationError("Could not detect type. Did not have a base or a length. Are you sure this is a shape?")


_waveform_poly_field = PolyField(
    deserialization_schema_selector=_waveform_schema_deserialization_disambiguation,
    required=True,
)


class DigitalWaveFormSchema(Schema):
    samples = fields.List(
        _create_tuple_field([fields.Int(), fields.Int()]),
        metadata={
            "description": "The digital waveform. Given as a list of tuples, each tuple in the format of: "
            "([int] state, [int] duration). state is either 0 or 1 indicating whether the "
            "digital output is off or on. duration is in ns. If the duration is 0, "
            "it will be played until the reminder of the analog pulse"
        },
        required=True,
    )

    class Meta:
        title = "Digital waveform"
        description = "The samples of a digital waveform"

    @post_load(pass_many=False)
    def build(self, data: DigitalWaveformConfigType, **kwargs: Any) -> QuaConfigDigitalWaveformDec:
        item = QuaConfigDigitalWaveformDec()
        for sample in data["samples"]:
            item.samples.append(QuaConfigDigitalWaveformSample(value=bool(sample[0]), length=int(sample[1])))
        return item


class MixerSchema(Schema):
    intermediate_frequency = fields.Float(
        metadata={"description": "The intermediate frequency associated with the correction matrix"}
    )
    lo_frequency = fields.Float(metadata={"description": "The LO frequency associated with the correction matrix"})
    correction = _create_tuple_field(
        [fields.Float(), fields.Float(), fields.Float(), fields.Float()],
        "A 2x2 matrix entered as a 4 elements list specifying the correction matrix.",
    )

    class Meta:
        title = "Mixer"
        description = (
            "The specification of the correction matrix for an IQ mixer. "
            "This is a list of correction matrices for each LO and IF frequencies."
        )

    @post_load(pass_many=False)
    def build(
        self,
        data: MixerConfigType,
        **kwargs: Any,
    ) -> QuaConfigCorrectionEntry:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.mixer_correction_converter.convert(data)


class PulseSchema(Schema):
    operation = fields.String(
        metadata={"description": "The type of operation. Possible values: 'control', 'measurement'"},
        required=True,
        validate=validate.OneOf(["control", "measurement"]),
    )
    length = fields.Int(
        metadata={"description": "The length of pulse [ns]."},
        required=True,
    )
    waveforms = fields.Dict(
        fields.String(),
        fields.String(metadata={"description": "The name of analog waveform to be played."}),
        metadata={
            "description": "The specification of the analog waveform to be played. "
            "If the associated element has a single input, then the key is 'single'. "
            "If the associated element has 'mixInputs', 'MWInput', or 'RFInput', then the keys are 'I' and 'Q'."
        },
    )
    digital_marker = fields.String(
        metadata={"description": "The name of the digital waveform to be played with this pulse."}
    )
    integration_weights = fields.Dict(
        fields.String(),
        fields.String(
            metadata={
                "description": "The name of the integration weights as it appears under the"
                ' "integration_weights" entry in the configuration.'
            }
        ),
        metadata={"description": "The name of the integration weight to be used in the program."},
    )

    class Meta:
        title = "pulse"
        description = "The specification and properties of a single pulse and to the measurement associated with it."

    @post_load(pass_many=False)
    def build(self, data: PulseConfigType, **kwargs: Any) -> QuaConfigPulseDec:
        item = QuaConfigPulseDec()
        item.length = data["length"]
        if data["operation"] == "measurement":
            item.operation = QuaConfigPulseDecOperation.MEASUREMENT
        elif data["operation"] == "control":
            item.operation = QuaConfigPulseDecOperation.CONTROL
        else:
            raise ConfigValidationException(f"Invalid operation type: {data['operation']}")
        if "integration_weights" in data:
            for k, v in data["integration_weights"].items():
                item.integration_weights[k] = v
        if "waveforms" in data:
            for waveform_key, waveform_name in data["waveforms"].items():
                item.waveforms[waveform_key] = str(waveform_name)
        if "digital_marker" in data:
            item.digital_marker = data["digital_marker"]
        return item


class SingleInputSchema(Schema):
    port = PortReferenceSchema

    class Meta:
        title = "Single input"
        description = "The specification of the input of an element which has a single input port"

    @post_load(pass_many=False)
    def build(self, data: SingleInputConfigType, **kwargs: Any) -> QuaConfigSingleInput:
        controller, fem, number = _get_port_reference_with_fem(data["port"])
        item = QuaConfigSingleInput(port=QuaConfigDacPortReference(controller=controller, fem=fem, number=number))
        return item


class MWInputSchema(Schema):
    port = PortReferenceSchema
    upconverter = fields.Int(
        metadata={"description": "The index of the upconverter to use. Default is 1"},
    )

    class Meta:
        title = "MW input"
        description = "The specification of the input of an element"

    @post_load(pass_many=False)
    def build(self, data: MwInputConfigType, **kwargs: Any) -> QuaConfigMicrowaveInputPortReference:
        controller, fem, number = _get_port_reference_with_fem(data["port"])
        item = QuaConfigMicrowaveInputPortReference(
            port=QuaConfigDacPortReference(controller=controller, fem=fem, number=number),
            upconverter=data.get("upconverter", DEFAULT_DUC_IDX),
        )
        return item


class MWOutputSchema(Schema):
    port = PortReferenceSchema

    class Meta:
        title = "MW output"
        description = "The specification of the input of an element"

    @post_load(pass_many=False)
    def build(self, data: MwInputConfigType, **kwargs: Any) -> QuaConfigMicrowaveOutputPortReference:
        controller, fem, number = _get_port_reference_with_fem(data["port"])
        item = QuaConfigMicrowaveOutputPortReference(
            port=QuaConfigAdcPortReference(controller=controller, fem=fem, number=number),
        )
        return item


class HoldOffsetSchema(Schema):
    duration = fields.Int(metadata={"description": """The ramp to zero duration, in ns"""}, required=True)

    class Meta:
        title = "Hold offset"
        description = "When defined, makes the element sticky"

    @post_load(pass_many=False)
    def build(self, data: HoldOffsetConfigType, **kwargs: Any) -> QuaConfigHoldOffset:
        item = QuaConfigHoldOffset()
        item.duration = data["duration"]
        return item


class StickySchema(Schema):
    analog = fields.Boolean(
        metadata={"description": """Whether the analog part of the pulse is sticky."""}, required=True
    )
    digital = fields.Boolean(metadata={"description": """Whether the digital part of the pulse is sticky."""})
    duration = fields.Int(metadata={"description": """The analog's ramp to zero duration, in ns"""})

    class Meta:
        title = "Sticky"
        description = "When defined, makes the element sticky"

    @post_load(pass_many=False)
    def build(self, data: StickyConfigType, **kwargs: Any) -> QuaConfigSticky:
        item = QuaConfigSticky()
        item.duration = data.get("duration", 4)
        item.analog = data["analog"]
        if "digital" in data:
            item.digital = data["digital"]
        return item


class MixInputSchema(Schema):
    I = PortReferenceSchema
    Q = PortReferenceSchema
    mixer = fields.String(
        metadata={
            "description": "The mixer used to drive the input of the element, "
            "taken from the names in mixers entry in the main configuration."
        }
    )
    lo_frequency = fields.Float(
        metadata={"description": "The frequency of the local oscillator which drives the mixer."}
    )

    class Meta:
        title = "Mixer input"
        description = "The specification of the input of an element which is driven by an IQ mixer"

    @post_load(pass_many=False)
    def build(
        self,
        data: MixInputConfigType,
        **kwargs: Any,
    ) -> QuaConfigMixInputs:
        capabilities = self.context[CAPABILITIES_KEY]
        lo_frequency = data.get("lo_frequency", 0)
        cont_i, fem_i, num_i = _get_port_reference_with_fem(data["I"])
        cont_q, fem_q, num_q = _get_port_reference_with_fem(data["Q"])

        item = QuaConfigMixInputs(
            i=QuaConfigDacPortReference(controller=cont_i, fem=fem_i, number=num_i),
            q=QuaConfigDacPortReference(controller=cont_q, fem=fem_q, number=num_q),
            mixer=data.get("mixer", ""),
            lo_frequency=int(lo_frequency),
        )
        if capabilities.supports_double_frequency:
            item.lo_frequency_double = float(lo_frequency)
        return item


class SingleInputCollectionSchema(Schema):
    inputs = fields.Dict(
        keys=fields.String(),
        values=PortReferenceSchema,
        metadata={"description": "A collection of multiple single inputs to the port"},
        required=True,
    )

    class Meta:
        title = "Single input collection"
        description = "Defines a set of single inputs which can be switched during play statements"

    @post_load(pass_many=False)
    def build(self, data: InputCollectionConfigType, **kwargs: Any) -> QuaConfigSingleInputCollection:
        item = QuaConfigSingleInputCollection()
        for name, reference in data["inputs"].items():
            controller, fem, number = _get_port_reference_with_fem(reference)
            item.inputs[name] = QuaConfigDacPortReference(controller=controller, fem=fem, number=number)
        return item


class MultipleInputsSchema(Schema):
    inputs = fields.Dict(
        keys=fields.String(),
        values=PortReferenceSchema,
        metadata={"description": "A collection of multiple single inputs to the port"},
        required=True,
    )

    class Meta:
        title = "Multiple inputs"
        description = "Defines a set of single inputs which are all played at once"

    @post_load(pass_many=False)
    def build(self, data: InputCollectionConfigType, **kwargs: Any) -> QuaConfigMultipleInputs:
        item = QuaConfigMultipleInputs()
        for name, reference in data["inputs"].items():
            controller, fem, number = _get_port_reference_with_fem(reference)
            item.inputs[name] = QuaConfigDacPortReference(controller=controller, fem=fem, number=number)
        return item


class OscillatorSchema(Schema):
    intermediate_frequency = fields.Float(
        metadata={"description": "The frequency of this oscillator [Hz]."},
        allow_none=True,
    )
    mixer = fields.String(
        metadata={
            "description": "The mixer used to drive the input of the oscillator, "
            "taken from the names in mixers entry in the main configuration"
        }
    )
    lo_frequency = fields.Float(
        metadata={"description": "The frequency of the local oscillator which drives the mixer [Hz]."}
    )

    @post_load(pass_many=False)
    def build(
        self,
        data: OscillatorConfigType,
        **kwargs: Any,
    ) -> QuaConfigOscillator:
        capabilities = self.context[CAPABILITIES_KEY]
        osc = QuaConfigOscillator()
        if "intermediate_frequency" in data and data["intermediate_frequency"] is not None:
            osc.intermediate_frequency = int(data["intermediate_frequency"])
            if capabilities.supports_double_frequency:
                osc.intermediate_frequency_double = float(data["intermediate_frequency"])

        if "mixer" in data and data["mixer"] is not None:
            osc.mixer.mixer = data["mixer"]
            osc.mixer.lo_frequency = int(data.get("lo_frequency", 0))
            if capabilities.supports_double_frequency:
                osc.mixer.lo_frequency_double = float(data.get("lo_frequency", 0.0))

        return osc


polarity_options = ["ABOVE", "ASCENDING", "BELOW", "DESCENDING"]


def _validate_polarity(polarity: str) -> None:
    if polarity.upper() not in polarity_options:
        raise ValidationError(f"Invalid polarity: {polarity}. Must be one of {polarity_options}")


class TimeTaggingParametersSchema(Schema):
    signalThreshold = fields.Int(required=True)
    signalPolarity = fields.String(
        metadata={"description": "The polarity of the signal threshold"},
        validate=_validate_polarity,
        required=True,
    )
    derivativeThreshold = fields.Int(required=True)
    derivativePolarity = fields.String(
        metadata={"description": "The polarity of the derivative threshold"},
        validate=_validate_polarity,
        required=True,
    )

    @post_load(pass_many=False)
    def build(self, data: TimeTaggingParametersConfigType, **kwargs: Any) -> QuaConfigOutputPulseParameters:
        converter: DictToQuaConfigConverter = self.context["converter"]
        return converter.element_converter.create_time_tagging_parameters(data)


class _SemiBuiltElement(TypedDict, total=False):
    intermediate_frequency: float
    oscillator: str
    measurement_qe: str
    operations: Dict[str, str]
    singleInput: QuaConfigSingleInput
    mixInputs: QuaConfigMixInputs
    singleInputCollection: QuaConfigSingleInputCollection
    multipleInputs: QuaConfigMultipleInputs
    MWInput: QuaConfigMicrowaveInputPortReference
    MWOutput: QuaConfigMicrowaveOutputPortReference
    time_of_flight: int
    smearing: int
    outputs: Dict[str, PortReferenceType]
    digitalInputs: Dict[str, QuaConfigDigitalInputPortReference]
    digitalOutputs: Dict[str, PortReferenceType]
    outputPulseParameters: QuaConfigOutputPulseParameters
    timeTaggingParameters: QuaConfigOutputPulseParameters
    hold_offset: QuaConfigHoldOffset
    sticky: QuaConfigSticky
    thread: str
    core: str
    RF_inputs: Dict[str, Tuple[str, int]]
    RF_outputs: Dict[str, Tuple[str, int]]


class ElementSchema(Schema):
    intermediate_frequency = fields.Float(
        metadata={"description": "The frequency at which the controller modulates the output to this element [Hz]."},
        allow_none=True,
    )
    oscillator = fields.String(
        metadata={
            "description": "The oscillator which is used by the controller to modulates the "
            "output to this element [Hz]. Can be used to share oscillators between elements"
        },
        allow_none=True,
    )

    measurement_qe = fields.String(metadata={"description": "not implemented"})
    operations = fields.Dict(
        keys=fields.String(),
        values=fields.String(
            metadata={
                "description": 'The name of the pulse as it appears under the "pulses" entry in the configuration dict'
            }
        ),
        metadata={"description": "A collection of all pulse names to be used in play and measure commands"},
    )
    singleInput = fields.Nested(SingleInputSchema)
    mixInputs = fields.Nested(MixInputSchema)
    singleInputCollection = fields.Nested(SingleInputCollectionSchema)
    multipleInputs = fields.Nested(MultipleInputsSchema)
    MWInput = fields.Nested(MWInputSchema)
    time_of_flight = fields.Int(
        metadata={
            "description": """The delay time, in ns, from the start of pulse until it reaches 
            back into the controller. Needs to be calibrated by looking at the raw ADC data."""
        }
    )
    smearing = fields.Int(
        metadata={
            "description": """Padding time, in ns, to add to both the start and end of the raw 
            ADC data window during a measure command."""
        }
    )
    outputs = fields.Dict(
        keys=fields.String(),
        values=PortReferenceSchema,
        metadata={"description": "The output ports of the element."},
    )
    MWOutput = fields.Nested(MWOutputSchema)
    digitalInputs = fields.Dict(keys=fields.String(), values=fields.Nested(DigitalInputSchema))
    digitalOutputs = fields.Dict(keys=fields.String(), values=PortReferenceSchema)
    outputPulseParameters = fields.Nested(
        TimeTaggingParametersSchema,
        metadata={"description": "Pulse parameters for Time-Tagging (deprecated, use 'timeTaggingParameters' instead)"},
    )
    timeTaggingParameters = fields.Nested(
        TimeTaggingParametersSchema, metadata={"description": "Pulse parameters for Time-Tagging"}
    )

    hold_offset = fields.Nested(HoldOffsetSchema)

    sticky = fields.Nested(StickySchema)

    thread = fields.String(metadata={"description": "Element thread (deprecated, use 'core' instead)"})
    core = fields.String(metadata={"description": "Element core"})
    RF_inputs = fields.Dict(keys=fields.String(), values=_create_tuple_field([fields.String(), fields.Int()]))
    RF_outputs = fields.Dict(keys=fields.String(), values=_create_tuple_field([fields.String(), fields.Int()]))

    class Meta:
        title = "Element"
        description = "The specifications, parameters and connections of a single element."

    @post_load(pass_many=False)
    def build(
        self,
        data: _SemiBuiltElement,
        **kwargs: Any,
    ) -> QuaConfigElementDec:
        capabilities = self.context[CAPABILITIES_KEY]
        el = QuaConfigElementDec()
        if "intermediate_frequency" in data and data["intermediate_frequency"] is not None:
            el.intermediate_frequency = abs(int(data["intermediate_frequency"]))
            el.intermediate_frequency_oscillator = int(data["intermediate_frequency"])
            if capabilities.supports_double_frequency:
                el.intermediate_frequency_double = float(abs(data["intermediate_frequency"]))
                el.intermediate_frequency_oscillator_double = float(data["intermediate_frequency"])

            el.intermediate_frequency_negative = data["intermediate_frequency"] < 0
        elif "oscillator" in data and data["oscillator"] is not None:
            el.named_oscillator = data["oscillator"]
        else:
            el.no_oscillator = Empty()

        # validate we have only 1 set of input defined
        validate_used_inputs(data)

        if "singleInput" in data:
            el.single_input = data["singleInput"]
        if "mixInputs" in data:
            el.mix_inputs = data["mixInputs"]
        if "singleInputCollection" in data:
            el.single_input_collection = data["singleInputCollection"]
        if "multipleInputs" in data:
            el.multiple_inputs = data["multipleInputs"]
        if "MWInput" in data:
            el.microwave_input = data["MWInput"]
        if "MWOutput" in data:
            el.microwave_output = data["MWOutput"]
        if "measurement_qe" in data:
            el.measurement_qe = data["measurement_qe"]
        if "time_of_flight" in data:
            el.time_of_flight = data["time_of_flight"]
        if "smearing" in data:
            el.smearing = data["smearing"]
        if "operations" in data:
            for op_name, operation in data["operations"].items():
                el.operations[op_name] = operation
        if data.get("outputs"):
            el.outputs = _build_port(data["outputs"])
            el.multiple_outputs = QuaConfigMultipleOutputs(port_references=el.outputs)
        if "digitalInputs" in data:
            for digital_input_name, digital_input in data["digitalInputs"].items():
                el.digital_inputs[digital_input_name] = digital_input
        if "digitalOutputs" in data:
            for digital_output_name, digital_output in data["digitalOutputs"].items():
                port_ref = _get_port_reference_with_fem(digital_output)
                el.digital_outputs[digital_output_name] = QuaConfigDigitalOutputPortReference(
                    port=QuaConfigPortReference(controller=port_ref[0], fem=port_ref[1], number=port_ref[2])
                )

        if "outputPulseParameters" in data:
            warnings.warn(
                deprecation_message("outputPulseParameters", "1.2.2", "1.3.0", "Use timeTaggingParameters instead."),
                DeprecationWarning,
            )
            el.output_pulse_parameters = data["outputPulseParameters"]
        if "timeTaggingParameters" in data:
            el.output_pulse_parameters = data["timeTaggingParameters"]
        if "sticky" in data:
            validate_sticky_duration(data["sticky"].duration)
            if capabilities.supports_sticky_elements:
                el.sticky = data["sticky"]
                el.sticky.duration = int(el.sticky.duration / 4)
            else:
                if data["sticky"].digital:
                    raise ConfigValidationException(
                        f"Server does not support digital sticky used in element " f"'{el}'"
                    )
                el.hold_offset = QuaConfigHoldOffset(duration=int(data["sticky"].duration / 4))

        elif "hold_offset" in data:
            if capabilities.supports_sticky_elements:
                el.sticky = QuaConfigSticky(analog=True, digital=False, duration=data["hold_offset"].duration)
            else:
                el.hold_offset = data["hold_offset"]

        if "thread" in data:
            warnings.warn(deprecation_message("thread", "1.2.2", "1.3.0", "Use 'core' instead."), DeprecationWarning)
            el.thread = element_thread_to_pb(data["thread"])
        if "core" in data:
            el.thread = element_thread_to_pb(data["core"])

        rf_inputs = data.get("RF_inputs", {})
        for k, (device, port) in rf_inputs.items():
            el.rf_inputs[k] = QuaConfigGeneralPortReference(device_name=device, port=port)

        rf_outputs = data.get("RF_outputs", {})
        for k, (device, port) in rf_outputs.items():
            el.rf_outputs[k] = QuaConfigGeneralPortReference(device_name=device, port=port)
        return el

    @validates_schema
    def validate_output_tof(self, data: ElementConfigType, **kwargs: Any) -> None:
        validate_output_tof(data)

    @validates_schema
    def validate_output_smearing(self, data: ElementConfigType, **kwargs: Any) -> None:
        validate_output_smearing(data)

    @validates_schema
    def validate_oscillator(self, data: ElementConfigType, **kwargs: Any) -> None:
        validate_oscillator(data)


def _build_port(data: Dict[str, PortReferenceType]) -> Dict[str, QuaConfigAdcPortReference]:
    outputs = {}
    if data is not None:
        for k, port in data.items():
            port_ref = _get_port_reference_with_fem(port)
            outputs[k] = QuaConfigAdcPortReference(controller=port_ref[0], fem=port_ref[1], number=port_ref[2])
    return outputs


class _SemiBuiltQuaConfig(TypedDict, total=False):
    oscillators: Dict[str, QuaConfigOscillator]
    elements: Dict[str, QuaConfigElementDec]
    controllers: Dict[str, QuaConfigDeviceDec]
    octaves: Dict[str, QuaConfigOctaveConfig]
    integration_weights: Dict[str, QuaConfigIntegrationWeightDec]
    waveforms: Dict[str, QuaConfigWaveformDec]
    digital_waveforms: Dict[str, QuaConfigDigitalWaveformDec]
    pulses: Dict[str, QuaConfigPulseDec]
    mixers: Dict[str, Sequence[QuaConfigCorrectionEntry]]


class QuaConfigSchema(Schema):
    version = fields.Int(metadata={"description": "Config version (deprecated, remove it from the Qua config)"})
    oscillators = fields.Dict(
        keys=fields.String(),
        values=fields.Nested(OscillatorSchema),
        metadata={
            "description": """The oscillators used to drive the elements. 
        Can be used to share oscillators between elements"""
        },
    )

    elements = fields.Dict(
        keys=fields.String(),
        values=fields.Nested(ElementSchema),
        metadata={
            "description": """The elements. Each element represents and
         describes a controlled entity which is connected to the ports of the 
         controller."""
        },
    )

    controllers = fields.Dict(
        fields.String(),
        fields.Nested(ControllerSchema),
        metadata={"description": """The controllers. """},
    )

    octaves = fields.Dict(
        fields.String(),
        fields.Nested(OctaveSchema),
        metadata={"description": "The octaves that are in the system, with their interconnected loopbacks."},
    )

    integration_weights = fields.Dict(
        keys=fields.String(),
        values=fields.Nested(IntegrationWeightSchema),
        metadata={
            "description": """The integration weight vectors used in the integration 
        and demodulation of data returning from a element."""
        },
    )

    waveforms = fields.Dict(
        keys=fields.String(),
        values=_waveform_poly_field,
        metadata={
            "description": """The analog waveforms sent to an element when a pulse is 
        played."""
        },
    )
    digital_waveforms = fields.Dict(
        keys=fields.String(),
        values=fields.Nested(DigitalWaveFormSchema),
        metadata={
            "description": """The digital waveforms sent to an element when a pulse is 
        played."""
        },
    )
    pulses = fields.Dict(
        keys=fields.String(),
        values=fields.Nested(PulseSchema),
        metadata={"description": """The pulses to be played to the elements. """},
    )
    mixers = fields.Dict(
        keys=fields.String(),
        values=fields.List(fields.Nested(MixerSchema)),
        metadata={
            "description": """The IQ mixer calibration properties, used to post-shape the pulse
         to compensate for imperfections in the mixers used for up-converting the 
         analog waveforms."""
        },
    )

    class Meta:
        title = "QUA Config"
        description = "QUA program config root object"

    @post_load(pass_many=False)
    def build(
        self,
        data: _SemiBuiltQuaConfig,
        **kwargs: Any,
    ) -> QuaConfig:
        converter: DictToQuaConfigConverter = self.context["converter"]

        converter.run_preload_validations(data, self.context[OCTAVE_ALREADY_CONFIGURED_KEY])  # type: ignore[arg-type]

        pb_config = converter.set_config_wrapper()
        controller_config = get_controller_pb_config(pb_config)
        logical_config = get_logical_pb_config(pb_config)

        if "version" in data:
            warnings.warn(
                deprecation_message("'version'", "1.2.2", "1.3.0", "Please remove it from the Qua config."),
                DeprecationWarning,
            )
        if "elements" in data:
            logical_config.elements = data["elements"]
        if "oscillators" in data:
            logical_config.oscillators = data["oscillators"]
        if "controllers" in data:
            for name, control_device in data["controllers"].items():
                controller_config.control_devices[name] = control_device
            # Controllers attribute is supported only in config v1
            if converter.all_controllers_are_opx(controller_config.control_devices) and isinstance(
                controller_config, QuaConfigQuaConfigV1
            ):
                for name, control_device in controller_config.control_devices.items():
                    controller_config.controllers[name] = control_device.fems[OPX_FEM_IDX].opx
        if "octaves" in data:
            controller_config.octaves = data["octaves"]
        if "integration_weights" in data:
            logical_config.integration_weights = data["integration_weights"]
        if "waveforms" in data:
            logical_config.waveforms = data["waveforms"]
        if "digital_waveforms" in data:
            logical_config.digital_waveforms = data["digital_waveforms"]
        if "mixers" in data:
            for mixer_name, correction_entry in data["mixers"].items():
                controller_config.mixers[mixer_name] = QuaConfigMixerDec(correction=list(correction_entry))
        if "pulses" in data:
            for pulse_name, pulse in data["pulses"].items():
                logical_config.pulses[pulse_name] = pulse

        converter.apply_post_load_setters(pb_config)
        _validate_inputs_or_outputs_exist(pb_config)

        return pb_config


def _validate_inputs_or_outputs_exist(pb_config: QuaConfig) -> None:
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
