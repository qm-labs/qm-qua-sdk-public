from typing import Any, Set, Dict, List, Optional, TypedDict


class PulserLocationType(TypedDict, total=False):
    controllerName: str
    pulserIndex: float
    femId: float


class IqInfoType(TypedDict, total=False):
    isPartOfIq: bool
    iqGroupId: float
    isI: bool
    isQ: bool


class ChirpInfoType(TypedDict, total=False):
    rate: List[int]
    times: List[int]
    units: str
    startFrequency: float
    endFrequency: float


class PlayedWaveformType(TypedDict, total=False):
    waveformName: str
    pulseName: str
    pulser: PulserLocationType
    iqInfo: IqInfoType
    timestamp: int
    length: int
    endsAt: int
    outputPorts: Set[int]
    quantumElements: str


class PortToDucMap(TypedDict):
    port: float
    ducs: List[float]


class EventLocationDescriptor(TypedDict, total=False):
    index: float
    location: str


class PlayedAnalogWaveformType(PlayedWaveformType, total=False):
    currentFrame: List[float]
    currentCorrectionElements: List[float]
    currentIntermediateFrequency: float
    currentGMatrixElements: List[float]
    currentDCOffsetByPort: Dict[int, float]
    currentPhase: float
    chirpInfo: ChirpInfoType
    portToDuc: List[PortToDucMap]


class AdcAcquisitionType(TypedDict, total=False):
    startTime: int
    endTime: int
    process: str
    pulser: PulserLocationType
    quantumElement: str
    adc: List[int]


class EventType(TypedDict, total=False):
    eventLatency: float
    eventLocationDescriptor: EventLocationDescriptor
    eventMessage: str
    eventValues: List[
        Any
    ]  # Type is unclear—only encountered empty lists so far, so couldn't determine the actual contents
    quantumElement: str
    sourcePulser: PulserLocationType
    sourcePulserIqInfo: IqInfoType
    timestamp: float


class WaveformReportType(TypedDict, total=False):
    analogWaveforms: List[PlayedAnalogWaveformType]
    digitalWaveforms: List[PlayedWaveformType]
    adcAcquisitions: List[AdcAcquisitionType]
    events: List[EventType]


class WaveformPlayingType(TypedDict, total=False):
    name: str
    timestamp: int
    duration: int
    frequency: float
    phase: float


class WaveformInControllerType(TypedDict):
    ports: Dict[int, List[WaveformPlayingType]]


class WaveformInPortsType(TypedDict):
    controllers: Dict[str, WaveformInControllerType]
    elements: Dict[str, WaveformPlayingType]


class AnalogOutputsType(TypedDict):
    waveforms: Optional[WaveformInPortsType]


class DigitalOutputsType(TypedDict):
    waveforms: Optional[WaveformInPortsType]
