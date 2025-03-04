import time
import logging
from pathlib import Path
from dataclasses import asdict, dataclass
from typing import Dict, Tuple, Union, Mapping, Optional, cast

from tinydb.table import Document
from tinydb import Query, TinyDB, where
from tinydb.storages import JSONStorage

from qm.octave.octave_mixer_calibration import MixerCalibrationResults
from qm.octave.calibration_utils import Correction, convert_to_correction
from qm.octave.abstract_calibration_db import AbstractCalibrationDB, AbstractIFCalibration, AbstractLOCalibration

logger = logging.getLogger(__name__)


@dataclass
class _Mode:
    octave_name: str
    octave_channel: int


@dataclass
class _LOMode:
    mode_id: int
    lo_freq: Union[int, float]
    gain: Optional[float]
    latest: int


@dataclass
class _IFMode:
    lo_mode_id: int
    if_freq: float
    latest: int


@dataclass
class LOCalibrationDBSchema(AbstractLOCalibration):
    i0: float
    q0: float
    dc_gain: float
    dc_phase: float
    temperature: float
    timestamp: float
    method: str

    def get_i0(self) -> float:
        return self.i0

    def get_q0(self) -> float:
        return self.q0


@dataclass
class IFCalibrationDBSchema(AbstractIFCalibration):
    gain: float
    phase: float
    temperature: float
    timestamp: float
    method: str

    def get_correction(self) -> Correction:
        return convert_to_correction(self.gain, self.phase)


class _ModeNotFoundError(KeyError):
    def __init__(self, query: Tuple[Union[str, Union[int, float]], ...]):
        self._query = query

    def __str__(self) -> str:
        return f"Didn't find mode for {self._query}"


class CalibrationDB(AbstractCalibrationDB):
    """
    Class for the calibration database.
    """

    def __init__(self, path: Union[Path, str]) -> None:
        self._file_path: Path = Path(path) / "calibration_db.json"
        self._db = TinyDB(self._file_path, indent=4, separators=(",", ": "), storage=JSONStorage)

    def __del__(self) -> None:
        self._db.close()

    def reset(self) -> None:
        self._db.close()

        self._file_path.unlink()
        self._db = TinyDB(self._file_path, indent=4, separators=(",", ": "), storage=JSONStorage)

    def _query_mode(self, octave_channel: Tuple[str, int]) -> Optional[Document]:
        return cast(
            Optional[Document],
            self._db.table("modes").get(
                (Query().octave_name == octave_channel[0]) & (Query().octave_channel == octave_channel[1])
            ),
        )

    def _get_timestamp(self, doc: Document) -> float:
        a = cast(Document, self._db.table("lo_cal").get(doc_id=doc["latest"]))
        return cast(float, a["timestamp"])

    def _query_lo_mode(self, mode_id: int, lo_freq: Union[int, float], gain: Optional[float]) -> Optional[Document]:
        if gain is not None:
            return cast(
                Optional[Document],
                self._db.table("lo_modes").get(
                    (Query().mode_id == mode_id) & (Query().lo_freq == lo_freq) & (Query().gain == gain)
                ),
            )

        lo_modes = self._db.table("lo_modes").search((Query().mode_id == mode_id) & (Query().lo_freq == lo_freq))
        if not lo_modes:
            return None

        return max(lo_modes, key=self._get_timestamp)

    def _query_if_mode(self, lo_mode_id: int, if_freq: float) -> Optional[Document]:
        return cast(
            Optional[Document],
            self._db.table("if_modes").get((Query().lo_mode_id == lo_mode_id) & (Query().if_freq == if_freq)),
        )

    def _mode_id(self, octave_channel: Tuple[str, int], create: bool = False) -> int:
        query_result = self._query_mode(octave_channel)
        if query_result is None:
            if create:
                return self._db.table("modes").insert(asdict(_Mode(*octave_channel)))
            raise _ModeNotFoundError(octave_channel)
        else:
            return query_result.doc_id

    def _lo_mode_id(self, mode_id: int, lo_freq: Union[int, float], gain: Optional[float], create: bool = False) -> int:
        query_result = self._query_lo_mode(mode_id, lo_freq, gain)
        if query_result is None:
            if create:
                return self._db.table("lo_modes").insert(asdict(_LOMode(mode_id, lo_freq, gain, 0)))
            else:
                raise _ModeNotFoundError((mode_id, lo_freq))
        else:
            return query_result.doc_id

    def _if_mode_id(self, lo_mode_id: int, if_freq: float, create: bool = False) -> int:
        query_result = self._query_if_mode(lo_mode_id, if_freq)
        if query_result is None:
            if create:
                return self._db.table("if_modes").insert(asdict(_IFMode(lo_mode_id, if_freq, 0)))
            else:
                raise _ModeNotFoundError((lo_mode_id, if_freq))
        else:
            return query_result.doc_id

    def _update_lo_calibration(
        self,
        octave_channel: Tuple[str, int],
        lo_freq: Union[int, float],
        gain: Optional[float],
        i0: float,
        q0: float,
        dc_gain: float,
        dc_phase: float,
        temperature: float,
        method: str = "",
    ) -> None:

        mode_id = self._mode_id(octave_channel, create=True)
        lo_mode_id = self._lo_mode_id(mode_id, lo_freq, gain, create=True)

        timestamp = time.time()

        lo_cal_id = self._db.table("lo_cal").insert(
            asdict(LOCalibrationDBSchema(i0, q0, dc_gain, dc_phase, temperature, timestamp, method))
        )

        self._db.table("lo_modes").update(asdict(_LOMode(mode_id, lo_freq, gain, lo_cal_id)), doc_ids=[lo_mode_id])

    def _update_if_calibration(
        self,
        octave_channel: Tuple[str, int],
        lo_freq: Union[int, float],
        output_gain: Optional[float],
        if_freq: float,
        gain: float,
        phase: float,
        temperature: float,
        method: str = "",
    ) -> None:

        mode_id = self._mode_id(octave_channel, create=True)
        lo_mode_id = self._lo_mode_id(mode_id, lo_freq, output_gain, create=True)
        if_mode_id = self._if_mode_id(lo_mode_id, if_freq, create=True)

        timestamp = time.time()
        if_cal_id = self._db.table("if_cal").insert(
            asdict(IFCalibrationDBSchema(gain, phase, temperature, timestamp, method))
        )

        self._db.table("if_modes").update(asdict(_IFMode(lo_mode_id, if_freq, if_cal_id)), doc_ids=[if_mode_id])

    def get_lo_cal(
        self, octave_channel: Tuple[str, int], lo_freq: Union[int, float], gain: Optional[float]
    ) -> Optional[AbstractLOCalibration]:
        """
        Get the LO calibration for a given octave channel, LO frequency, and gain
        Args:
            octave_channel: The octave channel to get the calibration for.
            lo_freq: The LO frequency to get the calibration for.
            gain: The gain to get the calibration for.
        Returns:
            The LO calibration for the given parameters, or None if it doesn't exist.
        """
        try:
            mode_id = self._mode_id(octave_channel)
        except _ModeNotFoundError:
            return None
        lo_mode = self._query_lo_mode(mode_id, lo_freq, gain)
        if lo_mode is None or lo_mode["latest"] == 0:
            return None

        lo_cal = cast(Optional[Document], self._db.table("lo_cal").get(doc_id=lo_mode["latest"]))
        if lo_cal is None:
            return None
        lo_cal.pop("lo_mode_id", None)
        lo_cal_obj = LOCalibrationDBSchema(**lo_cal)

        return lo_cal_obj

    def get_if_cal(
        self,
        octave_channel: Tuple[str, int],
        lo_freq: Union[int, float],
        gain: Optional[float],
        if_freq: Union[int, float],
    ) -> Optional[IFCalibrationDBSchema]:
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
        try:
            mode_id = self._mode_id(octave_channel, create=False)
            lo_mode_id = self._lo_mode_id(mode_id, lo_freq, gain, create=False)
            if_mode = self._query_if_mode(lo_mode_id, if_freq)
        except _ModeNotFoundError:
            return None

        if if_mode is None or if_mode["latest"] == 0:
            return None

        if_cal = self._db.table("if_cal").get(doc_id=if_mode["latest"])
        if if_cal is None:
            return None
        assert isinstance(if_cal, dict)
        if_cal.pop("if_mode_id", None)
        if_cal_obj = IFCalibrationDBSchema(**if_cal)

        return if_cal_obj

    def get_all_if_cal_for_lo(
        self, octave_channel: Tuple[str, int], lo_freq: Union[int, float], gain: Optional[float]
    ) -> Mapping[Union[int, float], IFCalibrationDBSchema]:
        """
        Get IF calibration for all IF frequencies for a given octave channel, LO frequency, and gain.
        Args:
            octave_channel: The octave channel to get the calibration for.
            lo_freq: The LO frequency to get the calibration for.
            gain: The gain to get the calibration for.
        Returns:
            A dictionary of IF frequencies to their respective IF calibration.
        """
        try:
            mode_id = self._mode_id(octave_channel)
            lo_mode_id = self._lo_mode_id(mode_id, lo_freq, gain)
        except _ModeNotFoundError:
            return {}

        if_modes = self._db.table("if_modes").search(where("lo_mode_id") == lo_mode_id)

        if if_modes is None:
            return {}

        if_dict: Dict[Union[int, float], IFCalibrationDBSchema] = {}
        for if_mode in if_modes:
            if_freq = if_mode["if_freq"]
            if_cal = self.get_if_cal(octave_channel, lo_freq, gain, if_freq)

            if if_cal:
                if_dict[if_freq] = if_cal

        return if_dict

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

        for (lo_freq, output_gain), lo_cal in result.items():
            self._update_lo_calibration(
                octave_channel,
                lo_freq,
                output_gain,
                lo_cal.i0,
                lo_cal.q0,
                lo_cal.dc_gain,
                lo_cal.dc_phase,
                lo_cal.temperature,
                method,
            )

            for if_freq, if_cal in lo_cal.image.items():
                fine_cal = if_cal.fine
                self._update_if_calibration(
                    octave_channel,
                    lo_freq,
                    output_gain,
                    if_freq,
                    fine_cal.gain,
                    fine_cal.phase,
                    lo_cal.temperature,
                    method,
                )
