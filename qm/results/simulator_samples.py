import warnings
from typing import Dict, List, Union, Literal, Mapping, Optional, Sequence, TypedDict, cast

import numpy as np


class _PortsWaveformsContainer(Dict[str, Sequence[float]]):
    def __init__(self, ports: Mapping[str, Sequence[float]]):
        data = {}
        for k, v in ports.items():
            standard_port = self._standardize_port(k)
            data[standard_port] = v
            if standard_port.startswith("1-"):
                # This is for backwards compatibility
                data[standard_port[2:]] = v
        super().__init__(data)

    def __getitem__(self, port: Union[str, int]) -> Sequence[float]:
        try:
            return super().__getitem__(self._standardize_port(port))
        except KeyError:
            warnings.warn("It looks like you edited the dictionary keys, don't do that!")
            return super().__getitem__(cast(str, port))

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, (int, str)):
            return False
        return super().__contains__(self._standardize_port(item))

    @staticmethod
    def _standardize_port(port: Union[str, int]) -> str:
        # Since we moved to a notation of <fem>-<port>, we want to keep backwards compatibility
        if isinstance(port, int) or "-" not in port:
            port = f"1-{port}"
        return port


class SimulatorControllerSamples:
    def __init__(
        self, analog: Mapping[str, Sequence[float]], digital: Mapping[str, Sequence[bool]], sampling_rate: float
    ):
        self.analog = _PortsWaveformsContainer(analog)
        self.digital = _PortsWaveformsContainer(digital)
        self._sampling_rate = sampling_rate

    def plot(
        self,
        analog_ports: Optional[Union[str, int, List[Union[str, int]]]] = None,
        digital_ports: Optional[Union[str, int, List[Union[str, int]]]] = None,
    ) -> None:
        """Plots the simulated output of the OPX in the given ports.
        If no ports are given, all active ports are plotted.

        Args:
            analog_ports: Union[None, str, list[str]]
            digital_ports: Union[None, str, list[str]]
        """
        import matplotlib.pyplot as plt

        def calc_t_axis(_samples: Sequence[float]) -> np.typing.NDArray[np.float64]:
            return np.arange(len(_samples)) / self._sampling_rate * 1e9

        if isinstance(analog_ports, (str, int)):
            analog_ports = [analog_ports]
        if isinstance(digital_ports, (str, int)):
            digital_ports = [digital_ports]

        analog_to_plot = self.analog.keys() if analog_ports is None else analog_ports
        digital_to_plot = self.digital.keys() if digital_ports is None else digital_ports

        for analog_port in analog_to_plot:
            analog_samples = self.analog[analog_port]
            plt.plot(calc_t_axis(analog_samples), analog_samples, label=f"Analog {analog_port}")
        for digital_port in digital_to_plot:
            digital_samples = self.digital[digital_port]
            plt.plot(calc_t_axis(digital_samples), digital_samples, label=f"Digital {digital_port}")
        plt.xlabel("Time [ns]")
        plt.ylabel("Output")
        plt.legend()


class SimulatorSamplesDictType(TypedDict):
    analog: Dict[str, Sequence[float]]
    digital: Dict[str, Sequence[bool]]


class SimulatorSamples:
    def __init__(self, controllers: Dict[str, SimulatorControllerSamples]):
        for k, v in controllers.items():
            self.__setattr__(k, v)

    @staticmethod
    def from_np_array(arr: np.typing.NDArray[np.generic], sampling_rate: float) -> "SimulatorSamples":
        controllers: Dict[str, SimulatorSamplesDictType] = {}
        assert arr.dtype.names is not None
        for col in arr.dtype.names:
            controller_name, output, number = col.split(":")
            output = cast(Literal["analog", "digital"], output)
            controller = controllers.setdefault(controller_name, {"analog": {}, "digital": {}})
            controller[output][number] = arr[col]  # type: ignore[call-overload]
        res = {}
        for controller_name, samples in controllers.items():
            res[controller_name] = SimulatorControllerSamples(
                samples["analog"], samples["digital"], sampling_rate=sampling_rate
            )
        return SimulatorSamples(res)
