import logging
import os.path
import dataclasses
from copy import deepcopy
from dataclasses import dataclass
from collections import defaultdict
from abc import ABCMeta, abstractmethod
from typing import Any, Dict, List, Type, Union, Mapping, TypeVar, Callable, Optional, Protocol, Sequence, cast

from qm.simulate import SimulatorSamples
from qm.waveform_report._utils import format_float, pretty_string_freq
from qm.waveform_report._type_hints import (
    EventType,
    IqInfoType,
    PortToDucMap,
    ChirpInfoType,
    AdcAcquisitionType,
    PlayedWaveformType,
    PulserLocationType,
    WaveformReportType,
    PlayedAnalogWaveformType,
)

logger = logging.getLogger(__name__)


class HasControllerProtocol(Protocol):
    @property
    def controller(self) -> str:
        raise NotImplementedError

    @property
    def fem(self) -> int:
        raise NotImplementedError

    @property
    def element(self) -> str:
        raise NotImplementedError


T = TypeVar("T", bound="PlayedWaveform")


@dataclass(frozen=True)
class PlayedWaveform(metaclass=ABCMeta):
    waveform_name: str
    pulse_name: str
    length: int
    timestamp: int
    iq_info: IqInfoType
    element: str
    output_ports: List[int]
    controller: str
    pulser: Dict[str, Any]
    fem: int

    @staticmethod
    def build_initialization_dict(
        dict_description: PlayedWaveformType, formatted_attribute_dict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        attribute_dict: Dict[str, Any]
        if formatted_attribute_dict is None:
            attribute_dict = {}
        else:
            attribute_dict = deepcopy(formatted_attribute_dict)

        attribute_dict.update(
            pulse_name=dict_description["pulseName"],
            waveform_name=dict_description["waveformName"],
            timestamp=int(dict_description["timestamp"]),
            length=int(dict_description["length"]),
            iq_info=dict_description["iqInfo"],
            element=dict_description["quantumElements"],
            output_ports=[int(p) for p in dict_description["outputPorts"]],
            pulser=dict_description["pulser"],
            controller=dict_description["pulser"]["controllerName"],
            fem=int(dict_description["pulser"].get("femId", 0)) + 1,
        )
        return attribute_dict

    @classmethod
    def from_job_dict(cls: Type[T], dict_description: PlayedWaveformType) -> T:
        return cls(**cls.build_initialization_dict(dict_description))

    @property
    def ports(self) -> List[str]:
        return [str(p) for p in self.output_ports]

    @property
    def is_iq(self) -> bool:
        return self.iq_info["isPartOfIq"]

    @property
    def is_I_pulse(self) -> bool:
        return self.iq_info["isI"]

    @property
    def get_iq_association(self) -> str:
        if not self.is_iq:
            return ""
        return "I" if self.is_I_pulse else "Q"

    @property
    def ends_at(self) -> int:
        return self.timestamp + self.length

    @abstractmethod
    def to_string(self) -> str:
        return ""

    def __str__(self) -> str:
        return self.to_string()

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    def _common_attributes_to_printable_str_list(self) -> List[str]:
        waveform_type_string = "Type="
        if self.is_iq:
            waveform_type_string += f"IQ Type ({'I' if self.iq_info['isI'] else 'Q'})"
        else:
            waveform_type_string += "Single"
        return [
            f"Waveform Name={self.waveform_name}",
            f"Pulse name={self.pulse_name.removeprefix('OriginPulseName=')}",
            f"Start Time={self.timestamp} ns",
            f"Length={self.length} ns",
            f"Element={self.element}",
            f"Output Ports={self.ports}",
            waveform_type_string,
        ]


@dataclass(frozen=True)
class PlayedAnalogWaveform(PlayedWaveform):
    current_amp_elements: List[float]
    current_dc_offset_by_port: Dict[str, float]
    current_intermediate_frequency: float
    current_frame: List[float]
    current_correction_elements: List[float]
    chirp_info: Optional[ChirpInfoType]
    current_phase: float

    @classmethod
    def from_job_dict(cls, dict_description: PlayedWaveformType) -> "PlayedAnalogWaveform":
        dict_description = cast(PlayedAnalogWaveformType, dict_description)
        pulse_chirp_info = dict_description["chirpInfo"]
        is_pulse_have_chirp = len(pulse_chirp_info["units"]) > 0 or len(pulse_chirp_info["rate"]) > 0
        formatted_attribute_list = dict(
            current_amp_elements=dict_description["currentGMatrixElements"],
            current_dc_offset_by_port=dict_description["currentDCOffsetByPort"],
            current_intermediate_frequency=dict_description["currentIntermediateFrequency"],
            current_frame=dict_description["currentFrame"],
            current_correction_elements=dict_description["currentCorrectionElements"],
            chirp_info=pulse_chirp_info if is_pulse_have_chirp else None,
            current_phase=dict_description.get("currentPhase", 0),
        )
        if dict_description.get("portToDuc") and any(d["ducs"] for d in dict_description["portToDuc"]):
            formatted_attribute_list["port_to_duc"] = PlayedMwAnalogWaveform.create_port_to_duc_mapping(
                dict_description["portToDuc"]
            )
            class_to_init: Type[PlayedAnalogWaveform] = PlayedMwAnalogWaveform
        else:
            class_to_init = PlayedAnalogWaveform
        initialization_dict = class_to_init.build_initialization_dict(dict_description, formatted_attribute_list)
        return class_to_init(**initialization_dict)

    def to_custom_string(self, show_chirp: bool = True) -> str:
        _attributes = super()._common_attributes_to_printable_str_list()
        _attributes += (
            [
                f"{k}={v if self.is_iq else v[0]}"
                for k, v in [
                    ("Amplitude Values", [format_float(f) for f in self.current_amp_elements]),
                    ("Frame Values", [format_float(f) for f in self.current_frame]),
                    ("Correction Values", [format_float(f) for f in self.current_correction_elements]),
                ]
            ]
            + [
                f"Intermediate Frequency={pretty_string_freq(self.current_intermediate_frequency)}",
                f"Current DC Offset (By output ports)={ {k: format_float(v) for k, v in self.current_dc_offset_by_port.items()} }",
                f"Current Phase={format_float(self.current_phase)},",
            ]
            + ([] if (self.chirp_info is None or not show_chirp) else [f"chirp_info={self.chirp_info}"])
        )
        s = "AnalogWaveform(" + ("\n" + len("AnalogWaveform(") * " ").join(_attributes) + ")"
        return s

    def to_string(self) -> str:
        return self.to_custom_string()


def _fix_duc_idx(duc_idx: int) -> int:
    """This one is to overcome the returned 3 and 4 from the GW, when it's fixed, this one can be removed"""
    return (duc_idx - 1) % 2 + 1


@dataclass(frozen=True)
class PlayedMwAnalogWaveform(PlayedAnalogWaveform):
    port_to_duc: Dict[int, List[int]]

    @staticmethod
    def create_port_to_duc_mapping(port_to_duc: List[PortToDucMap]) -> Dict[int, List[int]]:
        return {int(p["port"]): [_fix_duc_idx(int(d)) for d in p["ducs"]] for p in port_to_duc}

    @property
    def ports(self) -> List[str]:
        to_return = []
        for port in self.output_ports:
            if port in self.port_to_duc:
                assert (
                    len(self.port_to_duc[port]) == 1
                ), f"Number of DUCs per port must equal 1, got {len(self.port_to_duc[port])}"
                to_return.append(f"{port}-{self.port_to_duc[port][0]}")
            else:
                to_return.append(str(port))
        return to_return


@dataclass(frozen=True)
class PlayedDigitalWaveform(PlayedWaveform):
    @classmethod
    def from_job_dict(cls: Type[T], dict_description: PlayedWaveformType) -> T:
        return cls(**cls.build_initialization_dict(dict_description))

    def to_string(self) -> str:
        s = (
            "DigitalWaveform("
            + ("\n" + len("DigitalWaveform(") * " ").join(self._common_attributes_to_printable_str_list())
            + ")"
        )
        return s


@dataclass(frozen=True)
class AdcAcquisition:
    start_time: int
    end_time: int
    process: str
    pulser: PulserLocationType
    quantum_element: str
    adc_ports: List[int]
    controller: str
    fem: int
    element: str

    @classmethod
    def from_job_dict(cls, dict_description: AdcAcquisitionType) -> "AdcAcquisition":
        return cls(
            start_time=int(dict_description["startTime"]),
            end_time=int(dict_description["endTime"]),
            process=dict_description["process"],
            pulser=dict_description["pulser"],
            quantum_element=dict_description["quantumElement"],
            adc_ports=[int(p) + 1 for p in dict_description["adc"]],
            controller=dict_description["pulser"]["controllerName"],
            fem=int(dict_description["pulser"].get("femId", 0)) + 1,
            element=dict_description["quantumElement"],
        )

    @property
    def ports(self) -> List[str]:
        return [str(p) for p in self.adc_ports]

    def to_string(self) -> str:
        return (
            "AdcAcquisition("
            + ("\n" + len("AdcAcquisition(") * " ").join(
                [
                    f"start_time={self.start_time}",
                    f"end_time={self.end_time}",
                    f"process={self.process}",
                    f"element={self.quantum_element}",
                    f"input_ports={self.adc_ports}",
                ]
            )
            + ")"
        )

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class Event:
    name: str
    timestamp: int
    controller: str
    fem: int
    element: str
    is_i: bool
    is_q: bool

    @staticmethod
    def is_supported(dict_description: EventType) -> bool:
        supported_events_list = ["phase_reset"]
        event_message = dict_description["eventMessage"]
        ret = event_message in supported_events_list
        if not ret:
            logger.debug(
                f"Event message {event_message} not supported in supported events list: {supported_events_list}"
            )
        return ret

    @classmethod
    def from_job_dict(cls, dict_description: EventType) -> "Event":
        return cls(
            name=dict_description["eventMessage"],
            timestamp=int(dict_description["timestamp"]),
            controller=dict_description["sourcePulser"]["controllerName"],
            fem=int(dict_description["sourcePulser"].get("femId", 0)) + 1,
            element=dict_description["quantumElement"],
            is_i=dict_description["sourcePulserIqInfo"]["isI"],
            is_q=dict_description["sourcePulserIqInfo"]["isQ"],
        )

    def to_string(self) -> str:
        """Prints all fields of the event in the standard readable format."""
        indent = " " * len("Event(")
        body = ("\n" + indent).join(f"{f.name}={getattr(self, f.name)}" for f in dataclasses.fields(self))
        return f"Event({body})"

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class FemToWaveformMap:
    analog_out: Dict[str, List[PlayedAnalogWaveform]]
    digital_out: Dict[str, List[PlayedDigitalWaveform]]
    analog_in: Dict[str, List[AdcAcquisition]]


class _SingleControllerMapping(Dict[int, FemToWaveformMap]):
    @property
    def num_analog_out_ports(self) -> int:
        return len(self.flat_analog_out)

    @property
    def num_digital_out_ports(self) -> int:
        return len(self.flat_digital_out)

    @property
    def num_analog_in_ports(self) -> int:
        return len(self.flat_analog_in)

    @property
    def flat_analog_out(self) -> Dict[str, List[PlayedAnalogWaveform]]:
        return {f"{fem_idx}-{port_idx}": v for fem_idx, fem in self.items() for port_idx, v in fem.analog_out.items()}

    @property
    def flat_digital_out(self) -> Dict[str, List[PlayedDigitalWaveform]]:
        return {f"{fem_idx}-{port_idx}": v for fem_idx, fem in self.items() for port_idx, v in fem.digital_out.items()}

    @property
    def flat_analog_in(self) -> Dict[str, List[AdcAcquisition]]:
        return {f"{fem_idx}-{port_idx}": v for fem_idx, fem in self.items() for port_idx, v in fem.analog_in.items()}


@dataclass(frozen=True)
class WaveformReport:
    job_id: Union[int, str]
    analog_waveforms: List[PlayedAnalogWaveform]
    digital_waveforms: List[PlayedDigitalWaveform]
    adc_acquisitions: List[AdcAcquisition]
    events: List[Event]

    @classmethod
    def from_dict(cls, d: WaveformReportType, job_id: Union[int, str] = -1) -> "WaveformReport":
        return cls(
            analog_waveforms=[PlayedAnalogWaveform.from_job_dict(awf) for awf in d["analogWaveforms"]],
            digital_waveforms=[PlayedDigitalWaveform.from_job_dict(dwf) for dwf in d["digitalWaveforms"]],
            adc_acquisitions=[AdcAcquisition.from_job_dict(acq) for acq in d.get("adcAcquisitions", [])],
            events=[Event.from_job_dict(event) for event in d.get("events", []) if Event.is_supported(event)],
            job_id=job_id,
        )

    @property
    def waveforms(self) -> Sequence[PlayedWaveform]:
        return cast(List[PlayedWaveform], self.analog_waveforms) + cast(List[PlayedWaveform], self.digital_waveforms)

    @property
    def controllers_in_use(self) -> Sequence[str]:
        return sorted(self.fems_in_use_by_controller)

    @property
    def num_controllers_in_use(self) -> int:
        return len(self.controllers_in_use)

    @property
    def elements_in_report(self) -> Sequence[str]:
        wf_elements = {wf.element for wf in self.waveforms}
        adc_elements = {adc.element for adc in self.adc_acquisitions}
        event_elements = {event.element for event in self.events}
        return sorted(wf_elements | adc_elements | event_elements)

    @property
    def fems_in_use_by_controller(self) -> Mapping[str, Sequence[int]]:
        fems_in_use = defaultdict(set)
        for ap in self.waveforms:
            fems_in_use[ap.controller].add(ap.fem)
        for adc in self.adc_acquisitions:
            fems_in_use[adc.controller].add(adc.fem)
        for event in self.events:
            fems_in_use[event.controller].add(event.fem)
        return {k: sorted(v) for k, v in fems_in_use.items()}

    def to_string(self) -> str:
        """
        Dumps the report into a (pretty-print) string.

        return: str
        """
        waveforms_str = [wf.to_string() for wf in self.waveforms]
        adc_string = [adc.to_string() for adc in self.adc_acquisitions]
        events_str = [event.to_string() for event in self.events]
        return "\n".join(waveforms_str + adc_string + events_str)

    def _transform_report_by_func(self, func: Callable[[HasControllerProtocol], bool]) -> "WaveformReport":
        return WaveformReport(
            analog_waveforms=list(filter(func, self.analog_waveforms)),
            digital_waveforms=list(filter(func, self.digital_waveforms)),
            adc_acquisitions=list(filter(func, self.adc_acquisitions)),
            events=list(filter(func, self.events)),
            job_id=self.job_id,
        )

    def report_by_controllers(self) -> Mapping[str, "WaveformReport"]:
        def create_filter_func(controller: str) -> Callable[[HasControllerProtocol], bool]:
            return lambda r: r.controller == controller

        by_controller_map: Dict[str, "WaveformReport"] = {}
        for con_name in self.controllers_in_use:
            con_filter = create_filter_func(con_name)
            by_controller_map[con_name] = self._transform_report_by_func(con_filter)

        return by_controller_map

    def report_by_elements(self) -> Mapping[str, "WaveformReport"]:
        def create_filter_func(_element: str) -> Callable[[HasControllerProtocol], bool]:
            return lambda r: r.element == _element

        by_element_map: Dict[str, "WaveformReport"] = {}
        for element in self.elements_in_report:
            element_filter = create_filter_func(element)
            by_element_map[element] = self._transform_report_by_func(element_filter)

        return by_element_map

    def report_by_controller_and_fems(self) -> Mapping[str, Mapping[int, "WaveformReport"]]:
        def create_filter_func(controller: str, _fem: int) -> Callable[[HasControllerProtocol], bool]:
            return lambda r: r.controller == controller and r.fem == _fem

        by_controller_fem_map: Dict[str, Dict[int, "WaveformReport"]] = {}
        for con_name in self.controllers_in_use:
            by_controller_fem_map[con_name] = {}
            for fem in self.fems_in_use_by_controller[con_name]:
                fem_filter = create_filter_func(con_name, fem)
                by_controller_fem_map[con_name][fem] = self._transform_report_by_func(fem_filter)

        return by_controller_fem_map

    def to_dict(self) -> Dict[str, Any]:
        """
        Dumps the report to a dictionary containing three keys:
            "analog_waveforms", "digital_waveforms", "acd_acquisitions".
        Each key holds the list of all the associate data.

        Returns:
            dict
        """
        return {
            "analog_waveforms": [awf.to_dict() for awf in self.analog_waveforms],
            "digital_waveforms": [dwf.to_dict() for dwf in self.digital_waveforms],
            "adc_acquisitions": [acq.to_dict() for acq in self.adc_acquisitions],
            "events": [event.to_dict() for event in self.events],
        }

    def _strict_get_report_by_output_ports(self) -> Mapping[str, _SingleControllerMapping]:
        report_by_controller_and_fem = self.report_by_controller_and_fems()
        result = {}
        for controller, fem_to_report_map in report_by_controller_and_fem.items():
            per_controller = {}
            for fem, report in fem_to_report_map.items():
                analog_out, digital_out, analog_in = defaultdict(list), defaultdict(list), defaultdict(list)
                for awf in report.analog_waveforms:
                    for p in awf.ports:
                        analog_out[p].append(awf)
                for dwf in report.digital_waveforms:
                    for p in dwf.ports:
                        digital_out[p].append(dwf)
                for adc in report.adc_acquisitions:
                    for p in adc.ports:
                        analog_in[p].append(adc)
                per_controller[fem] = FemToWaveformMap(
                    analog_out=dict(analog_out), digital_out=dict(digital_out), analog_in=dict(analog_in)
                )
            result[controller] = _SingleControllerMapping(per_controller)
        return result

    def get_report_by_output_ports(
        self, on_controller: Optional[str] = None
    ) -> Union[Mapping[str, _SingleControllerMapping], _SingleControllerMapping]:
        result = self._strict_get_report_by_output_ports()
        if on_controller is None:
            if self.num_controllers_in_use == 1:
                return result[self.controllers_in_use[0]]
            else:
                return result
        else:
            return result[on_controller]

    def create_plot(
        self,
        samples: Optional[SimulatorSamples] = None,
        controllers: Optional[Sequence[str]] = None,
        plot: bool = True,
        save_path: Optional[str] = None,
    ) -> None:
        """Creates a plot describing the pulses from each element to each port.
        See arguments description for further options.

        Args:
            samples: The raw samples as generated from the simulator. If not given, the plot will be generated without it.
            controllers: list of controllers to generate the plot. Each controller output will be saved as a different
                        file. If not given, take all the controllers who participate in the program.
            plot: Show the plot at the end of this function call.
            save_path: Save the plot to the given location. None for not saving.

        Returns:
            None
        """
        if controllers is None:
            controllers = self.controllers_in_use

        report_by_controllers = self.report_by_controllers()
        for con_name, report in report_by_controllers.items():
            if con_name not in controllers:
                continue

            if samples is None:
                from qm.waveform_report._waveform_plot_builder import _WaveformPlotBuilder

                con_builder = _WaveformPlotBuilder(report, self.job_id)
            else:
                from qm.waveform_report._waveform_plot_builder import _WaveformPlotBuilderWithSamples

                con_builder = _WaveformPlotBuilderWithSamples(report, samples[con_name], self.job_id)

            if save_path is not None:
                dirname = os.path.dirname(save_path)
                filename = f"waveform_report_{con_name}_{self.job_id}"
                con_builder.save(dirname, filename)
            if plot:
                con_builder.plot()
