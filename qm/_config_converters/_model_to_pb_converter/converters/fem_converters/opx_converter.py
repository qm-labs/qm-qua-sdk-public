from typing import Mapping

from qm.exceptions import ConfigValidationException
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm._config_converters.split_ports_by_fems import FemDataOpx
from qm.config._ports import OpxPlus, AnalogInputPortOpx, AnalogOutputPortOpx, DigitalInputPortOpx, DigitalOutputPortOpx
from qm._config_converters._model_to_pb_converter.converters.fem_converters.fem_to_pb_converter_base import (
    FemToPbConverter,
)


class OpxToPbConverter(FemToPbConverter[FemDataOpx, QuaConfig.ControllerDec]):
    def convert(self, input_data: FemDataOpx) -> QuaConfig.ControllerDec:
        cont = QuaConfig.ControllerDec(type="opx1")
        for analog_output in input_data.analog_outputs:
            idx = analog_output.index
            cont.analogOutputs[idx].CopyFrom(self._analog_output_port_to_pb(analog_output))

        for analog_input_data in input_data.analog_inputs:
            idx = analog_input_data.index
            cont.analogInputs[idx].CopyFrom(self._lf_analog_input_port_to_pb(analog_input_data))
            sampling_rate = cont.analogInputs[idx].samplingRate
            if sampling_rate != 1e9:
                raise ConfigValidationException(f"Sampling rate of {sampling_rate} is not supported for OPX")

        self._set_digital_ports_in_config(cont, input_data)
        return cont

    @staticmethod
    def _analog_output_port_to_pb(data: AnalogOutputPortOpx) -> QuaConfig.AnalogOutputPortDec:
        port = QuaConfig.AnalogOutputPortDec(
            offset=data.offset.get_value(),
            delay=data.delay.get_value(),
            shareable=data.shareable.get_value(),
            crosstalk=data.crosstalk.get_value(),
        )
        if data.filter_feedforward.is_set or data.filter_feedback_seq.is_set:
            port.filter.CopyFrom(
                QuaConfig.AnalogOutputPortFilter(
                    feedforward=list(data.filter_feedforward.get_value()),
                    feedback=list(data.filter_feedback_seq.get_value()),
                )
            )
        return port

    def deconvert(self, output_data: QuaConfig.ControllerDec, controller: OpxPlus) -> FemDataOpx:  # type: ignore[override]
        """
        The deconvert function breaks liskov substitution ot simplify the interface,
        together with enjoying the goodies of the methods of the base converter
        """
        return FemDataOpx(
            analog_outputs=self._deconvert_opx_analog_outputs(output_data.analogOutputs, controller),
            analog_inputs=self._deconvert_analog_inputs(output_data.analogInputs, controller),
            digital_outputs=self._deconvert_digital_outputs(output_data.digitalOutputs, controller),
            digital_inputs=self._deconvert_digital_inputs(output_data.digitalInputs, controller),
        )

    def _deconvert_opx_analog_outputs(
        self, outputs: Mapping[int, QuaConfig.AnalogOutputPortDec], controller: OpxPlus
    ) -> tuple[AnalogOutputPortOpx, ...]:
        ret = tuple(
            self._deconvert_analog_output(data, controller=controller, index=int(name))
            for name, data in outputs.items()
        )
        return ret

    def _deconvert_analog_output(
        self, data: QuaConfig.AnalogOutputPortDec, controller: OpxPlus, index: int
    ) -> AnalogOutputPortOpx:
        return AnalogOutputPortOpx(
            controller=controller,
            index=index,
            offset=data.offset,
            delay=data.delay,
            shareable=data.shareable,
            crosstalk=dict(data.crosstalk),
            filter_feedforward=self._deconvert_feedforward_filter(data.filter),
            filter_feedback=data.filter.feedback,
        )

    def _deconvert_digital_inputs(
        self,
        inputs: Mapping[int, QuaConfig.DigitalInputPortDec],
        controller: OpxPlus,
    ) -> tuple[DigitalInputPortOpx, ...]:
        return tuple(
            self._deconvert_digital_input(data, controller=controller, index=idx) for idx, data in inputs.items()
        )

    def _deconvert_digital_input(
        self, data: QuaConfig.DigitalInputPortDec, controller: OpxPlus, index: int
    ) -> DigitalInputPortOpx:
        return DigitalInputPortOpx(
            controller=controller,
            index=index,
            shareable=data.shareable,
            deadtime=data.deadtime,
            threshold=data.threshold,
            polarity=self._get_polarity(data),
        )

    def _deconvert_analog_inputs(
        self,
        inputs: Mapping[int, QuaConfig.AnalogInputPortDec],
        controller: OpxPlus,
    ) -> tuple[AnalogInputPortOpx, ...]:
        ret = tuple(
            self._deconvert_analog_input(data, controller=controller, index=idx) for idx, data in inputs.items()
        )
        return ret

    @staticmethod
    def _deconvert_analog_input(
        data: QuaConfig.AnalogInputPortDec, controller: OpxPlus, index: int
    ) -> AnalogInputPortOpx:
        return AnalogInputPortOpx(
            controller=controller,
            index=index,
            offset=data.offset,
            gain_db=data.gainDb.value if data.gainDb is not None else 0,
            shareable=data.shareable,
        )

    def _deconvert_digital_outputs(
        self,
        outputs: Mapping[int, QuaConfig.DigitalOutputPortDec],
        controller: OpxPlus,
    ) -> tuple[DigitalOutputPortOpx, ...]:
        return tuple(
            self._deconvert_digital_output(data, controller=controller, index=idx) for idx, data in outputs.items()
        )

    @staticmethod
    def _deconvert_digital_output(
        data: QuaConfig.DigitalOutputPortDec, controller: OpxPlus, index: int
    ) -> DigitalOutputPortOpx:
        return DigitalOutputPortOpx(
            controller=controller,
            index=index,
            shareable=data.shareable,
            inverted=data.inverted,
        )
