import warnings
from typing import Mapping, Sequence

from qm import QopCaps
from qm.type_hinting import Number
from qm.exceptions import ConfigValidationException
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm._config_converters.split_ports_by_fems import FemDataOctoDac
from qm.config._primitives import NOT_SET, ConfigValue, ConfigOptional
from qm._config_converters._model_to_pb_converter.converters.fem_converters.fem_to_pb_converter_base import (
    FemToPbConverter,
)
from qm.config._ports import (
    LfFem,
    AnalogInputPortOctoDac,
    AnalogOutputPortOctoDac,
    DigitalInputPortOctoDac,
    DigitalOutputPortOctoDac,
)
from qm.config._ports._analog_output import (
    OutputMode,
    UpsamplingMode,
    AnalogOutputFeedbackFilter33,
    AnalogOutputFeedbackFilter35,
    AnalogOutputFeedbackExponential,
)


class LfFemToPbConverter(FemToPbConverter[FemDataOctoDac, QuaConfig.OctoDacFemDec]):
    def convert(self, input_data: FemDataOctoDac) -> QuaConfig.OctoDacFemDec:
        cont = QuaConfig.OctoDacFemDec()
        for analog_output in input_data.analog_outputs:
            int_k = analog_output.index
            cont.analogOutputs[int_k].CopyFrom(self._analog_output_port_to_pb(analog_output))

        for analog_input_data in input_data.analog_inputs:
            int_k = analog_input_data.index
            cont.analogInputs[int_k].CopyFrom(self._lf_analog_input_port_to_pb(analog_input_data))

        self._set_digital_ports_in_config(cont, input_data)
        return cont

    def _analog_output_port_to_pb(self, data: AnalogOutputPortOctoDac) -> QuaConfig.OctoDacAnalogOutputPortDec:
        self._validate_invalid_sampling_rate_and_upsampling_mode(data)
        if any(x.is_set for x in [data.min_voltage_limit, data.max_voltage_limit]) and not self._capabilities.supports(
            QopCaps.port_voltage_limits
        ):
            raise ConfigValidationException(
                "['min_voltage_limit', 'max_voltage_limit'] are supported only from QOP 3.7 and later"
            )
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
                self._set_exponential_param(filters, filter_feedback.exponential)
                self._set_high_pass_param(filters, filter_feedback.high_pass.get_value())

                if self._capabilities.supports(QopCaps.exponential_dc_gain_filter):
                    if isinstance(filter_feedback, AnalogOutputFeedbackFilter33) and filter_feedback.high_pass.is_set:
                        warnings.warn(
                            f"Setting the `high_pass` to {filter_feedback.high_pass.get_value()} is equivalent to "
                            f"setting the `exponential_dc_gain` field to 0 and adding an exponential filter of "
                            f"(1, {filter_feedback.high_pass.get_value()}). The `high_pass` field will be "
                            f"deprecated in QUA 2.0.",
                            DeprecationWarning,
                        )
                    self._set_exponential_dc_gain_param(filters, filter_feedback.exponential_dc_gain.get_value())
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
        else:
            if data.filter_feedback_inst.is_set:
                raise ConfigValidationException(
                    f"The configuration keys ['exponential', 'high_pass'] are supported only from QOP "
                    f"{QopCaps.exponential_iir_filter.from_qop_version} and later. "
                    f"Use the keys ['feedback'] instead."
                )
            feedback = list(data.filter_feedback_seq) if data.filter_feedback_seq is not None else []
            filters = QuaConfig.AnalogOutputPortFilter(
                feedforward=data.filter_feedforward.get_value(),
                feedback=feedback,
            )

        if self._should_apply_defaults:
            analog_output = QuaConfig.OctoDacAnalogOutputPortDec(
                shareable=data.shareable.get_value(),
                offset=data.offset.get_value(),
                delay=data.delay.get_value(),
                output_mode=self._output_mode_to_pb(data.output_mode),
            )
        else:
            analog_output = QuaConfig.OctoDacAnalogOutputPortDec(
                offset=data.offset.get_value(True),
                delay=data.delay.get_value(True),
            )
            if data.shareable.is_set:
                analog_output.shareable = data.shareable.get_value()

            if data.output_mode.is_set:
                analog_output.output_mode = self._output_mode_to_pb(data.output_mode)

        if data.min_voltage_limit.is_set:
            analog_output.min_voltage_limit.CopyFrom(
                QuaConfig.OctoDacAnalogOutputPortDec.VoltageLimitContainer(value=data.min_voltage_limit.get_value())
            )
        if data.max_voltage_limit.is_set:
            analog_output.max_voltage_limit.CopyFrom(
                QuaConfig.OctoDacAnalogOutputPortDec.VoltageLimitContainer(value=data.max_voltage_limit.get_value())
            )

        if filters.ByteSize():
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

    def _validate_invalid_sampling_rate_and_upsampling_mode(self, data: AnalogOutputPortOctoDac) -> None:
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

    def _set_exponential_param(
        self,
        item: QuaConfig.AnalogOutputPortFilter,
        exponential: Sequence[tuple[float, float]],
    ) -> None:
        exponential_serialized = [
            QuaConfig.ExponentialParameters(amplitude=amp, time_constant=tau) for amp, tau in exponential
        ]
        self._set_pb_attr_config_v2(item.iir, exponential_serialized, "exponential", "exponential_v2")

    def _set_high_pass_param(
        self,
        item: QuaConfig.AnalogOutputPortFilter,
        data: float | None,
    ) -> None:
        if data is None:
            return

        self._set_pb_attr_config_v2(
            item.iir,
            data,
            "high_pass",
            "high_pass_v2",
            allow_nones=True,
            create_container=QuaConfig.IirFilter.HighPassContainer,
        )

    def _set_exponential_dc_gain_param(
        self,
        item: QuaConfig.AnalogOutputPortFilter,
        data: float | None,
    ) -> None:
        if (not self._init_mode) and self._capabilities.supports(QopCaps.config_v2) and data is None:
            return
        item.iir.exponential_dc_gain.CopyFrom(QuaConfig.IirFilter.ExponentialDcGainContainer(value=data))

    @staticmethod
    def _output_mode_to_pb(data: ConfigValue[OutputMode]) -> QuaConfig.OctoDacAnalogOutputPortDec.OutputMode:
        if data.get_value() == "direct":
            return QuaConfig.OctoDacAnalogOutputPortDec.OutputMode.direct
        return QuaConfig.OctoDacAnalogOutputPortDec.OutputMode.amplified

    def update_sampling_rate_enum(
        self, item: QuaConfig.OctoDacAnalogOutputPortDec, data: AnalogOutputPortOctoDac
    ) -> None:
        """Also update the upsampling mode, as its value is tightly correlated to the sampling rate."""
        sampling_rate = (
            data.sampling_rate.get_value() if self._should_apply_defaults else data.sampling_rate.get_value(True)
        )
        if sampling_rate is not None:
            if sampling_rate == 1e9:
                item.sampling_rate = QuaConfig.OctoDacAnalogOutputPortDec.SamplingRate.GSPS1
                if data.upsampling_mode.get_value() == "mw":
                    item.upsampling_mode = QuaConfig.OctoDacAnalogOutputPortDec.SamplingRateMode.mw
                else:
                    item.upsampling_mode = QuaConfig.OctoDacAnalogOutputPortDec.SamplingRateMode.pulse

            elif sampling_rate == 2e9:
                item.sampling_rate = QuaConfig.OctoDacAnalogOutputPortDec.SamplingRate.GSPS2
                item.upsampling_mode = QuaConfig.OctoDacAnalogOutputPortDec.SamplingRateMode.unset

            else:
                raise ValueError("Sampling rate should be either 1e9 or 2e9")

    def deconvert(self, output_data: QuaConfig.OctoDacFemDec, fem: LfFem) -> FemDataOctoDac:  # type: ignore[override]
        """
        The deconvert function breaks liskov substitution ot simplify the interface,
        together with enjoying the goodies of the methods of the base converter
        """
        return FemDataOctoDac(
            analog_outputs=self._deconvert_analog_outputs(output_data.analogOutputs, fem=fem),
            analog_inputs=self._deconvert_analog_inputs(output_data.analogInputs, fem=fem),
            digital_outputs=self._deconvert_digital_outputs(output_data.digitalOutputs, fem=fem),
            digital_inputs=self._deconvert_digital_inputs(output_data.digitalInputs, fem=fem),
        )

    def _deconvert_analog_output(
        self,
        data: QuaConfig.OctoDacAnalogOutputPortDec,
        fem: LfFem,
        index: int,
    ) -> AnalogOutputPortOctoDac:
        filter_feedforward = self._deconvert_feedforward_filter(data.filter)
        filter_feedback = self._deconvert_feedback_filter(data.filter)

        sampling_rate: ConfigOptional[float] = NOT_SET
        if data.sampling_rate:
            sampling_rate = {1: 1e9, 2: 2e9}[data.sampling_rate]

        upsampling_mode: ConfigOptional[UpsamplingMode] = NOT_SET
        if data.upsampling_mode:
            if data.upsampling_mode == QuaConfig.OctoDacAnalogOutputPortDec.SamplingRateMode.mw:
                upsampling_mode = "mw"
            if data.upsampling_mode == QuaConfig.OctoDacAnalogOutputPortDec.SamplingRateMode.pulse:
                upsampling_mode = "pulse"

        output_mode: ConfigOptional[OutputMode] = NOT_SET
        if data.HasField("output_mode"):
            if data.output_mode == QuaConfig.OctoDacAnalogOutputPortDec.OutputMode.direct:
                output_mode = "direct"
            elif data.output_mode == QuaConfig.OctoDacAnalogOutputPortDec.OutputMode.amplified:
                output_mode = "amplified"

        min_voltage_limit: ConfigOptional[Number | None] = NOT_SET
        max_voltage_limit: ConfigOptional[Number | None] = NOT_SET
        if self._capabilities.supports(QopCaps.port_voltage_limits):
            if data.HasField("min_voltage_limit"):
                min_voltage_limit = data.min_voltage_limit.value if data.min_voltage_limit.HasField("value") else None
            if data.HasField("max_voltage_limit"):
                max_voltage_limit = data.max_voltage_limit.value if data.max_voltage_limit.HasField("value") else None

        return AnalogOutputPortOctoDac(
            fem=fem,
            index=index,
            offset=data.offset,
            delay=data.delay,
            shareable=data.shareable,
            crosstalk=(
                dict(data.crosstalk_v2.value)
                if self._capabilities.supports(QopCaps.config_v2)
                else dict(data.crosstalk)
            ),
            filter_feedforward=filter_feedforward,
            filter_feedback=filter_feedback,
            sampling_rate=sampling_rate,
            upsampling_mode=upsampling_mode,
            output_mode=output_mode,
            min_voltage_limit=min_voltage_limit,
            max_voltage_limit=max_voltage_limit,
        )

    def _deconvert_analog_outputs(
        self,
        outputs: Mapping[int, QuaConfig.OctoDacAnalogOutputPortDec],
        fem: LfFem,
    ) -> tuple[AnalogOutputPortOctoDac, ...]:
        ret = tuple(self._deconvert_analog_output(data, fem=fem, index=int(name)) for name, data in outputs.items())
        return ret

    def _deconvert_feedback_filter(
        self, output_data: QuaConfig.AnalogOutputPortFilter
    ) -> AnalogOutputFeedbackExponential | Sequence[float]:
        if not self._capabilities.supports(QopCaps.exponential_iir_filter):
            return list(output_data.feedback)

        raw_exponential = (
            output_data.iir.exponential_v2.value
            if self._capabilities.supports(QopCaps.config_v2)
            else output_data.iir.exponential
        )
        exponential = [(exp_params.amplitude, exp_params.time_constant) for exp_params in raw_exponential]

        if self._capabilities.supports(QopCaps.config_v2):
            # We handle both cases: the container being None (as likely returned by the Gateway),
            # and an initialized container with value=None.
            high_pass = output_data.iir.high_pass_v2.value if output_data.iir.HasField("high_pass_v2") else None
        else:
            high_pass = output_data.iir.high_pass if output_data.iir.HasField("high_pass") else None

        if self._capabilities.supports(QopCaps.exponential_dc_gain_filter):
            exponential_dc_gain = (
                output_data.iir.exponential_dc_gain.value
                if output_data.iir.HasField("exponential_dc_gain")
                and output_data.iir.exponential_dc_gain.HasField("value")
                else None
            )
            if exponential_dc_gain is None and high_pass is not None:
                return AnalogOutputFeedbackFilter33(exponential, high_pass)
            return AnalogOutputFeedbackFilter35(exponential, exponential_dc_gain)
        return AnalogOutputFeedbackFilter33(exponential, high_pass)

    def _deconvert_analog_inputs(
        self,
        inputs: Mapping[int, QuaConfig.AnalogInputPortDec],
        fem: LfFem,
    ) -> tuple[AnalogInputPortOctoDac, ...]:
        ret = tuple(self._deconvert_analog_input(data, fem=fem, index=idx) for idx, data in inputs.items())
        return ret

    @staticmethod
    def _deconvert_analog_input(data: QuaConfig.AnalogInputPortDec, fem: LfFem, index: int) -> AnalogInputPortOctoDac:
        sampling_rate: ConfigOptional[float] = NOT_SET
        if data.samplingRate:
            sampling_rate = data.samplingRate
        return AnalogInputPortOctoDac(
            fem=fem,
            index=index,
            offset=data.offset,
            gain_db=data.gainDb.value if data.gainDb is not None else 0,
            shareable=data.shareable,
            sampling_rate=sampling_rate,
        )

    def _deconvert_digital_outputs(
        self,
        outputs: Mapping[int, QuaConfig.DigitalOutputPortDec],
        fem: LfFem,
    ) -> tuple[DigitalOutputPortOctoDac, ...]:
        return tuple(self._deconvert_digital_output(data, fem=fem, index=idx) for idx, data in outputs.items())

    @staticmethod
    def _deconvert_digital_output(
        data: QuaConfig.DigitalOutputPortDec, fem: LfFem, index: int
    ) -> DigitalOutputPortOctoDac:
        return DigitalOutputPortOctoDac(
            fem=fem,
            index=index,
            shareable=data.shareable,
            inverted=data.inverted,
        )

    def _deconvert_digital_inputs(
        self,
        inputs: Mapping[int, QuaConfig.DigitalInputPortDec],
        fem: LfFem,
    ) -> tuple[DigitalInputPortOctoDac, ...]:
        return tuple(self._deconvert_digital_input(data, fem=fem, index=idx) for idx, data in inputs.items())

    def _deconvert_digital_input(
        self, data: QuaConfig.DigitalInputPortDec, fem: LfFem, index: int
    ) -> DigitalInputPortOctoDac:
        return DigitalInputPortOctoDac(
            fem=fem,
            index=index,
            shareable=data.shareable,
            deadtime=data.deadtime,
            threshold=data.threshold,
            polarity=self._get_polarity(data),
        )
