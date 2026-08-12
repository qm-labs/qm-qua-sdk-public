import copy
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from qm.config._pulses._pulse import Pulse
from qm.config._primitives import NamedObject

if TYPE_CHECKING:
    from qm.config._elements._element import Element


class Operation(NamedObject):
    """A named operation that maps elements to the pulses they should play.

    Models the per-element ``operations`` mapping from the legacy config
    (``operation_name -> pulse_name``), bundled across multiple elements.
    """

    def __init__(self, pulses: Mapping["Element[Any]", Pulse], name: str = ""):
        """
        Args:
            pulses: Mapping ``element -> pulse`` describing which pulse each element
                plays when this operation runs.
            name: The operation name (the key under each element's ``operations``
                mapping). Auto-generated if empty.
        """
        super().__init__(name)
        self.pulses = pulses

    def __getitem__(self, item: "Element[Any]") -> Pulse:
        p = copy.deepcopy(self.pulses[item])
        return p
