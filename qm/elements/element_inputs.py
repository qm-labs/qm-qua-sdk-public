import logging
from typing import Tuple, Generic, TypeVar, Optional, Sequence

import numpy
from dependency_injector.wiring import Provide, inject

from qm.api.frontend_api import FrontendApi
from qm.grpc.general_messages import Matrix
from qm.api.models.capabilities import ServerCapabilities
from qm.api.models.devices import MixerInfo, AnalogOutputPortFilter
from qm.containers.capabilities_container import CapabilitiesContainer
from qm.type_hinting.general import NumpySupportedFloat, NumpySupportedNumber
from qm.grpc.qua_config import (
    QuaConfigMixInputs,
    QuaConfigSingleInput,
    QuaConfigMultipleInputs,
    QuaConfigDacPortReference,
    QuaConfigSingleInputCollection,
    QuaConfigMicrowaveInputPortReference,
)

logger = logging.getLogger(__name__)


def _set_single_output_port_dc_offset(
    frontend_api: FrontendApi,
    machine_id: str,
    element_name: str,
    input_name: str,
    offset: NumpySupportedNumber,
) -> None:
    offset = float(offset)
    logger.debug(f"Setting DC offset of input '{input_name}' on element '{element_name}' to '{offset}'")
    frontend_api.set_output_dc_offset(machine_id, element_name, input_name, offset)


def _create_taps_filter(
    feedforward: Optional[Sequence[NumpySupportedFloat]], feedback: Optional[Sequence[NumpySupportedFloat]]
) -> AnalogOutputPortFilter:
    feedforward = [] if feedforward is None else feedforward
    feedback = [] if feedback is None else feedback

    for name, instance in zip(["feedforward", "feedback"], [feedforward, feedback]):
        if not isinstance(instance, (numpy.ndarray, list)):
            raise TypeError(f"{name} must be a list, or a numpy array. Got {type(instance)}.")
    return AnalogOutputPortFilter(feedforward=[float(x) for x in feedforward], feedback=[float(x) for x in feedback])


@inject
def static_set_mixer_correction(
    frontend_api: FrontendApi,
    machine_id: str,
    mixer: str,
    intermediate_frequency: NumpySupportedNumber,
    lo_frequency: NumpySupportedNumber,
    values: Tuple[NumpySupportedFloat, NumpySupportedFloat, NumpySupportedFloat, NumpySupportedFloat],
    capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities],
) -> None:
    # TODO - this function is here (and not under MixedInputsElement) to support backwards the direct calling to mixer
    #  Once it is changed, one can put this function under the element

    if not isinstance(values, (tuple, list)) or len(values) != 4:
        raise Exception("correction values must have 4 items")

    float_values = [float(x) for x in values]
    if not all((-2 < x <= (2 - 2 ** (-16))) for x in float_values):
        logger.warning(
            "At least one of the correction values are out of range. "
            f"values should be between -2 and 2 - 2 ** (-16), got {float_values}. "
            f"Not setting the correction matrix."
        )
        return
    correction_matrix = Matrix(*float_values)

    mixer_lo_frequency_double = 0.0
    mixer_intermediate_frequency_double = 0.0
    if capabilities.supports_double_frequency:
        mixer_lo_frequency_double = float(lo_frequency)
        mixer_intermediate_frequency_double = abs(float(intermediate_frequency))

    mixer_info = MixerInfo(
        mixer=mixer,
        frequency_negative=bool(intermediate_frequency < 0),
        lo_frequency=int(lo_frequency),
        intermediate_frequency=abs(int(intermediate_frequency)),
        lo_frequency_double=mixer_lo_frequency_double,
        intermediate_frequency_double=mixer_intermediate_frequency_double,
    )
    frontend_api.set_correction(machine_id, mixer_info, correction_matrix)


ElementInputGRPCType = TypeVar(
    "ElementInputGRPCType",
    QuaConfigSingleInput,
    QuaConfigMixInputs,
    QuaConfigSingleInputCollection,
    QuaConfigMultipleInputs,
    QuaConfigMicrowaveInputPortReference,
    None,
)


class ElementInput(Generic[ElementInputGRPCType]):
    def __init__(self, name: str, config: ElementInputGRPCType, frontend_api: FrontendApi, machine_id: str):
        self._name = name
        self._config: ElementInputGRPCType = config
        self._frontend = frontend_api
        self._id = machine_id


class NoInput(ElementInput[None]):
    pass


class MicrowaveInput(ElementInput[QuaConfigMicrowaveInputPortReference]):
    pass


class SingleInput(ElementInput[QuaConfigSingleInput]):
    @property
    def port(self) -> QuaConfigDacPortReference:
        return self._config.port

    def set_output_dc_offset(self, offset: float) -> None:
        _set_single_output_port_dc_offset(self._frontend, self._id, self._name, "single", offset)

    def set_output_filter(
        self,
        feedforward: Optional[Sequence[NumpySupportedFloat]],
        feedback: Optional[Sequence[NumpySupportedFloat]],
    ) -> None:
        analog_filter = _create_taps_filter(feedforward, feedback)
        self._frontend.set_output_filter_taps(self._id, self._name, "single", analog_filter)


class MultipleInputs(ElementInput[QuaConfigMultipleInputs]):
    pass


class SingleInputCollection(ElementInput[QuaConfigSingleInputCollection]):
    pass


class MixInputs(ElementInput[QuaConfigMixInputs]):
    @property
    def i_port(self) -> QuaConfigDacPortReference:
        return self._config.i

    @property
    def q_port(self) -> QuaConfigDacPortReference:
        return self._config.q

    @property
    @inject
    def lo_frequency(self, capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities]) -> float:
        if capabilities.supports_double_frequency:
            return self._config.lo_frequency_double
        return self._config.lo_frequency

    def set_lo_frequency(self, value: float) -> None:
        self._set_config_lo_frequency(value)

    @inject
    def _set_config_lo_frequency(
        self, value: float, capabilities: ServerCapabilities = Provide[CapabilitiesContainer.capabilities]
    ) -> None:
        freq = float(value)
        logger.debug(f"Setting element '{self._name}' LO frequency to '{freq}'.")
        self._config.lo_frequency = int(freq)
        self._config.lo_frequency_double = 0.0
        if capabilities.supports_double_frequency:
            self._config.lo_frequency_double = float(freq)

    @property
    def mixer(self) -> str:
        return self._config.mixer

    def set_output_dc_offset(self, i_offset: Optional[float] = None, q_offset: Optional[float] = None) -> None:
        if i_offset is not None:
            _set_single_output_port_dc_offset(self._frontend, self._id, self._name, "I", i_offset)
        if q_offset is not None:
            _set_single_output_port_dc_offset(self._frontend, self._id, self._name, "Q", q_offset)

    def set_output_filter(
        self,
        input_name: str,
        feedforward: Optional[Sequence[NumpySupportedFloat]],
        feedback: Optional[Sequence[NumpySupportedFloat]],
    ) -> None:
        analog_filter = _create_taps_filter(feedforward, feedback)
        self._frontend.set_output_filter_taps(
            self._id,
            self._name,
            input_name,
            analog_filter,
        )

    def set_mixer_correction(
        self,
        intermediate_frequency: NumpySupportedNumber,
        lo_frequency: NumpySupportedNumber,
        values: Tuple[NumpySupportedFloat, NumpySupportedFloat, NumpySupportedFloat, NumpySupportedFloat],
    ) -> None:
        static_set_mixer_correction(
            self._frontend,
            self._id,
            mixer=self.mixer,
            intermediate_frequency=intermediate_frequency,
            lo_frequency=lo_frequency,
            values=values,
        )
