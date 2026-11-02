from qm.config._primitives import NOT_SET
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm._config_converters.split_ports_by_fems import FemDataLFLN08
from qm._config_converters._model_to_pb_converter.converters.fem_converters.analog_fem_converter_base import (
    AnalogFemToPbConverter,
)
from qm.config._ports import (
    LFLN08Fem,
    AnalogInputPortLFLN08,
    AnalogOutputPortLFLN08,
    DigitalInputPortLFLN08,
    DigitalOutputPortLFLN08,
)


class LFLN08FemToPbConverter(AnalogFemToPbConverter[FemDataLFLN08, QuaConfig.LFLN08FemDec]):
    @property
    def _fem_pb_cls(self) -> type[QuaConfig.LFLN08FemDec]:
        return QuaConfig.LFLN08FemDec

    @property
    def _fem_data_cls(self) -> type[FemDataLFLN08]:
        return FemDataLFLN08

    @property
    def _analog_input_cls(self) -> type[AnalogInputPortLFLN08]:
        return AnalogInputPortLFLN08

    @property
    def _digital_output_cls(self) -> type[DigitalOutputPortLFLN08]:
        return DigitalOutputPortLFLN08

    @property
    def _digital_input_cls(self) -> type[DigitalInputPortLFLN08]:
        return DigitalInputPortLFLN08

    def _construct_analog_output(self, data: AnalogOutputPortLFLN08) -> QuaConfig.LFLN08AnalogOutputPortDec:
        if self._should_apply_defaults:
            analog_output = QuaConfig.LFLN08AnalogOutputPortDec(
                shareable=data.shareable.get_value(),
                offset=data.offset.get_value(),
                delay=data.delay.get_value(),
            )
        else:
            analog_output = QuaConfig.LFLN08AnalogOutputPortDec(
                offset=data.offset.get_value(True),
                delay=data.delay.get_value(True),
            )
            if data.shareable.is_set:
                analog_output.shareable = data.shareable.get_value()
        return analog_output

    def _deconvert_analog_output(
        self,
        data: QuaConfig.LFLN08AnalogOutputPortDec,
        fem: LFLN08Fem,
        index: int,
    ) -> AnalogOutputPortLFLN08:
        min_voltage_limit, max_voltage_limit = self._deconvert_voltage_limits(data)

        return AnalogOutputPortLFLN08(
            fem=fem,
            index=index,
            offset=data.offset,
            delay=data.delay,
            shareable=data.shareable,
            crosstalk=self._deconvert_crosstalk(data),
            filter_feedforward=self._deconvert_feedforward_filter(data.filter) if data.HasField("filter") else NOT_SET,
            filter_feedback=self._deconvert_feedback_filter(data.filter) if data.HasField("filter") else NOT_SET,
            sampling_rate=self._deconvert_sampling_rate(data),
            upsampling_mode=self._deconvert_upsampling_mode(data),
            min_voltage_limit=min_voltage_limit,
            max_voltage_limit=max_voltage_limit,
        )
