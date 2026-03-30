from collections.abc import Mapping
from typing import Dict, Type, Union, Literal, TypeVar, MutableMapping, cast

from google.protobuf.wrappers_pb2 import Int32Value

from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.utils.protobuf_utils import which_one_of
from qm.exceptions import ConfigValidationException
from qm.api.models.capabilities import OPX_FEM_IDX, QopCaps, ServerCapabilities
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter
from qm.program._dict_to_pb_converter.converters.element_converter import DEFAULT_DUC_IDX
from qm.program._dict_to_pb_converter.converters.control_device_converter.analog_output_filters_converter import (
    AnalogOutputFiltersConverter,
)
from qm.type_hinting.config_types import (
    FEM_IDX,
    Band,
    Upconverter,
    LfFemConfigType,
    MwFemConfigType,
    ControllerConfigType,
    MwUpconverterConfigType,
    AnalogInputPortConfigType,
    AnalogOutputPortConfigType,
    DigitalInputPortConfigType,
    DigitalOutputPortConfigType,
    OPX1000ControllerConfigType,
    MwFemAnalogInputPortConfigType,
    MwFemAnalogOutputPortConfigType,
    AnalogOutputPortConfigTypeOctoDac,
)

AnalogOutputType = TypeVar(
    "AnalogOutputType",
    inc_qua_config_pb2.QuaConfig.AnalogOutputPortDec,
    inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec,
)
ControllerConfigTypeVar = TypeVar(
    "ControllerConfigTypeVar",
    inc_qua_config_pb2.QuaConfig.OctoDacFemDec,
    inc_qua_config_pb2.QuaConfig.ControllerDec,
    inc_qua_config_pb2.QuaConfig.MicrowaveFemDec,
)


class ControlDeviceConverter(
    BaseDictToPbConverter[
        Union[ControllerConfigType, OPX1000ControllerConfigType], inc_qua_config_pb2.QuaConfig.DeviceDec
    ]
):
    def __init__(self, capabilities: ServerCapabilities, init_mode: bool) -> None:
        super().__init__(capabilities, init_mode)
        self._filters_converter = AnalogOutputFiltersConverter(capabilities, init_mode)

    def convert(
        self, input_data: Union[ControllerConfigType, OPX1000ControllerConfigType]
    ) -> inc_qua_config_pb2.QuaConfig.DeviceDec:
        return self.controlling_devices_to_pb(input_data)

    def controlling_devices_to_pb(
        self, data: Union[ControllerConfigType, OPX1000ControllerConfigType]
    ) -> inc_qua_config_pb2.QuaConfig.DeviceDec:
        fems: Dict[int, inc_qua_config_pb2.QuaConfig.FEMTypes] = {}

        if "fems" in data:
            data = cast(OPX1000ControllerConfigType, data)
            # Here we assume that we don't declare OPX as FEM
            if set(data) & {"analog", "analog_outputs", "digital_outputs", "digital_inputs"}:
                raise Exception(
                    "'analog', 'analog_outputs', 'digital_outputs' and 'digital_inputs' are not allowed when 'fems' is present"
                )
            for k, v in data["fems"].items():
                if v.get("type") == "MW":
                    fems[int(k)] = self._mw_fem_to_pb(cast(MwFemConfigType, v))
                else:
                    fems[int(k)] = self._fem_to_pb(cast(LfFemConfigType, v))

        else:
            data = cast(ControllerConfigType, data)
            fems[OPX_FEM_IDX] = self._controller_to_pb(data)

        item = inc_qua_config_pb2.QuaConfig.DeviceDec(fems=fems)
        return item

    def _controller_to_pb(self, data: ControllerConfigType) -> inc_qua_config_pb2.QuaConfig.FEMTypes:
        cont = inc_qua_config_pb2.QuaConfig.ControllerDec(type=data.get("type", "opx1"))
        cont = self._set_ports_in_config(cont, data)
        return inc_qua_config_pb2.QuaConfig.FEMTypes(opx=cont)

    def _fem_to_pb(self, data: LfFemConfigType) -> inc_qua_config_pb2.QuaConfig.FEMTypes:
        cont = inc_qua_config_pb2.QuaConfig.OctoDacFemDec()
        cont = self._set_ports_in_config(cont, data)
        return inc_qua_config_pb2.QuaConfig.FEMTypes(octo_dac=cont)

    def _mw_fem_to_pb(self, data: MwFemConfigType) -> inc_qua_config_pb2.QuaConfig.FEMTypes:
        cont = inc_qua_config_pb2.QuaConfig.MicrowaveFemDec()
        cont = self._set_ports_in_config(cont, data)
        return inc_qua_config_pb2.QuaConfig.FEMTypes(microwave=cont)

    def _set_ports_in_config(
        self,
        config: ControllerConfigTypeVar,
        data: Union[ControllerConfigType, LfFemConfigType, MwFemConfigType],
    ) -> ControllerConfigTypeVar:
        if "analog_outputs" in data:
            for analog_output_idx, analog_output_data in data["analog_outputs"].items():
                int_k = int(analog_output_idx)
                if isinstance(config, inc_qua_config_pb2.QuaConfig.ControllerDec):
                    analog_output_data = cast(AnalogOutputPortConfigType, analog_output_data)
                    config.analogOutputs[int_k].CopyFrom(
                        self.analog_output_port_to_pb(
                            analog_output_data,
                            output_type=inc_qua_config_pb2.QuaConfig.AnalogOutputPortDec,
                        )
                    )
                elif isinstance(config, inc_qua_config_pb2.QuaConfig.OctoDacFemDec):
                    analog_output_data = cast(AnalogOutputPortConfigTypeOctoDac, analog_output_data)
                    config.analogOutputs[int_k].CopyFrom(self.opx_1000_analog_output_port_to_pb(analog_output_data))
                elif isinstance(config, inc_qua_config_pb2.QuaConfig.MicrowaveFemDec):
                    analog_output_data = cast(MwFemAnalogOutputPortConfigType, analog_output_data)
                    config.analogOutputs[int_k].CopyFrom(self.mw_fem_analog_output_to_pb(analog_output_data))
                else:
                    raise ValueError(f"Unknown config type {type(config)}")

        if "analog_inputs" in data:
            if isinstance(
                config, (inc_qua_config_pb2.QuaConfig.ControllerDec, inc_qua_config_pb2.QuaConfig.OctoDacFemDec)
            ):
                for analog_input_idx, analog_input_data in data["analog_inputs"].items():
                    analog_input_data = cast(AnalogInputPortConfigType, analog_input_data)
                    config.analogInputs[int(analog_input_idx)].CopyFrom(self.analog_input_port_to_pb(analog_input_data))
                    if isinstance(config, inc_qua_config_pb2.QuaConfig.ControllerDec):
                        sampling_rate = config.analogInputs[int(analog_input_idx)].samplingRate
                        if sampling_rate != 1e9:
                            raise ConfigValidationException(
                                f"Sampling rate of {sampling_rate} is not supported for OPX"
                            )
            elif isinstance(config, inc_qua_config_pb2.QuaConfig.MicrowaveFemDec):
                for analog_input_idx, analog_input_data_mw in data["analog_inputs"].items():
                    analog_input_data_mw = cast(MwFemAnalogInputPortConfigType, analog_input_data_mw)
                    config.analogInputs[int(analog_input_idx)].CopyFrom(
                        self.mw_fem_analog_input_port_to_pb(analog_input_data_mw)
                    )
            else:
                raise ValueError(f"Unknown config type {type(config)}")

        if "digital_outputs" in data:
            for digital_output_idx, digital_output_data in data["digital_outputs"].items():
                config.digitalOutputs[int(digital_output_idx)].CopyFrom(
                    self.digital_output_port_to_pb(digital_output_data)
                )

        if "digital_inputs" in data:
            for digital_input_idx, digital_input_data in data["digital_inputs"].items():
                config.digitalInputs[int(digital_input_idx)].CopyFrom(self.digital_input_port_to_pb(digital_input_data))

        return config

    def analog_input_port_to_pb(
        self, data: AnalogInputPortConfigType
    ) -> inc_qua_config_pb2.QuaConfig.AnalogInputPortDec:
        default_schema: AnalogInputPortConfigType = {
            "offset": 0.0,
            "shareable": False,
            "gain_db": 0,
            "sampling_rate": 1e9,
        }
        data_with_defaults = self._apply_defaults(data, default_schema=default_schema)
        analog_input = inc_qua_config_pb2.QuaConfig.AnalogInputPortDec()
        gain_db = data_with_defaults.get("gain_db")
        if gain_db is not None:
            analog_input.gainDb.CopyFrom(Int32Value(value=gain_db))
        sharable = data_with_defaults.get("shareable")
        if sharable is not None:
            analog_input.shareable = sharable
        sampling_rate = data_with_defaults.get("sampling_rate")
        if sampling_rate is not None:
            analog_input.samplingRate = sampling_rate
        offset = data_with_defaults.get("offset")
        if offset is not None:
            analog_input.offset = offset
        return analog_input

    def mw_fem_analog_input_port_to_pb(
        self, data: MwFemAnalogInputPortConfigType
    ) -> inc_qua_config_pb2.QuaConfig.MicrowaveAnalogInputPortDec:
        if self._init_mode:
            self._validate_required_fields(data, ["band", "downconverter_frequency"], "microwave analog input port")

        default_schema: MwFemAnalogInputPortConfigType = {"sampling_rate": 1e9, "gain_db": 0, "shareable": False}
        data_with_defaults = self._apply_defaults(data, default_schema)
        analog_input = inc_qua_config_pb2.QuaConfig.MicrowaveAnalogInputPortDec()
        sampling_rate = data_with_defaults.get("sampling_rate")
        if sampling_rate is not None:
            analog_input.samplingRate = sampling_rate

        gain_db = data_with_defaults.get("gain_db")
        if gain_db is not None:
            analog_input.gain_db = gain_db

        band = data_with_defaults.get("band")
        if band is not None:
            analog_input.band = band
        shareable = data_with_defaults.get("shareable")
        if shareable is not None:
            analog_input.shareable = shareable
        if "downconverter_frequency" in data_with_defaults:
            analog_input.downconverter.frequency = data_with_defaults["downconverter_frequency"]

        if self._capabilities.supports(QopCaps.lo_mode):
            data_with_defaults = self._apply_defaults(  # type: ignore[assignment]
                data_with_defaults,
                default_schema={"lo_mode": "auto"},
            )
            if "lo_mode" in data_with_defaults:
                lo_mode_value = data_with_defaults.get("lo_mode")
                # mypy
                if lo_mode_value is None:
                    raise ConfigValidationException("'lo_mode' is required.")
                analog_input.lo_mode = getattr(
                    inc_qua_config_pb2.QuaConfig.MicrowaveAnalogInputPortDec.LoMode, lo_mode_value.upper()
                )
        else:
            self._validate_unsupported_params(
                data_with_defaults.keys(),
                unsupported_params=["lo_mode"],
                supported_from=QopCaps.lo_mode.from_qop_version,
            )

        return analog_input

    def _validate_invalid_sampling_rate_and_upsampling_mode(self, data: AnalogOutputPortConfigTypeOctoDac) -> None:
        # We check that a user explicitly tried to put upsampling mode (not the default value) with a non-compatible sampling rate
        if "upsampling_mode" in data and "sampling_rate" in data and data["sampling_rate"] != 1e9:
            raise ConfigValidationException("'upsampling_mode' is only relevant for 'sampling_rate' of 1GHz.")

        # A sampling rate of 1GHZ goes hand in hand with an upsampling mode, so when updating one of these values,
        # it has to be compatible with the other.
        if not self._init_mode:
            if "sampling_rate" in data and data["sampling_rate"] == 1e9 and "upsampling_mode" not in data:
                raise ConfigValidationException(
                    "'upsampling_mode' should be provided when updating 'sampling_rate' to 1GHZ."
                )

            if "upsampling_mode" in data and "sampling_rate" not in data:
                raise ConfigValidationException(
                    "'sampling_rate' of 1GHZ should be provided when updating 'upsampling_mode'."
                )

    def analog_output_port_to_pb(
        self,
        data: AnalogOutputPortConfigType,
        output_type: Type[AnalogOutputType],
    ) -> AnalogOutputType:
        default_schema: AnalogOutputPortConfigType = {"shareable": False, "offset": 0.0, "delay": 0}
        data_with_defaults = self._apply_defaults(data, default_schema)

        analog_output = output_type()
        shareable = data_with_defaults.get("shareable")
        if shareable is not None:
            analog_output.shareable = shareable

        offset = data_with_defaults.get("offset")
        if offset is not None:
            analog_output.offset = offset

        delay = data_with_defaults.get("delay")
        if delay is not None and delay < 0:
            raise ConfigValidationException(f"analog output delay cannot be a negative value, given value: {delay}")

        if delay is not None:
            analog_output.delay = delay

        if "filter" in data_with_defaults:
            analog_output.filter.CopyFrom(self._filters_converter.convert(data_with_defaults["filter"]))

        if "crosstalk" in data_with_defaults:
            if self._capabilities.supports(QopCaps.config_v2) and isinstance(
                analog_output, inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec
            ):
                crosstalk_in_pb = analog_output.crosstalk_v2.value
            else:
                crosstalk_in_pb = analog_output.crosstalk

            for k, v in data_with_defaults["crosstalk"].items():
                crosstalk_in_pb[int(k)] = v

        return analog_output

    def opx_1000_analog_output_port_to_pb(
        self,
        data: AnalogOutputPortConfigTypeOctoDac,
    ) -> inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec:
        item = self.analog_output_port_to_pb(data, output_type=inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec)
        self._validate_invalid_sampling_rate_and_upsampling_mode(data)

        default_schema: AnalogOutputPortConfigTypeOctoDac = {
            "sampling_rate": 1e9,
            "upsampling_mode": "mw",
            "output_mode": "direct",
        }
        data_with_defaults = self._apply_defaults(data, default_schema)

        self.update_sampling_rate_enum(item, data_with_defaults)

        if "output_mode" in data_with_defaults:
            output_mode = data_with_defaults.get("output_mode")
            if output_mode is None:
                raise ConfigValidationException("got None output_mode, expected literal")
            item.output_mode = getattr(
                inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec.OutputMode, cast(str, output_mode)
            )

        if self._capabilities.supports(QopCaps.port_voltage_limits):
            data_with_defaults = self._apply_defaults(  # type: ignore[assignment]
                data_with_defaults,
                default_schema={"min_voltage_limit": None, "max_voltage_limit": None},
            )

            if "min_voltage_limit" in data_with_defaults:
                min_voltage_limit = data_with_defaults.get("min_voltage_limit")
                item.min_voltage_limit.CopyFrom(
                    inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec.VoltageLimitContainer(
                        value=min_voltage_limit
                    )
                )

            if "max_voltage_limit" in data_with_defaults:
                max_voltage_limit = data_with_defaults.get("max_voltage_limit")
                item.max_voltage_limit.CopyFrom(
                    inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec.VoltageLimitContainer(
                        value=max_voltage_limit
                    )
                )

        else:
            self._validate_unsupported_params(
                data_with_defaults.keys(),
                unsupported_params=["min_voltage_limit", "max_voltage_limit"],
                supported_from=QopCaps.port_voltage_limits.from_qop_version,
            )

        return item

    @staticmethod
    def update_sampling_rate_enum(
        item: inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec,
        data_with_defaults: AnalogOutputPortConfigTypeOctoDac,
    ) -> None:
        """Also update the upsampling mode, as its value is tightly correlated to the sampling rate."""
        sampling_rate = data_with_defaults.get("sampling_rate")
        if sampling_rate is None:
            item.ClearField("sampling_rate")
            item.ClearField("upsampling_mode")
        else:
            if sampling_rate == 1e9:
                item.sampling_rate = inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec.SamplingRate.GSPS1
                item.upsampling_mode = getattr(
                    inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec.SamplingRateMode,
                    data_with_defaults["upsampling_mode"],
                )

            elif sampling_rate == 2e9:
                item.sampling_rate = inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec.SamplingRate.GSPS2
                item.upsampling_mode = inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec.SamplingRateMode.unset

            else:
                raise ValueError("Sampling rate should be either 1e9 or 2e9")

    def get_upconverters(
        self, data: MwFemAnalogOutputPortConfigType, data_with_defaults: MwFemAnalogOutputPortConfigType
    ) -> Union[None, Dict[int, inc_qua_config_pb2.QuaConfig.UpConverterConfigDec]]:
        upconverters = cast(
            Dict[int, inc_qua_config_pb2.QuaConfig.UpConverterConfigDec], data_with_defaults.get("upconverters")
        )
        if "upconverter_frequency" in data and "upconverters" in data:
            raise ConfigValidationException("Use either 'upconverter_frequency' or 'upconverters' but not both")
        if "upconverter_frequency" in data:
            upconverters = {
                DEFAULT_DUC_IDX: inc_qua_config_pb2.QuaConfig.UpConverterConfigDec(
                    frequency=data["upconverter_frequency"]
                )
            }
        else:
            if upconverters is not None:
                upconverters = {int(k): self.upconverter_config_dec_to_pb(v) for k, v in upconverters.items()}
            elif upconverters is None and self._init_mode:
                raise ConfigValidationException("You should declare at least one upconverter.")

        return cast(Union[None, Dict[int, inc_qua_config_pb2.QuaConfig.UpConverterConfigDec]], upconverters)

    def mw_fem_analog_output_to_pb(
        self,
        data: MwFemAnalogOutputPortConfigType,
    ) -> inc_qua_config_pb2.QuaConfig.MicrowaveAnalogOutputPortDec:
        if self._init_mode:
            self._validate_required_fields(data, ["band"], "microwave analog output port")

        default_schema: MwFemAnalogOutputPortConfigType = {
            "sampling_rate": 1e9,
            "full_scale_power_dbm": -11,
            "delay": 0,
            "shareable": False,
            "upconverters": {},
        }
        data_with_defaults = self._apply_defaults(data, default_schema)
        item = inc_qua_config_pb2.QuaConfig.MicrowaveAnalogOutputPortDec(
            samplingRate=data_with_defaults.get("sampling_rate"),
            fullScalePowerDbm=data_with_defaults.get("full_scale_power_dbm"),
            delay=data_with_defaults.get("delay"),
        )
        band = data_with_defaults.get("band")
        if band is not None:
            item.band = band
        shareable = data_with_defaults.get("shareable")
        if shareable is not None:
            item.shareable = shareable
        upconverters = self.get_upconverters(data, data_with_defaults)
        self._set_pb_attr_config_v2(item, upconverters, "upconverters", "upconverters_v2")

        return item

    def digital_input_port_to_pb(
        self, data: DigitalInputPortConfigType
    ) -> inc_qua_config_pb2.QuaConfig.DigitalInputPortDec:
        if self._init_mode:
            self._validate_required_fields(data, ["threshold", "polarity", "deadtime"], "digital input port")

        default_schema: DigitalInputPortConfigType = {"shareable": False}
        data_with_defaults = self._apply_defaults(data, default_schema=default_schema)

        digital_input = inc_qua_config_pb2.QuaConfig.DigitalInputPortDec(
            threshold=data_with_defaults.get("threshold"),
            level=inc_qua_config_pb2.QuaConfig.VoltageLevel.LVTTL,
            # The user is not supposed to edit this anymore, it should always be LVTTL. Up until now the gateway just always
            # put LVTTL here, but we are moving it here because the SDK is in charge of supplying defaults.
        )
        shareable = data_with_defaults.get("shareable")
        if shareable is not None:
            digital_input.shareable = shareable
        if "polarity" in data_with_defaults:
            if data_with_defaults["polarity"].upper() == "RISING":
                digital_input.polarity = inc_qua_config_pb2.QuaConfig.DigitalInputPortDec.Polarity.RISING
            elif data_with_defaults["polarity"].upper() == "FALLING":
                digital_input.polarity = inc_qua_config_pb2.QuaConfig.DigitalInputPortDec.Polarity.FALLING
            else:
                raise ConfigValidationException(f"Invalid polarity: {data_with_defaults['polarity']}")

        if "deadtime" in data_with_defaults:
            digital_input.deadtime = data_with_defaults["deadtime"]

        return digital_input

    def digital_output_port_to_pb(
        self, data: DigitalOutputPortConfigType
    ) -> inc_qua_config_pb2.QuaConfig.DigitalOutputPortDec:
        default_schema: DigitalOutputPortConfigType = {"shareable": False, "inverted": False}
        data_with_defaults = self._apply_defaults(data, default_schema)

        digital_output = inc_qua_config_pb2.QuaConfig.DigitalOutputPortDec(
            # The only currently supported level is LVTTL, so we set it always
            level=inc_qua_config_pb2.QuaConfig.VoltageLevel.LVTTL,
        )
        shareable = data_with_defaults.get("shareable")
        if shareable is not None:
            digital_output.shareable = shareable

        inverted = data_with_defaults.get("inverted")
        if inverted is not None:
            digital_output.inverted = inverted

        return digital_output

    @staticmethod
    def upconverter_config_dec_to_pb(
        data: Union[MwUpconverterConfigType, inc_qua_config_pb2.QuaConfig.UpConverterConfigDec],
    ) -> inc_qua_config_pb2.QuaConfig.UpConverterConfigDec:
        if isinstance(data, inc_qua_config_pb2.QuaConfig.UpConverterConfigDec):
            return data
        return inc_qua_config_pb2.QuaConfig.UpConverterConfigDec(frequency=data["frequency"])

    def deconvert(
        self, output_data: inc_qua_config_pb2.QuaConfig.DeviceDec
    ) -> Union[ControllerConfigType, OPX1000ControllerConfigType]:
        if len(output_data.fems) == 1 and 1 in output_data.fems:
            _, opx = which_one_of(output_data.fems[1], "fem_type_one_of")
            if isinstance(opx, inc_qua_config_pb2.QuaConfig.ControllerDec):
                return self._deconvert_controller(opx)

        return {
            "type": "opx1000",
            "fems": {cast(FEM_IDX, fem_idx): self._deconvert_fem(fem) for fem_idx, fem in output_data.fems.items()},
        }

    def _deconvert_controller(self, data: inc_qua_config_pb2.QuaConfig.ControllerDec) -> ControllerConfigType:
        return {
            "type": cast(Literal["opx", "opx1"], data.type),
            "analog_outputs": self._deconvert_controller_analog_outputs(data.analogOutputs),
            "analog_inputs": _deconvert_controller_analog_inputs(data.analogInputs, is_opx_plus_controller=True),
            "digital_outputs": _deconvert_controller_digital_outputs(data.digitalOutputs),
            "digital_inputs": _deconvert_controller_digital_inputs(data.digitalInputs),
        }

    def _deconvert_fem(self, data: inc_qua_config_pb2.QuaConfig.FEMTypes) -> Union[LfFemConfigType, MwFemConfigType]:
        _, fem_config = which_one_of(data, "fem_type_one_of")
        if isinstance(fem_config, inc_qua_config_pb2.QuaConfig.OctoDacFemDec):
            return self._deconvert_octo_dac(fem_config)
        elif isinstance(fem_config, inc_qua_config_pb2.QuaConfig.MicrowaveFemDec):
            return self._deconvert_mw_fem(fem_config)
        else:
            raise ValueError(f"Unknown FEM type - {fem_config}")

    def _deconvert_mw_fem(self, data: inc_qua_config_pb2.QuaConfig.MicrowaveFemDec) -> MwFemConfigType:
        ret: MwFemConfigType = {"type": "MW"}
        if data.analogOutputs:
            ret["analog_outputs"] = self._deconvert_mw_analog_outputs(data.analogOutputs)
        if data.analogInputs:
            ret["analog_inputs"] = self._deconvert_mw_analog_inputs(data.analogInputs)
        if data.digitalOutputs:
            ret["digital_outputs"] = _deconvert_controller_digital_outputs(data.digitalOutputs)
        if data.digitalInputs:
            ret["digital_inputs"] = _deconvert_controller_digital_inputs(data.digitalInputs)
        return ret

    def _deconvert_controller_analog_outputs(
        self, outputs: MutableMapping[int, inc_qua_config_pb2.QuaConfig.AnalogOutputPortDec]
    ) -> Mapping[Union[int, str], AnalogOutputPortConfigType]:
        ret: Mapping[Union[int, str], AnalogOutputPortConfigType] = {
            int(name): self._deconvert_single_analog_output(data) for name, data in outputs.items()
        }
        return ret

    def _deconvert_single_analog_output(
        self, data: inc_qua_config_pb2.QuaConfig.AnalogOutputPortDec
    ) -> AnalogOutputPortConfigType:
        ret = cast(
            AnalogOutputPortConfigType,
            {
                "offset": data.offset,
                "delay": data.delay,
                "shareable": data.shareable,
                "filter": self._filters_converter.deconvert(data.filter),
                "crosstalk": data.crosstalk,
            },
        )
        return ret

    def _deconvert_mw_analog_outputs(
        self,
        outputs: MutableMapping[int, inc_qua_config_pb2.QuaConfig.MicrowaveAnalogOutputPortDec],
    ) -> Mapping[Union[int, str], MwFemAnalogOutputPortConfigType]:
        return {idx: self._deconvert_single_mw_analog_output(output) for idx, output in outputs.items()}

    def _deconvert_mw_analog_inputs(
        self,
        inputs: MutableMapping[int, inc_qua_config_pb2.QuaConfig.MicrowaveAnalogInputPortDec],
    ) -> Mapping[Union[int, str], MwFemAnalogInputPortConfigType]:
        return {idx: self._deconvert_single_mw_analog_input(_input) for idx, _input in inputs.items()}

    def _deconvert_single_mw_analog_input(
        self, data: inc_qua_config_pb2.QuaConfig.MicrowaveAnalogInputPortDec
    ) -> MwFemAnalogInputPortConfigType:
        ret = cast(
            MwFemAnalogInputPortConfigType,
            {
                "band": cast(Literal[1, 2, 3], data.band),
                "shareable": data.shareable,
                "gain_db": data.gain_db,
                "sampling_rate": data.samplingRate,
                "downconverter_frequency": data.downconverter.frequency,
            },
        )
        if self._capabilities.supports(QopCaps.lo_mode):
            ret["lo_mode"] = cast(
                Literal["auto", "always_on"],
                inc_qua_config_pb2.QuaConfig.MicrowaveAnalogInputPortDec.LoMode.Name(data.lo_mode).lower(),
            )
        return ret

    def _deconvert_octo_dac(self, data: inc_qua_config_pb2.QuaConfig.OctoDacFemDec) -> LfFemConfigType:
        ret: LfFemConfigType = {"type": "LF"}
        if data.analogOutputs:
            ret["analog_outputs"] = self._deconvert_octo_dac_fem_analog_outputs(data.analogOutputs)
        if data.analogInputs:
            ret["analog_inputs"] = _deconvert_controller_analog_inputs(data.analogInputs)
        if data.digitalOutputs:
            ret["digital_outputs"] = _deconvert_controller_digital_outputs(data.digitalOutputs)
        if data.digitalInputs:
            ret["digital_inputs"] = _deconvert_controller_digital_inputs(data.digitalInputs)
        return ret

    def _deconvert_single_octo_dac_fem_analog_output(
        self,
        data: inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec,
    ) -> AnalogOutputPortConfigTypeOctoDac:
        ret = cast(
            AnalogOutputPortConfigTypeOctoDac,
            {
                "offset": data.offset,
                "delay": data.delay,
                "shareable": data.shareable,
                "filter": self._filters_converter.deconvert(data.filter),
                "crosstalk": (
                    data.crosstalk_v2.value if self._capabilities.supports(QopCaps.config_v2) else data.crosstalk
                ),
            },
        )
        if data.sampling_rate:
            ret["sampling_rate"] = {1: 1e9, 2: 2e9}[data.sampling_rate]
        if data.upsampling_mode:
            ret["upsampling_mode"] = cast(
                Literal["mw", "pulse"],
                inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec.SamplingRateMode.Name(data.upsampling_mode),
            )
        if data.output_mode is not None:  # We check for "is not None" because the 0 value is valid
            ret["output_mode"] = cast(
                Literal["direct", "amplified"],
                inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec.OutputMode.Name(data.output_mode),
            )
        if self._capabilities.supports(QopCaps.port_voltage_limits):
            ret["min_voltage_limit"] = (
                data.min_voltage_limit.value
                if data.HasField("min_voltage_limit") and data.min_voltage_limit.HasField("value")
                else None
            )
            ret["max_voltage_limit"] = (
                data.max_voltage_limit.value
                if data.HasField("max_voltage_limit") and data.max_voltage_limit.HasField("value")
                else None
            )

        return ret

    def _deconvert_octo_dac_fem_analog_outputs(
        self,
        outputs: MutableMapping[int, inc_qua_config_pb2.QuaConfig.OctoDacAnalogOutputPortDec],
    ) -> Mapping[Union[int, str], AnalogOutputPortConfigTypeOctoDac]:
        ret: Mapping[Union[int, str], AnalogOutputPortConfigTypeOctoDac] = {
            int(name): self._deconvert_single_octo_dac_fem_analog_output(data) for name, data in outputs.items()
        }
        return ret

    def _deconvert_single_mw_analog_output(
        self, data: inc_qua_config_pb2.QuaConfig.MicrowaveAnalogOutputPortDec
    ) -> MwFemAnalogOutputPortConfigType:
        upconverters = (
            data.upconverters_v2.value if self._capabilities.supports(QopCaps.config_v2) else data.upconverters
        )
        ret = cast(
            MwFemAnalogOutputPortConfigType,
            {
                "sampling_rate": data.samplingRate,
                "full_scale_power_dbm": data.fullScalePowerDbm,
                "band": cast(Band, data.band),
                "delay": data.delay,
                "shareable": data.shareable,
                "upconverters": {cast(Upconverter, k): {"frequency": v.frequency} for k, v in upconverters.items()},
            },
        )
        return ret


def _deconvert_controller_analog_inputs(
    inputs: Mapping[int, inc_qua_config_pb2.QuaConfig.AnalogInputPortDec], is_opx_plus_controller: bool = False
) -> Mapping[Union[int, str], AnalogInputPortConfigType]:
    ret: Mapping[Union[int, str], AnalogInputPortConfigType] = {
        idx: _deconvert_controller_analog_input(data, is_opx_plus_controller) for idx, data in inputs.items()
    }
    return ret


def _deconvert_controller_analog_input(
    data: inc_qua_config_pb2.QuaConfig.AnalogInputPortDec, is_opx_plus_controller: bool
) -> AnalogInputPortConfigType:
    sampling_rate = data.samplingRate
    if is_opx_plus_controller and not data.samplingRate:
        sampling_rate = 1e9  # For OPX+ controllers, the get_config always returns 0, but we know it is 1e9 (the only allowed value for OPX+)

    ret = cast(
        AnalogInputPortConfigType,
        {
            "offset": data.offset,
            "gain_db": data.gainDb.value if data.gainDb is not None else 0,
            "shareable": data.shareable,
            "sampling_rate": sampling_rate,
        },
    )
    return ret


def _deconvert_controller_digital_outputs(
    outputs: MutableMapping[int, inc_qua_config_pb2.QuaConfig.DigitalOutputPortDec],
) -> Mapping[Union[int, str], DigitalOutputPortConfigType]:
    return {idx: _deconvert_controller_digital_output(data) for idx, data in outputs.items()}


def _deconvert_controller_digital_output(
    data: inc_qua_config_pb2.QuaConfig.DigitalOutputPortDec,
) -> DigitalOutputPortConfigType:
    to_return = cast(
        DigitalOutputPortConfigType,
        {
            "shareable": data.shareable,
            "inverted": data.inverted,
        },
    )
    return to_return


def _deconvert_controller_digital_inputs(
    inputs: MutableMapping[int, inc_qua_config_pb2.QuaConfig.DigitalInputPortDec],
) -> Mapping[Union[int, str], DigitalInputPortConfigType]:
    return {idx: _deconvert_digital_input(data) for idx, data in inputs.items()}


def _deconvert_digital_input(data: inc_qua_config_pb2.QuaConfig.DigitalInputPortDec) -> DigitalInputPortConfigType:
    to_return = cast(
        DigitalInputPortConfigType,
        {
            "deadtime": data.deadtime,
            "threshold": data.threshold,
            "shareable": data.shareable,
        },
    )
    if data.polarity is not None:
        to_return["polarity"] = cast(
            Literal["RISING", "FALLING"], inc_qua_config_pb2.QuaConfig.DigitalInputPortDec.Polarity.Name(data.polarity)
        )

    return to_return
