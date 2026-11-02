import copy
from typing import TYPE_CHECKING

from qm.config._pulses._pulse import Pulse
from qm.config._primitives import NamedObject
from qm.exceptions import ElementNameAlreadyExists

if TYPE_CHECKING:
    from qm.config._elements._element import AnyElement


class Operation(NamedObject):
    """A named operation that maps elements to the pulses they should play.

    Models the per-element ``operations`` mapping from the legacy config
    (``operation_name -> pulse_name``), bundled across multiple elements.
    """

    def __init__(self, *pairs: tuple["AnyElement", Pulse], name: str = ""):
        """
        Args:
            pairs: ``(element, pulse)`` pairs describing which pulse each element
        """
        super().__init__(name)
        self._mapping: dict[str, Pulse] = {}
        for element, pulse in pairs:
            self._mapping[element.name] = pulse

    def __getitem__(self, item: "AnyElement | str") -> Pulse:
        key = item if isinstance(item, str) else item.name
        p = copy.deepcopy(self._mapping[key])
        return p

    def __setitem__(self, item: "AnyElement | str", value: Pulse) -> None:
        key = item if isinstance(item, str) else item.name
        if key in self._mapping:
            raise ElementNameAlreadyExists(f"Element {key} already mapped to pulse.")
        self._mapping[key] = value
