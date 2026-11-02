import warnings
from abc import abstractmethod
from typing import Any, Mapping, TypeVar

from qm.type_hinting import Number
from qm.api.models.capabilities import QopCaps
from qm.exceptions import ConfigValidationException
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm.config._primitives import NOT_SET, ConfigOptional
from qm.utils.deprecation_utils import QmQuaDeprecationWarning
from qm._config_converters.split_ports_by_fems import FemDataLFLN08, FemDataOctoDac
from qm.config._ports._analog_output import UpsamplingMode, AnalogOutputFeedbackFilter33, AnalogOutputFeedbackFilter35
from qm._config_converters._model_to_pb_converter.converters.fem_converters.fem_to_pb_converter_base import (
    FemToPbConverter,
)
from qm._config_converters._model_to_pb_converter.converters.fem_converters.filter_conversion_utils import (
    set_high_pass_param,
    set_exponential_param,
    deconvert_feedback_filter,
    set_exponential_dc_gain_param,
)

FemDataT = TypeVar("FemDataT", FemDataOctoDac, FemDataLFLN08)
FemPbT = TypeVar("FemPbT", QuaConfig.OctoDacFemDec, QuaConfig.LFLN08FemDec)


class AnalogFemToPbConverter(FemToPbConverter[FemDataT, FemPbT]):
    """Shared implementation for the LF-FEM and LF-LN08 converters."""

    @property
    @abstractmethod
    def _fem_pb_cls(self) -> type[FemPbT]: ...

    @property
    @abstractmethod
    def _fem_data_cls(self) -> type[FemDataT]: ...

    @property
    @abstractmethod
    def _analog_input_cls(self) -> type[Any]: ...

    @property
    @abstractmethod
    def _digital_output_cls(self) -> type[Any]: ...

    @property
    @abstractmethod
    def _digital_input_cls(self) -> type[Any]: ...

    @abstractmethod
    def _construct_analog_output(self, data: Any) -> Any:
        """Build the bare analog-output pb message (shareable/offset/delay and, for LF, output_mode)."""

    @abstractmethod
    def _deconvert_analog_output(self, data: Any, fem: Any, index: int) -> Any: ...

    def convert(self, input_data: FemDataT) -> FemPbT:
        cont = self._fem_pb_cls()
        for analog_output in input_data.analog_outputs:
            int_k = analog_output.index
            cont.analogOutputs[int_k].CopyFrom(self._analog_output_port_to_pb(analog_output))

        for analog_input_data in input_data.analog_inputs:
            int_k = analog_input_data.index
            cont.analogInputs[int_k].CopyFrom(self._lf_analog_input_port_to_pb(analog_input_data))

        self._set_digital_ports_in_config(cont, input_data)
        return cont

    def _analog_output_port_to_pb(self, data: Any) -> Any:
        self._validate_invalid_sampling_rate_and_upsampling_mode(data)
        if any(x.is_set for x in [data.min_voltage_limit, data.max_voltage_limit]) and not self._capabilities.supports(
            QopCaps.port_voltage_limits
        ):
            raise ConfigValidationException(
                "['min_voltage_limit', 'max_voltage_limit'] are supported only from QOP 3.7 and later"
            )

        filters = self._build_output_filters(data)
        analog_output = self._construct_analog_output(data)

        if data.min_voltage_limit.is_set:
            analog_output.min_voltage_limit.CopyFrom(
                type(analog_output).VoltageLimitContainer(value=data.min_voltage_limit.get_value())
            )
        if data.max_voltage_limit.is_set:
            analog_output.max_voltage_limit.CopyFrom(
                type(analog_output).VoltageLimitContainer(value=data.max_voltage_limit.get_value())
            )

        # Like the legacy converter, a declared filter is written even when empty, so it survives the round trip
        if data.filter_feedforward.is_set or data.filter_feedback_inst.is_set or data.filter_feedback_seq is not None:
            analog_output.filter.CopyFrom(filters)

        if data.crosstalk.is_set:
            if self._capabilities.supports(QopCaps.config_v2):
                crosstalk_in_pb = analog_output.crosstalk_v2.value  # in the original converter it is _value, strange.
            else:
                crosstalk_in_pb = analog_output.crosstalk
            for k, v in data.crosstalk.get_value().items():
                crosstalk_in_pb[k] = v

        self.update_sampling_rate_enum(analog_output, data)

        return analog_output

    def _build_output_filters(self, data: Any) -> QuaConfig.AnalogOutputPortFilter:
        if self._capabilities.supports(QopCaps.exponential_iir_filter):
            if data.filter_feedback_seq is not None:
                raise ConfigValidationException(
                    f"The configuration keys ['feedback'] are supported only until QOP "
                    f"{QopCaps.exponential_iir_filter.from_qop_version}. "
                    f"Use the keys ['high_pass', 'exponential'] instead."
                )

            filters = QuaConfig.AnalogOutputPortFilter()
            if data.filter_feedforward.is_set:
                self._set_pb_attr_config_v2(
                    filters, data.filter_feedforward.get_value(), "feedforward", "feedforward_v2"
                )

            if data.filter_feedback_inst.is_set:
                filter_feedback = data.filter_feedback_inst.get_value()
                set_exponential_param(filters, filter_feedback.exponential, set_attr=self._set_pb_attr_config_v2)
                set_high_pass_param(
                    filters, filter_feedback.high_pass.get_value(), set_attr=self._set_pb_attr_config_v2
                )

                if self._capabilities.supports(QopCaps.exponential_dc_gain_filter):
                    if isinstance(filter_feedback, AnalogOutputFeedbackFilter33) and filter_feedback.high_pass.is_set:
                        warnings.warn(
                            f"Setting the `high_pass` to {filter_feedback.high_pass.get_value()} is equivalent to "
                            f"setting the `exponential_dc_gain` field to 0 and adding an exponential filter of "
                            f"(1, {filter_feedback.high_pass.get_value()}). The `high_pass` field will be "
                            f"deprecated in QUA 2.0",
                            QmQuaDeprecationWarning,
                        )
                    set_exponential_dc_gain_param(
                        filters,
                        filter_feedback.exponential_dc_gain.get_value(),
                        capabilities=self._capabilities,
                        init_mode=self._init_mode,
                    )
                else:
                    if (
                        isinstance(filter_feedback, AnalogOutputFeedbackFilter35)
                        and filter_feedback.exponential_dc_gain.is_set
                    ):
                        raise ConfigValidationException(
                            f"The configuration keys ['exponential_dc_gain'] are supported only from QOP "
                            f"{QopCaps.exponential_dc_gain_filter.from_qop_version} and later. "
                            f"Use the keys ['high_pass'] instead."
                        )
            return filters

        if data.filter_feedback_inst.is_set:
            raise ConfigValidationException(
                f"The configuration keys ['exponential', 'high_pass'] are supported only from QOP "
                f"{QopCaps.exponential_iir_filter.from_qop_version} and later. "
                f"Use the keys ['feedback'] instead."
            )
        feedback = list(data.filter_feedback_seq) if data.filter_feedback_seq is not None else []
        return QuaConfig.AnalogOutputPortFilter(
            feedforward=data.filter_feedforward.get_value(),
            feedback=feedback,
        )

    def _validate_invalid_sampling_rate_and_upsampling_mode(self, data: Any) -> None:
        # A sampling rate of 1GHZ goes hand in hand with an upsampling mode, so when updating one of these values,
        # it has to be compatible with the other.
        if not self._init_mode:
            if data.sampling_rate.get_value(True) == 1e9 and not data.upsampling_mode.is_set:
                raise ConfigValidationException(
                    "'upsampling_mode' should be provided when updating 'sampling_rate' to 1GHZ."
                )

            if data.upsampling_mode.is_set and not data.sampling_rate.is_set:
                raise ConfigValidationException(
                    "'sampling_rate' of 1GHZ should be provided when updating 'upsampling_mode'."
                )

    def update_sampling_rate_enum(self, item: Any, data: Any) -> None:
        """Also update the upsampling mode, as its value is tightly correlated to the sampling rate.

        Args:
            item: The protobuf analog output port to set the sampling rate (and upsampling mode) on.
            data: The analog output port model holding the ``sampling_rate`` and ``upsampling_mode``.
        """
        pb_cls = type(item)
        sampling_rate = (
            data.sampling_rate.get_value() if self._should_apply_defaults else data.sampling_rate.get_value(True)
        )
        if sampling_rate is not None:
            if sampling_rate == 1e9:
                item.sampling_rate = pb_cls.SamplingRate.GSPS1
                if data.upsampling_mode.get_value() == "mw":
                    item.upsampling_mode = pb_cls.SamplingRateMode.mw
                else:
                    item.upsampling_mode = pb_cls.SamplingRateMode.pulse

            elif sampling_rate == 2e9:
                item.sampling_rate = pb_cls.SamplingRate.GSPS2
                item.upsampling_mode = pb_cls.SamplingRateMode.unset

            else:
                raise ValueError("Sampling rate should be either 1e9 or 2e9")

    def deconvert(self, output_data: FemPbT, fem: Any) -> FemDataT:  # type: ignore[override]
        """
        The deconvert function breaks liskov substitution to simplify the interface,
        together with enjoying the goodies of the methods of the base converter.

        Args:
            output_data: The protobuf FEM declaration to convert back into a model.
            fem: The FEM that the deconverted ports belong to.

        Returns:
            The FEM data model (analog/digital inputs and outputs) reconstructed from the protobuf.
        """
        return self._fem_data_cls(
            analog_outputs=self._deconvert_analog_outputs(output_data.analogOutputs, fem=fem),
            analog_inputs=self._deconvert_analog_inputs(output_data.analogInputs, fem=fem),
            digital_outputs=self._deconvert_digital_outputs(output_data.digitalOutputs, fem=fem),
            digital_inputs=self._deconvert_digital_inputs(output_data.digitalInputs, fem=fem),
        )

    def _deconvert_sampling_rate(self, data: Any) -> ConfigOptional[float]:
        if data.sampling_rate:
            return {1: 1e9, 2: 2e9}[data.sampling_rate]
        return NOT_SET

    def _deconvert_upsampling_mode(self, data: Any) -> ConfigOptional[UpsamplingMode]:
        if data.upsampling_mode:
            pb_cls = type(data)
            if data.upsampling_mode == pb_cls.SamplingRateMode.mw:
                return "mw"
            if data.upsampling_mode == pb_cls.SamplingRateMode.pulse:
                return "pulse"
        return NOT_SET

    def _deconvert_voltage_limits(
        self, data: Any
    ) -> tuple[ConfigOptional[Number | None], ConfigOptional[Number | None]]:
        min_voltage_limit: ConfigOptional[Number | None] = NOT_SET
        max_voltage_limit: ConfigOptional[Number | None] = NOT_SET
        if self._capabilities.supports(QopCaps.port_voltage_limits):
            if data.HasField("min_voltage_limit"):
                min_voltage_limit = data.min_voltage_limit.value if data.min_voltage_limit.HasField("value") else None
            if data.HasField("max_voltage_limit"):
                max_voltage_limit = data.max_voltage_limit.value if data.max_voltage_limit.HasField("value") else None
        return min_voltage_limit, max_voltage_limit

    def _deconvert_crosstalk(self, data: Any) -> dict[int, float]:
        return dict(data.crosstalk_v2.value) if self._capabilities.supports(QopCaps.config_v2) else dict(data.crosstalk)

    def _deconvert_feedback_filter(self, data: QuaConfig.AnalogOutputPortFilter) -> Any:
        return deconvert_feedback_filter(data, capabilities=self._capabilities)

    def _deconvert_analog_outputs(self, outputs: Mapping[int, Any], fem: Any) -> tuple[Any, ...]:
        return tuple(self._deconvert_analog_output(data, fem=fem, index=int(name)) for name, data in outputs.items())

    def _deconvert_analog_inputs(self, inputs: Mapping[int, QuaConfig.AnalogInputPortDec], fem: Any) -> tuple[Any, ...]:
        return tuple(self._deconvert_analog_input(data, fem=fem, index=idx) for idx, data in inputs.items())

    def _deconvert_analog_input(self, data: QuaConfig.AnalogInputPortDec, fem: Any, index: int) -> Any:
        sampling_rate: ConfigOptional[float] = NOT_SET
        if data.samplingRate:
            sampling_rate = data.samplingRate
        return self._analog_input_cls(
            fem=fem,
            index=index,
            offset=data.offset,
            gain_db=data.gainDb.value if data.gainDb is not None else 0,
            shareable=data.shareable,
            sampling_rate=sampling_rate,
        )

    def _deconvert_digital_outputs(
        self, outputs: Mapping[int, QuaConfig.DigitalOutputPortDec], fem: Any
    ) -> tuple[Any, ...]:
        return tuple(self._deconvert_digital_output(data, fem=fem, index=idx) for idx, data in outputs.items())

    def _deconvert_digital_output(self, data: QuaConfig.DigitalOutputPortDec, fem: Any, index: int) -> Any:
        return self._digital_output_cls(
            fem=fem,
            index=index,
            shareable=data.shareable,
            inverted=data.inverted,
        )

    def _deconvert_digital_inputs(
        self, inputs: Mapping[int, QuaConfig.DigitalInputPortDec], fem: Any
    ) -> tuple[Any, ...]:
        return tuple(self._deconvert_digital_input(data, fem=fem, index=idx) for idx, data in inputs.items())

    def _deconvert_digital_input(self, data: QuaConfig.DigitalInputPortDec, fem: Any, index: int) -> Any:
        return self._digital_input_cls(
            fem=fem,
            index=index,
            shareable=data.shareable,
            deadtime=data.deadtime,
            threshold=data.threshold,
            polarity=self._get_polarity(data),
        )
