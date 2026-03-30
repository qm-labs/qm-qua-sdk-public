from typing import Dict, Union, Optional, MutableMapping, overload

from qm.api.frontend_api import FrontendApi
from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.utils.protobuf_utils import which_one_of
from qm._octaves_container import OctavesContainer
from qm.octave.octave_config import QmOctaveConfig
from qm.utils.config_utils import get_logical_pb_config
from qm.api.models.capabilities import ServerCapabilities
from qm.elements.element import Element, AllElements, NewApiUpconvertedElement
from qm.elements.element_outputs import NoOutput, ElementOutput, DownconvertedOutput
from qm.elements.element_inputs import (
    NoInput,
    MixInputs,
    SingleInput,
    MicrowaveInput,
    MultipleInputs,
    ElementInputGRPCType,
    SingleInputCollection,
)


class ElementNotFound(KeyError):
    def __init__(self, key: str):
        self._key = key

    def __str__(self) -> str:
        return f"Element with the key {self._key} was not found."


class UnknownElementType(ValueError):
    pass


class ElementsDB(Dict[str, AllElements]):
    def __missing__(self, key: str) -> None:
        raise ElementNotFound(key)


def init_elements(
    pb_config: inc_qua_config_pb2.QuaConfig,
    frontend_api: FrontendApi,
    machine_id: str,
    capabilities: ServerCapabilities,
    octave_config: Optional[QmOctaveConfig] = None,
) -> ElementsDB:
    elements = {}
    _octave_container = OctavesContainer(pb_config, capabilities, octave_config)
    logical_config = get_logical_pb_config(pb_config)
    for name, element_config in logical_config.elements.items():
        _, element_inputs = which_one_of(element_config, "element_inputs_one_of")
        input_inst = _get_element_input(
            element_config, element_inputs, name, frontend_api, machine_id, _octave_container
        )

        rf_output = _get_element_rf_output(element_config.RFOutputs, _octave_container)

        elements[name] = Element(
            name=name,
            config=element_config,
            api=frontend_api,
            machine_id=machine_id,
            element_input=input_inst,
            element_output=rf_output,
            set_frequency_as_double=capabilities.supports_double_frequency,
        )
    return ElementsDB(elements)


@overload
def _get_element_input(
    element_config: inc_qua_config_pb2.QuaConfig.ElementDec,
    element_inputs: None,
    name: str,
    frontend_api: FrontendApi,
    machine_id: str,
    octave_container: OctavesContainer,
) -> NoInput:
    pass


@overload
def _get_element_input(
    element_config: inc_qua_config_pb2.QuaConfig.ElementDec,
    element_inputs: inc_qua_config_pb2.QuaConfig.MixInputs,
    name: str,
    frontend_api: FrontendApi,
    machine_id: str,
    octave_container: OctavesContainer,
) -> MixInputs:
    pass


@overload
def _get_element_input(
    element_config: inc_qua_config_pb2.QuaConfig.ElementDec,
    element_inputs: inc_qua_config_pb2.QuaConfig.SingleInput,
    name: str,
    frontend_api: FrontendApi,
    machine_id: str,
    octave_container: OctavesContainer,
) -> SingleInput:
    pass


@overload
def _get_element_input(
    element_config: inc_qua_config_pb2.QuaConfig.ElementDec,
    element_inputs: inc_qua_config_pb2.QuaConfig.MultipleInputs,
    name: str,
    frontend_api: FrontendApi,
    machine_id: str,
    octave_container: OctavesContainer,
) -> MultipleInputs:
    pass


@overload
def _get_element_input(
    element_config: inc_qua_config_pb2.QuaConfig.ElementDec,
    element_inputs: inc_qua_config_pb2.QuaConfig.SingleInputCollection,
    name: str,
    frontend_api: FrontendApi,
    machine_id: str,
    octave_container: OctavesContainer,
) -> SingleInputCollection:
    pass


@overload
def _get_element_input(
    element_config: inc_qua_config_pb2.QuaConfig.ElementDec,
    element_inputs: inc_qua_config_pb2.QuaConfig.MicrowaveInputPortReference,
    name: str,
    frontend_api: FrontendApi,
    machine_id: str,
    octave_container: OctavesContainer,
) -> MicrowaveInput:
    pass


def _get_element_input(
    element_config: inc_qua_config_pb2.QuaConfig.ElementDec,
    element_inputs: ElementInputGRPCType,
    name: str,
    frontend_api: FrontendApi,
    machine_id: str,
    octave_container: OctavesContainer,
) -> Union[NoInput, MixInputs, SingleInput, MultipleInputs, SingleInputCollection, MicrowaveInput]:
    if element_inputs is None:
        return NoInput(name, element_inputs, frontend_api, machine_id)
    if isinstance(element_inputs, inc_qua_config_pb2.QuaConfig.MixInputs):
        return octave_container.create_mix_inputs(element_config, name, frontend_api, machine_id)
    if isinstance(element_inputs, inc_qua_config_pb2.QuaConfig.SingleInput):
        return SingleInput(name, element_inputs, frontend_api, machine_id)
    if isinstance(element_inputs, inc_qua_config_pb2.QuaConfig.MultipleInputs):
        return MultipleInputs(name, element_inputs, frontend_api, machine_id)
    if isinstance(element_inputs, inc_qua_config_pb2.QuaConfig.SingleInputCollection):
        return SingleInputCollection(name, element_inputs, frontend_api, machine_id)
    if isinstance(element_inputs, inc_qua_config_pb2.QuaConfig.MicrowaveInputPortReference):
        return MicrowaveInput(name, element_inputs, frontend_api, machine_id)
    raise UnknownElementType(f"Element {name} is of unknown type - {type(element_inputs)}.")


def _get_element_rf_output(
    rf_outputs: MutableMapping[str, inc_qua_config_pb2.QuaConfig.GeneralPortReference],
    octave_container: OctavesContainer,
) -> ElementOutput:
    downconverter = octave_container.get_downconverter(rf_outputs)
    if downconverter is not None:  # I prefer isinstace, but this allows for easier testing
        return DownconvertedOutput(downconverter)
    return NoOutput()


class UpconvertedElementsDB(Dict[str, NewApiUpconvertedElement]):
    def __missing__(self, key: str) -> None:
        raise ElementNotFound(key)


def init_octave_elements(
    pb_config: inc_qua_config_pb2.QuaConfig,
    capabilities: ServerCapabilities,
    octave_config: Optional[QmOctaveConfig],
) -> UpconvertedElementsDB:
    elements = {}
    _octave_container = OctavesContainer(pb_config, capabilities, octave_config)

    for name, element_config in get_logical_pb_config(pb_config).elements.items():
        _, element_inputs = which_one_of(element_config, "element_inputs_one_of")
        if isinstance(element_inputs, inc_qua_config_pb2.QuaConfig.MixInputs):
            input_inst = _octave_container.create_new_api_upconverted_input(element_config, name)
            if input_inst is not None:
                rf_output = _get_element_rf_output(element_config.RFOutputs, _octave_container)
                elements[name] = NewApiUpconvertedElement(
                    name=name,
                    config=element_config,
                    element_input=input_inst,
                    element_output=rf_output,
                    set_frequency_as_double=capabilities.supports_double_frequency,
                )
    return UpconvertedElementsDB(elements)
