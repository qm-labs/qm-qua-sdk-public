from abc import ABC, abstractmethod
from collections.abc import Mapping, Collection

from qm.config._octave import OctaveRfOutput
from qm.exceptions import ConfigValidationException
from qm.config._primitives import NamedObject, ConfigObject
from qm.config._ports import (
    MwFem,
    Opx1000,
    StandardPort,
    ElementPortType,
    AnalogOutputPort,
    AnalogOutputPortMicrowave,
    standardize_lf_port,
)


def _standardize_mw_port(port: StandardPort | AnalogOutputPortMicrowave) -> AnalogOutputPortMicrowave:
    if isinstance(port, AnalogOutputPortMicrowave):
        return port
    cont, fem, idx = port
    return AnalogOutputPortMicrowave(fem=MwFem(controller=Opx1000(cont), index=fem), index=idx)


class ElementInput(ConfigObject, ABC):
    """Base type for the input of an element."""

    @property
    @abstractmethod
    def ports(self) -> Collection[AnalogOutputPort]:
        pass


class NoInput(ElementInput):
    """Marks an element that has no input."""

    @property
    def ports(self) -> Collection[AnalogOutputPort]:
        return ()


class SingleInput(ElementInput):
    """The specification of the input of an element which is connected to a single port."""

    def __init__(self, port: ElementPortType):
        """
        Args:
            port: The analog output port driving this element. Either an
                ``AnalogOutputPortLf`` instance or a port reference tuple.
        """
        self.port = standardize_lf_port(port)

    @property
    def ports(self) -> Collection[AnalogOutputPort]:
        return (self.port,)


class Mixer(NamedObject):
    """The specification of the correction matrix for an IQ mixer.

    Holds a list of correction matrices for each ``(lo_frequency, intermediate_frequency)``
    pair. Each correction is a 2x2 matrix entered as a 4-element tuple, used to
    compensate for imperfections in IQ mixers.
    """

    def __init__(
        self,
        lo_if_to_correction: Mapping[tuple[float | None, float | None], tuple[float, float, float, float]],
        name: str = "",
    ) -> None:
        """
        Args:
            lo_if_to_correction: Mapping from ``(lo_frequency, intermediate_frequency)``
                to ``(c00, c01, c10, c11)`` correction tuples. ``None`` keys are
                accepted but normalized to ``0.0`` by ``lo_if_to_correction_no_none``.
            name: Name used to reference this mixer from elements. Auto-generated
                if empty.
        """
        super().__init__(name)
        self.lo_if_to_correction = dict(lo_if_to_correction)

    def add_correction(self, lo_freq: float, if_freq: float, correction: tuple[float, float, float, float]) -> None:
        self.lo_if_to_correction[lo_freq, if_freq] = correction

    def add_identity_correction(self, lo_freq: float, if_freq: float) -> None:
        # Semantic: ensure (lo, if) has a correction; identity is only a fallback.
        # Do NOT overwrite user-declared corrections from the config's `mixers` section.
        self.lo_if_to_correction.setdefault((lo_freq, if_freq), (1.0, 0.0, 0.0, 1.0))

    @property
    def data_has_nones(self) -> bool:
        return any(any(f is None for f in key) for key in self.lo_if_to_correction)

    @property
    def lo_if_to_correction_no_none(self) -> Mapping[tuple[float, float], tuple[float, float, float, float]]:
        to_return: dict[tuple[float, float], tuple[float, float, float, float]] = {}
        for (lo_freq, if_freq), correction in self.lo_if_to_correction.items():
            lo_freq = lo_freq or 0.0
            if_freq = if_freq or 0.0
            to_return[(lo_freq, if_freq)] = correction
        if len(to_return) != len(self.lo_if_to_correction):
            raise ConfigValidationException("You have two keys that are actually the same")
        return to_return


class MixInput(ElementInput):
    """The specification of the input of an element which is driven by an IQ mixer."""

    def __init__(
        self, i_port: ElementPortType, q_port: ElementPortType, mixer: Mixer | None = None, lo_frequency: float = 0
    ):
        """
        Args:
            i_port: The analog output port for the I quadrature. Either an
                ``AnalogOutputPortLf`` or a port reference tuple.
            q_port: The analog output port for the Q quadrature. Either an
                ``AnalogOutputPortLf`` or a port reference tuple.
            mixer: The mixer used to drive the input of the element. If ``None``,
                an empty ``Mixer`` is created.
            lo_frequency: The frequency of the local oscillator which drives the
                mixer.
        """
        self.i_port = standardize_lf_port(i_port)
        self.q_port = standardize_lf_port(q_port)
        # Keep `None` when the user didn't declare a mixer. Auto-creating an empty `Mixer({})` here
        # would let `NamedObject.__init__` assign a hash-based name like `mixer_22fd`, which the pb
        # then references but the mixer-collection step skips (no corrections), producing a dangling
        # reference the server rejects. The dict-to-pb path only synthesises a mixer when the
        # element has an intermediate frequency — see `add_identity_correction_to_mixer` below.
        self.mixer = mixer
        self.lo_frequency = lo_frequency

    def add_identity_correction_to_mixer(self, if_freq: float) -> None:
        if self.mixer is None:
            self.mixer = Mixer({})
        self.mixer.add_identity_correction(self.lo_frequency, if_freq)

    @property
    def ports(self) -> Collection[AnalogOutputPort]:
        return self.i_port, self.q_port

    @property
    def lo_frequency_int(self) -> int:
        return int(self.lo_frequency)


class InputCollection(ElementInput, ABC):
    """Base class for element inputs that are a collection of analog output ports."""

    def __init__(self, ports: Collection[ElementPortType] | Mapping[str, ElementPortType]):
        """
        Args:
            ports: Either a mapping of ``name -> port`` (port reference tuple or
                ``AnalogOutputPortLf``), or a sequence of ports. When a sequence is
                passed, names are auto-generated from the port's controller, FEM index
                and port index.
        """
        if not isinstance(ports, Mapping):
            standardized_ports = [standardize_lf_port(port) for port in ports]
            ports = {f"{v.controller_name}_{v.fem_1_based}_{v.index_1_based}": v for v in standardized_ports}
        self._ports = {k: standardize_lf_port(p) for k, p in ports.items()}

    @property
    def ports(self) -> Collection[AnalogOutputPort]:
        return tuple(self._ports.values())

    @property
    def name_to_port(self) -> Mapping[str, AnalogOutputPort]:
        return self._ports


class SingleInputCollection(InputCollection):
    """Defines a set of single inputs which can be switched during play statements."""


class MultipleInputs(InputCollection):
    """Defines a set of single inputs which are all played at once."""


class MicrowaveInput(ElementInput):
    """The specification of the MW input of an element."""

    def __init__(self, port: AnalogOutputPortMicrowave | StandardPort, upconverter_idx: int = 1) -> None:
        """
        Args:
            port: The MW analog output port driving this element. Either an
                ``AnalogOutputPortMicrowave`` or a 3-tuple ``(controller, fem, port)``.
            upconverter_idx: The index of the upconverter to use. Default ``1``.
        """
        self.port = _standardize_mw_port(port)
        self.upconverter_idx = upconverter_idx

    @property
    def ports(self) -> Collection[AnalogOutputPort]:
        return (self.port,)


class UpconvertedRfInput(MixInput):
    """A ``MixInput`` whose I/Q ports and LO frequency come from an Octave RF output."""

    def __init__(self, port: OctaveRfOutput, mixer: Mixer | None = None, name: str = "") -> None:
        """
        Args:
            port: The Octave RF output that supplies the I/Q connections and the
                LO frequency.
            mixer: Optional mixer correction. If ``None``, an empty ``Mixer`` is
                created.
        """
        super().__init__(
            i_port=port.i_connection,
            q_port=port.q_connection,
            mixer=mixer,
            lo_frequency=port.lo_frequency,
        )
        self.octave_port = port
        if not name:
            name = "in1"
        self.name = name
