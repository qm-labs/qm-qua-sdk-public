from abc import ABCMeta, abstractmethod
from typing import Tuple, Union, Mapping, Optional

from qm.octave.calibration_utils import Correction
from qm.octave.octave_mixer_calibration import MixerCalibrationResults


class AbstractLOCalibration(metaclass=ABCMeta):
    @abstractmethod
    def get_i0(self) -> float:
        pass

    @abstractmethod
    def get_q0(self) -> float:
        pass


class AbstractIFCalibration(metaclass=ABCMeta):
    @abstractmethod
    def get_correction(self) -> Correction:
        pass


class AbstractCalibrationDB(metaclass=ABCMeta):
    """
    Abstract class for the calibration database.
    """

    @abstractmethod
    def get_lo_cal(
        self, octave_channel: Tuple[str, int], lo_freq: Union[int, float], gain: Optional[float]
    ) -> Optional[AbstractLOCalibration]:
        """
        Get the LO calibration for a given octave channel, LO frequency, and gain.
        Args:
            octave_channel: The octave channel to get the calibration for.
            lo_freq: The LO frequency to get the calibration for.
            gain: The gain to get the calibration for.
        Returns:
            The LO calibration for the given parameters, or None if it doesn't exist.
        """
        pass

    @abstractmethod
    def get_if_cal(
        self,
        octave_channel: Tuple[str, int],
        lo_freq: Union[int, float],
        gain: Optional[float],
        if_freq: Union[int, float],
    ) -> Optional[AbstractIFCalibration]:
        """
        Get the IF calibration for a given octave channel, LO frequency, gain, and IF frequency.
        Args:
            octave_channel: The octave channel to get the calibration for.
            lo_freq: The LO frequency to get the calibration for.
            gain: The gain to get the calibration for.
            if_freq: The IF frequency to get the calibration for.
        Returns:
            The IF calibration for the given parameters, or None if it doesn't exist.
        """
        pass

    @abstractmethod
    def get_all_if_cal_for_lo(
        self, octave_channel: Tuple[str, int], lo_freq: Union[int, float], gain: Optional[float]
    ) -> Mapping[Union[int, float], AbstractIFCalibration]:
        """
        Get IF calibration for all IF frequencies for a given octave channel, LO frequency, and gain.
        Args:
            octave_channel: The octave channel to get the calibration for.
            lo_freq: The LO frequency to get the calibration for.
            gain: The gain to get the calibration for.
        Returns:
            A dictionary of IF frequencies to their respective IF calibration, or an empty dictionary if none exist.
        """
        pass

    @abstractmethod
    def update_calibration_result(
        self, result: MixerCalibrationResults, octave_channel: Tuple[str, int], method: str = ""
    ) -> None:
        """
        Update the calibration database with the given calibration results.
        Args:
            result: The calibration results to update the database with.
            octave_channel: The octave channel to update the database with.
            method: Deprecated.
        """
        pass
