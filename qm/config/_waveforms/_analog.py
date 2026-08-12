from abc import ABC
from collections.abc import Sequence
from typing import Literal, TypeAlias, cast, overload

from qm.type_hinting import Number
from qm.config._primitives import NamedObject


class WaveformValidationError(Exception):
    pass


class AnalogWaveform(NamedObject, ABC):
    """Base class for the analog waveforms sent to an element when a pulse is played."""


class ConstantWaveform(AnalogWaveform):
    """A waveform with a constant amplitude."""

    def __init__(self, sample: float, name: str = ""):
        """
        Args:
            sample: Waveform amplitude.
            name: Name used to reference this waveform from pulses. Auto-generated
                if empty.
        """
        super().__init__(name)
        self.sample = sample


class ArbitraryWaveform(AnalogWaveform, ABC):
    """The modulating envelope of an arbitrary waveform."""

    def __init__(
        self,
        samples: list[float],
        name: str = "",
    ):
        """
        Args:
            samples: List of sample values for the arbitrary waveform.
            name: Name used to reference this waveform from pulses. Auto-generated
                if empty.
        """
        super().__init__(name)
        self.samples = samples


class OverridableArbitraryWaveform(ArbitraryWaveform):
    """An arbitrary waveform that can be overridden after compilation.

    Cannot be used together with a non-default ``sampling_rate``.
    """


class ArbitraryWaveformWithMaxError(ArbitraryWaveform):
    """An arbitrary waveform with a bound on the error introduced by automatic compression."""

    def __init__(
        self,
        samples: list[float],
        max_allowed_error: float,
        name: str = "",
    ):
        """
        Args:
            samples: List of sample values for the arbitrary waveform.
            max_allowed_error: Maximum allowed error for automatic compression.
            name: Name used to reference this waveform from pulses. Auto-generated
                if empty.
        """
        super().__init__(samples, name=name)
        self.max_allowed_error = max_allowed_error


class ArbitraryWaveformWithSamplingRate(ArbitraryWaveform):
    """An arbitrary waveform with a non-default sampling rate."""

    def __init__(
        self,
        samples: list[float],
        sampling_rate: float,
        name: str = "",
    ):
        """
        Args:
            samples: List of sample values for the arbitrary waveform.
            sampling_rate: Sampling rate, in S/s (samples per second). Default is
                ``1e9``. Cannot be set when ``is_overridable=True``.
            name: Name used to reference this waveform from pulses. Auto-generated
                if empty.
        """
        super().__init__(samples, name=name)
        self.sampling_rate = sampling_rate


class WaveformArray(AnalogWaveform):
    """A waveform consisting of multiple arrays of arbitrary samples."""

    def __init__(
        self,
        samples_array: Sequence[Sequence[float]],
        name: str = "",
    ):
        """
        Args:
            samples_array: Arrays of samples; each inner array contains the values
                of one arbitrary waveform variant.
            name: Name used to reference this waveform from pulses. Auto-generated
                if empty.
        """
        super().__init__(name=name)
        # todo - add validation on the structure
        self.samples_array = [list(samples) for samples in samples_array]


@overload
def create_arbitrary_waveform(
    samples: list[float],
    *,
    name: str = "",
) -> ArbitraryWaveformWithMaxError:
    pass


@overload
def create_arbitrary_waveform(
    samples: list[float],
    *,
    is_overridable: Literal[True] = True,
    name: str = "",
) -> OverridableArbitraryWaveform:
    pass


@overload
def create_arbitrary_waveform(
    samples: list[float],
    *,
    max_allowed_error: float,
    name: str = "",
) -> ArbitraryWaveformWithMaxError:
    pass


@overload
def create_arbitrary_waveform(
    samples: list[float],
    *,
    sampling_rate: float,
    name: str = "",
) -> ArbitraryWaveformWithSamplingRate:
    pass


def create_arbitrary_waveform(
    samples: list[float],
    *,
    is_overridable: bool = False,
    max_allowed_error: float | None = None,
    sampling_rate: float | None = None,
    name: str = "",
) -> ArbitraryWaveform:
    if is_overridable:
        if max_allowed_error is not None:
            raise WaveformValidationError("Overridable waveforms cannot have property 'max_allowed_error'")
        if sampling_rate is not None:
            raise WaveformValidationError("Overridable waveforms cannot have property 'sampling_rate_key'")
        return OverridableArbitraryWaveform(samples=samples, name=name)

    if max_allowed_error is not None:
        if sampling_rate is not None:
            raise WaveformValidationError("Cannot use both 'max_allowed_error' and 'sampling_rate'")
        return ArbitraryWaveformWithMaxError(samples=samples, max_allowed_error=max_allowed_error, name=name)

    return ArbitraryWaveformWithMaxError(samples=samples, max_allowed_error=1e-4, name=name)


SingleWaveformOptions: TypeAlias = Number | Sequence[float] | Sequence[Sequence[float]] | AnalogWaveform


def standardize_waveform(waveform: SingleWaveformOptions) -> AnalogWaveform:
    if isinstance(waveform, AnalogWaveform):
        return waveform
    if isinstance(waveform, (float, int)):
        return ConstantWaveform(waveform)
    if isinstance(waveform[0], (float, int)):
        return create_arbitrary_waveform(list(cast(Sequence[float], waveform)), is_overridable=True)
    return WaveformArray(cast(Sequence[Sequence[float]], waveform))
