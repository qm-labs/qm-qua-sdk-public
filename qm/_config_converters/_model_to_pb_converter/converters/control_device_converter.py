from collections.abc import Mapping, Collection

from qm.utils.protobuf_utils import which_one_of
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm.api.models.capabilities import ServerCapabilities
from qm.config._ports._port_base import Port, LfFem, MwFem, Opx1000, OpxPlus, PortReference
from qm._config_converters._model_to_pb_converter.base_converter import BaseModelToPbConverter
from qm._config_converters._model_to_pb_converter.converters.fem_converters.opx_converter import OpxToPbConverter
from qm._config_converters.split_ports_by_fems import FemDataOpx, FemDataOctoDac, FemDataMicrowave, split_to_fems
from qm._config_converters._model_to_pb_converter.converters.fem_converters.mw_converter import MwFemToPbConverter
from qm._config_converters._model_to_pb_converter.converters.fem_converters.lf_fem_converter import LfFemToPbConverter


class ControlDeviceConverter(BaseModelToPbConverter[Collection[Port], Mapping[str, QuaConfig.DeviceDec]]):
    def __init__(self, capabilities: ServerCapabilities, init_mode: bool) -> None:
        super().__init__(capabilities, init_mode)
        self._opx_converter = OpxToPbConverter(capabilities, init_mode)
        self._lf_fem_converter = LfFemToPbConverter(capabilities, init_mode)
        self._mw_fem_converter = MwFemToPbConverter(capabilities, init_mode)

    def convert(self, input_data: Collection[Port]) -> Mapping[str, QuaConfig.DeviceDec]:
        # todo - validate compatibility of ports
        real_ports = [p for p in input_data if not isinstance(p, PortReference)]
        data_split_by_fems = split_to_fems(real_ports)
        to_return: dict[str, QuaConfig.DeviceDec] = {}
        for controller_name, controller_data in data_split_by_fems.items():
            fems = {}
            for fem_idx, fem_data in controller_data.items():
                if isinstance(fem_data, FemDataOpx):
                    opx_pb = self._opx_converter.convert(fem_data)
                    fems[fem_idx] = QuaConfig.FEMTypes(opx=opx_pb)
                elif isinstance(fem_data, FemDataOctoDac):
                    lf_fem_pb = self._lf_fem_converter.convert(fem_data)
                    fems[fem_idx] = QuaConfig.FEMTypes(octo_dac=lf_fem_pb)
                elif isinstance(fem_data, FemDataMicrowave):
                    mw_fem_pb = self._mw_fem_converter.convert(fem_data)
                    fems[fem_idx] = QuaConfig.FEMTypes(microwave=mw_fem_pb)
                else:
                    raise TypeError(f"Unsupported fem data type: {fem_data}")
            to_return[controller_name] = QuaConfig.DeviceDec(fems=fems)
        return to_return

    def deconvert(self, output_data: Mapping[str, QuaConfig.DeviceDec]) -> Collection[Port]:
        to_return: list[Port] = []
        for name, data in output_data.items():
            ports = self._deconvert_single_controller(data, name)
            to_return.extend(ports)
        return to_return

    def _deconvert_single_controller(self, output_data: QuaConfig.DeviceDec, name: str) -> Collection[Port]:
        if len(output_data.fems) == 1 and 1 in output_data.fems:
            _, opx = which_one_of(output_data.fems[1], "fem_type_one_of")
            if isinstance(opx, QuaConfig.ControllerDec):
                opx_plus = OpxPlus(name=name)
                opx_data = self._opx_converter.deconvert(opx, opx_plus)
                return (
                    opx_data.analog_outputs
                    + opx_data.analog_inputs
                    + opx_data.digital_outputs
                    + opx_data.digital_inputs
                )

        opx1000 = Opx1000(name=name)
        to_return: tuple[Port, ...] = tuple()
        for fem_idx, fem in output_data.fems.items():
            curr = self._deconvert_fem(fem, controller=opx1000, fem_idx=fem_idx)
            to_return += tuple(curr)
        return to_return

    def _deconvert_fem(self, data: QuaConfig.FEMTypes, controller: Opx1000, fem_idx: int) -> Collection[Port]:
        _, fem_config = which_one_of(data, "fem_type_one_of")
        if isinstance(fem_config, QuaConfig.OctoDacFemDec):
            lf_fem = LfFem(controller=controller, index=fem_idx)
            lf_data = self._lf_fem_converter.deconvert(fem_config, lf_fem)
            return lf_data.analog_outputs + lf_data.analog_inputs + lf_data.digital_outputs + lf_data.digital_inputs
        elif isinstance(fem_config, QuaConfig.MicrowaveFemDec):
            mw_fem = MwFem(controller=controller, index=fem_idx)
            mw_data = self._mw_fem_converter.deconvert(fem_config, mw_fem)
            return mw_data.analog_outputs + mw_data.analog_inputs + mw_data.digital_outputs + mw_data.digital_inputs
        else:
            raise ValueError(f"Unknown FEM type - {fem_config}")
