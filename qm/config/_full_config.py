from typing import Any
from collections.abc import Collection

from qm.config._ports import Port
from qm.config._octave import OctaveRfPort
from qm.config._elements import Mixer, Element
from qm.config._primitives import ConfigObject


class PhysicalConfig(ConfigObject):
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
        elements: Collection[Element[Any]],
        additional_physical_config: PhysicalConfig | None = None,
    ) -> None:
        """
        Args:
            elements: The elements in the configuration. Each element represents a
                controlled entity which is connected to the ports of the controller.
            additional_physical_config: Physical resources not reachable through
                elements (extra controller ports, named mixers, Octave RF ports).
                If ``None``, an empty ``PhysicalConfig`` is created.
        """
        self.elements = elements
        self.additional_physical_config = (
            additional_physical_config if additional_physical_config is not None else PhysicalConfig()
        )
