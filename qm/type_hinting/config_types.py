from typing import List, Tuple, Union, Literal, Mapping, Optional, Sequence, TypedDict

from qm.type_hinting.general import Number

StandardPort = Tuple[str, int, int]
PortReferenceType = Union[Tuple[str, int], StandardPort]


# TODO: This is a placeholder while we still use dicts, once we move to pydantics we can simply change the
#  inheritance of the classes handled here and add a more robust validation to the types


class AnalogOutputFilterConfigTypeQop35(TypedDict, total=False):
    feedforward: List[float]
    exponential: List[Tuple[float, float]]
    exponential_dc_gain: Optional[float]


class AnalogOutputFilterConfigTypeQop33(TypedDict, total=False):
    feedforward: List[float]
    exponential: List[Tuple[float, float]]
    high_pass: Optional[float]


class AnalogOutputFilterConfigType(TypedDict, total=False):
    feedforward: List[float]
    feedback: List[float]


class AnalogOutputPortConfigType(TypedDict, total=False):
    offset: Number
    filter: Union[AnalogOutputFilterConfigType, AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigTypeQop35]
    delay: int
    crosstalk: Mapping[int, Number]
    shareable: bool


class AnalogInputPortConfigType(TypedDict, total=False):
    offset: Number
    gain_db: int
    shareable: bool
    sampling_rate: float


class DigitalOutputPortConfigType(TypedDict, total=False):
    shareable: bool
    inverted: bool


class DigitalInputPortConfigType(TypedDict, total=False):
    shareable: bool
    deadtime: int
    polarity: Literal["RISING", "FALLING"]
    threshold: Number


class AnalogOutputPortConfigTypeOctoDac(TypedDict, total=False):
    offset: Number
    filter: Union[AnalogOutputFilterConfigType, AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigTypeQop35]
    delay: int
    crosstalk: Mapping[int, Number]
    shareable: bool
    connectivity: Tuple[str, str]
    sampling_rate: float
    upsampling_mode: Literal["mw", "pulse"]
    output_mode: Literal["direct", "amplified"]


class LfFemConfigType(TypedDict, total=False):
    type: Literal["LF"]
    analog_outputs: Mapping[Union[int, str], AnalogOutputPortConfigTypeOctoDac]
    analog_inputs: Mapping[Union[int, str], AnalogInputPortConfigType]
    digital_outputs: Mapping[Union[int, str], DigitalOutputPortConfigType]
    digital_inputs: Mapping[Union[int, str], DigitalInputPortConfigType]


Band = Literal[1, 2, 3]
Upconverter = Literal[1, 2]


class MwFemAnalogInputPortConfigType(TypedDict, total=False):
    sampling_rate: float
    gain_db: int
    shareable: bool
    band: Band
    downconverter_frequency: float


class MwUpconverterConfigType(TypedDict, total=False):
    frequency: float


class MwFemAnalogOutputPortConfigType(TypedDict, total=False):
    sampling_rate: float
    full_scale_power_dbm: int
    band: Band
    delay: int
    shareable: bool
    upconverters: Mapping[Upconverter, MwUpconverterConfigType]
    upconverter_frequency: float


class MwFemConfigType(TypedDict, total=False):
    type: Literal["MW"]
    analog_outputs: Mapping[Union[int, str], MwFemAnalogOutputPortConfigType]
    analog_inputs: Mapping[Union[int, str], MwFemAnalogInputPortConfigType]
    digital_outputs: Mapping[Union[int, str], DigitalOutputPortConfigType]
    digital_inputs: Mapping[Union[int, str], DigitalInputPortConfigType]


class ControllerConfigType(TypedDict, total=False):
    type: Literal["opx", "opx1"]
    analog_outputs: Mapping[Union[int, str], AnalogOutputPortConfigType]
    analog_inputs: Mapping[Union[int, str], AnalogInputPortConfigType]
    digital_outputs: Mapping[Union[int, str], DigitalOutputPortConfigType]
    digital_inputs: Mapping[Union[int, str], DigitalInputPortConfigType]


class OctaveRFOutputConfigType(TypedDict, total=False):
    LO_frequency: float
    LO_source: Literal["internal", "external"]
    output_mode: Literal["always_on", "always_off", "triggered", "triggered_reversed"]
    gain: Union[int, float]
    input_attenuators: Literal["ON", "OFF"]
    I_connection: PortReferenceType
    Q_connection: PortReferenceType


class OctaveRFInputConfigType(TypedDict, total=False):
    RF_source: Literal["RF_in", "loopback_1", "loopback_2", "loopback_3", "loopback_4", "loopback_5"]
    LO_frequency: float
    LO_source: Literal["internal", "external", "analyzer"]
    IF_mode_I: Literal["direct", "mixer", "envelope", "off"]
    IF_mode_Q: Literal["direct", "mixer", "envelope", "off"]


class OctaveSingleIfOutputConfigType(TypedDict, total=False):
    port: PortReferenceType
    name: str


class OctaveIfOutputsConfigType(TypedDict, total=False):
    IF_out1: OctaveSingleIfOutputConfigType
    IF_out2: OctaveSingleIfOutputConfigType


FEM_IDX = Literal[1, 2, 3, 4, 5, 6, 7, 8, "1", "2", "3", "4", "5", "6", "7", "8"]


class OPX1000ControllerConfigType(TypedDict, total=False):
    type: Literal["opx1000"]
    fems: Mapping[FEM_IDX, Union[LfFemConfigType, MwFemConfigType]]


LoopbackType = Tuple[
    Tuple[str, Literal["Synth1", "Synth2", "Synth3", "Synth4", "Synth5"]],
    Literal["Dmd1LO", "Dmd2LO", "LO1", "LO2", "LO3", "LO4", "LO5"],
]


class OctaveConfigType(TypedDict, total=False):
    RF_outputs: Mapping[int, OctaveRFOutputConfigType]
    RF_inputs: Mapping[int, OctaveRFInputConfigType]
    IF_outputs: OctaveIfOutputsConfigType
    loopbacks: List[LoopbackType]
    connectivity: Union[str, Tuple[str, int]]


class DigitalInputConfigType(TypedDict, total=False):
    delay: int
    buffer: int
    port: PortReferenceType


class IntegrationWeightConfigType(TypedDict, total=False):
    cosine: Union[List[Tuple[float, int]], List[float]]
    sine: Union[List[Tuple[float, int]], List[float]]


class ConstantWaveformConfigType(TypedDict, total=False):
    type: Literal["constant"]
    sample: float


class ArbitraryWaveformConfigType(TypedDict, total=False):
    type: Literal["arbitrary"]
    samples: List[float]
    max_allowed_error: float
    sampling_rate: Number
    is_overridable: bool


class WaveformArrayConfigType(TypedDict, total=False):
    type: Literal["array"]
    samples_array: Sequence[Sequence[float]]


class DigitalWaveformConfigType(TypedDict, total=False):
    samples: List[Tuple[int, int]]


class MixerConfigType(TypedDict, total=False):
    intermediate_frequency: float
    lo_frequency: float
    correction: Tuple[Number, Number, Number, Number]


class SingleWaveformConfigType(TypedDict, total=False):
    single: str


class MixWaveformConfigType(TypedDict, total=False):
    I: str
    Q: str


class PulseConfigType(TypedDict, total=False):
    operation: Literal["measurement", "control"]
    length: int
    waveforms: Union[SingleWaveformConfigType, MixWaveformConfigType]
    digital_marker: str
    integration_weights: Mapping[str, str]


class SingleInputConfigType(TypedDict, total=False):
    port: PortReferenceType


class MwInputConfigType(TypedDict, total=False):
    port: PortReferenceType
    upconverter: Upconverter


class MwOutputConfigType(TypedDict, total=False):
    port: PortReferenceType


class HoldOffsetConfigType(TypedDict, total=False):
    duration: int


class StickyConfigType(TypedDict, total=False):
    analog: bool
    digital: bool
    duration: int


class MixInputConfigType(TypedDict, total=False):
    I: PortReferenceType
    Q: PortReferenceType
    mixer: str
    lo_frequency: float


class InputCollectionConfigType(TypedDict, total=False):
    inputs: Mapping[str, PortReferenceType]


class OscillatorConfigType(TypedDict, total=False):
    intermediate_frequency: float
    mixer: str
    lo_frequency: float


class TimeTaggingParametersConfigType(TypedDict, total=False):
    signalThreshold: int
    signalPolarity: Literal["ABOVE", "ASCENDING", "BELOW", "DESCENDING"]
    derivativeThreshold: int
    derivativePolarity: Literal["ABOVE", "ASCENDING", "BELOW", "DESCENDING"]


OutputPulseParameterConfigType = TimeTaggingParametersConfigType


class ElementConfigType(TypedDict, total=False):
    intermediate_frequency: float
    oscillator: str
    measurement_qe: str
    operations: Mapping[str, str]
    singleInput: SingleInputConfigType
    mixInputs: MixInputConfigType
    singleInputCollection: InputCollectionConfigType
    multipleInputs: InputCollectionConfigType
    MWInput: MwInputConfigType
    MWOutput: MwOutputConfigType
    time_of_flight: int
    smearing: int
    outputs: Mapping[str, PortReferenceType]
    digitalInputs: Mapping[str, DigitalInputConfigType]
    digitalOutputs: Mapping[str, PortReferenceType]
    outputPulseParameters: OutputPulseParameterConfigType
    timeTaggingParameters: TimeTaggingParametersConfigType
    hold_offset: HoldOffsetConfigType
    sticky: StickyConfigType
    thread: str
    core: str
    RF_inputs: Mapping[str, Tuple[str, int]]
    RF_outputs: Mapping[str, Tuple[str, int]]


class ControllerQuaConfig(TypedDict, total=False):
    controllers: Mapping[str, Union[ControllerConfigType, OPX1000ControllerConfigType]]
    octaves: Mapping[str, OctaveConfigType]
    mixers: Mapping[str, Sequence[MixerConfigType]]


class LogicalQuaConfig(TypedDict, total=False):
    oscillators: Mapping[str, OscillatorConfigType]
    elements: Mapping[str, ElementConfigType]
    integration_weights: Mapping[str, IntegrationWeightConfigType]
    waveforms: Mapping[str, Union[ArbitraryWaveformConfigType, ConstantWaveformConfigType, WaveformArrayConfigType]]
    digital_waveforms: Mapping[str, DigitalWaveformConfigType]
    pulses: Mapping[str, PulseConfigType]


class FullQuaConfig(TypedDict, total=False):
    """
    The FullQuaConfig type represents the complete QUA configuration.
    The QUA configuration is where we define our 'Quantum Machine' with its elements and their operations.
    """

    oscillators: Mapping[str, OscillatorConfigType]
    elements: Mapping[str, ElementConfigType]
    controllers: Mapping[str, Union[ControllerConfigType, OPX1000ControllerConfigType]]
    octaves: Mapping[str, OctaveConfigType]
    integration_weights: Mapping[str, IntegrationWeightConfigType]
    waveforms: Mapping[str, Union[ArbitraryWaveformConfigType, ConstantWaveformConfigType, WaveformArrayConfigType]]
    digital_waveforms: Mapping[str, DigitalWaveformConfigType]
    pulses: Mapping[str, PulseConfigType]
    mixers: Mapping[str, Sequence[MixerConfigType]]


# The previous name for FullQuaConfig. It is kept for backwards compatibility.
DictQuaConfig = FullQuaConfig
