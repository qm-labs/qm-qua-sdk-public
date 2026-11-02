from collections.abc import Collection

from qm.config._ports import Port
from qm.config._octave import OctaveRfPort
from qm.config._primitives import ConfigObject
from qm.config._elements import Mixer, AnyElement, MixedInput, UpconvertedRfInput


class ControllerConfig(ConfigObject):
    """Physical resources that are not directly attached to an element.

    Models the controller/octave entries from the legacy config that aren't reachable
    through the elements: extra ports, named mixers, and Octave RF ports.
    """

    def __init__(
        self,
        ports: Collection[Port] = (),
        mixers: Collection[Mixer] = (),
        octave_ports: Collection[OctaveRfPort] = (),
    ):
        """
        Args:
            ports: Controller ports declared independently of any element.
            mixers: Mixer corrections (legacy ``mixers`` mapping).
            octave_ports: Octave RF ports declared independently of any element.
        """
        self.ports = ports
        self.mixers = mixers
        self.octave_ports = octave_ports


class LogicalConfig(ConfigObject):
    def __init__(self, elements: Collection[AnyElement]) -> None:
        self.elements = elements


class FullConfigModel(ConfigObject):
    """The QUA program's configuration root, equivalent to the legacy ``QuaConfigSchema``.

    The legacy top-level entries (``oscillators``, ``waveforms``, ``digital_waveforms``,
    ``pulses``, ``integration_weights``, ``controllers``) are not stored here directly --
    they are reached via the ``elements``: each element references its inputs/outputs/ports
    and carries its own pulses (which in turn carry their waveforms and integration
    weights).
    """

    def __init__(
        self,
        logical_config: LogicalConfig,
        additional_controller_config: ControllerConfig | None = None,
    ) -> None:
        """
        Args:
            elements: The elements in the configuration. Each element represents a
                controlled entity which is connected to the ports of the controller.
            additional_controller_config: Physical resources not reachable through
                elements (extra controller ports, named mixers, Octave RF ports).
                If ``None``, an empty ``ControllerConfig`` is created.
        """
        self.logical_config = logical_config
        self.additional_controller_config = (
            additional_controller_config if additional_controller_config is not None else ControllerConfig()
        )

    @property
    def elements(self) -> Collection[AnyElement]:
        return self.logical_config.elements

    def get_controller_config(self, init_mode: bool = True) -> ControllerConfig:
        ports = self._collect_ports()
        mixers = self._collect_mixers(init_mode)
        octave_ports = self._collect_octave_ports()
        return ControllerConfig(ports=ports, mixers=mixers, octave_ports=octave_ports)

    def _collect_ports(self) -> Collection[Port]:
        ports = list(self.additional_controller_config.ports)
        for element in self.elements:
            ports.extend(element.all_ports)
        return ports

    def _collect_mixers(self, init_mode: bool) -> Collection[Mixer]:
        mixers = list(self.additional_controller_config.mixers)
        if not init_mode:
            return mixers
        for element in self.elements:
            if isinstance(element.input, MixedInput) and element.input.mixer is not None:
                # Skip stub mixers that exist only to carry a reference name (see
                # `_compose_element_input` where we create `Mixer({}, name=mixer_name)`
                # for undeclared mixer references so element.mixInputs.mixer stays stable).
                # The ground-truth dict-to-pb path doesn't emit those either.
                if element.input.mixer.lo_if_to_correction:
                    mixers.append(element.input.mixer)
            if element.oscillator is not None and element.oscillator.mixer is not None:
                mixers.append(element.oscillator.mixer)
        return mixers

    def _collect_octave_ports(self) -> Collection[OctaveRfPort]:
        """Collects the ports from the element and from the controller config"""
        octave_ports = list(self.additional_controller_config.octave_ports)
        for element in self.elements:
            if isinstance(element.input, UpconvertedRfInput):
                octave_ports.append(element.input.octave_port)
            if element.output_connected_to_octave is not None:
                octave_ports.append(element.output_connected_to_octave)
        return octave_ports
