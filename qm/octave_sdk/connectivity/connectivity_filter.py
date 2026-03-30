import copy
from typing import List, TypeVar, Optional, MutableSequence

from qm.grpc.octave.v1 import api_pb2
from qm.octave_sdk._octave_client import ExploreResult
from qm.octave_sdk.connectivity.exceptions import ExploreResponseException
from qm.octave_sdk.connectivity.connectivity_util_private import (
    IfSourceType,
    RfSourceType,
    get_if_source_type,
    get_rf_source_type,
    get_rf_source_from_synth_panel_output,
    identity_object_to_module_ref_type_mapping,
)

_T = TypeVar(
    "_T", api_pb2.RFUpConvIdentity, api_pb2.RFDownConvIdentity, api_pb2.IFDownConvIdentity, api_pb2.SynthIdentity
)


# Must be called after self._identity_response is copied from the original identity
class FilteredWorkingModules:
    def __init__(
        self,
        identity_response_original: api_pb2.IdentifyResponse,
        explore_result: ExploreResult,
    ) -> None:
        self.identity_response_filtered: api_pb2.IdentifyResponse = copy.deepcopy(identity_response_original)
        self.missing_modules: List[api_pb2.ModuleReference] = []
        self._filter_by_working_modules(explore_result)

    def _filter_by_working_modules(self, explore_result: ExploreResult) -> None:
        if not isinstance(explore_result, ExploreResult):
            raise ExploreResponseException("Wrong explore response object")

        # ------Start with plain module removal-----
        self._filter_by_identity_module_and_explore_module(
            self.identity_response_filtered.rf_up_converters,
            explore_result.modules[api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER],
        )
        self._filter_by_identity_module_and_explore_module(
            self.identity_response_filtered.rf_down_converters,
            explore_result.modules[api_pb2.OctaveModule.OCTAVE_MODULE_RF_DOWNCONVERTER],
        )
        self._filter_by_identity_module_and_explore_module(
            self.identity_response_filtered.if_down_converters,
            explore_result.modules[api_pb2.OctaveModule.OCTAVE_MODULE_IF_DOWNCONVERTER],
        )
        self._filter_by_identity_module_and_explore_module(
            self.identity_response_filtered.synthesizers,
            explore_result.modules[api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER],
        )

        # -----Work on input wiring, go from back to front-----
        synths = [uc.index for uc in self.identity_response_filtered.synthesizers]

        # panel outputs - remove all synths
        self._remove_synths_from_panel_output(synths)

        # RF up - remove all synths
        self._remove_synths_from_rf_up(synths)

        # RF down - remove all synths and Upconv
        self._remove_synths_and_rf_up_from_rf_out(synths)

        # IF down - remove all Down conv
        self._remove_rf_down_from_if()

    def _remove_rf_down_from_if(self) -> None:
        rf_ins = [uc.index for uc in self.identity_response_filtered.rf_down_converters]
        if_convs = self.identity_response_filtered.if_down_converters
        for if_conv in if_convs[:]:
            all_vars = [getattr(if_conv.connectivity, f.name) for f in if_conv.connectivity.DESCRIPTOR.fields]
            if_source_fields: List[api_pb2.IFSource] = [
                rf_source for rf_source in all_vars if isinstance(rf_source, api_pb2.IFSource)
            ]

            for if_source in if_source_fields:
                source_type = get_if_source_type(if_source)
                if source_type == IfSourceType.rf_downconv_if_source:
                    if if_source.rf_downconv_if_source.index not in rf_ins:
                        if_source.ClearField("rf_downconv_if_source")
                        if_source.constant_source = api_pb2.ConstantSource.CONSTANT_SOURCE_OPEN

    def _remove_synths_and_rf_up_from_rf_out(self, synths: List[int]) -> None:
        rf_outs = [uc.index for uc in self.identity_response_filtered.rf_up_converters]
        down_convs = self.identity_response_filtered.rf_down_converters
        for down_conv in down_convs[:]:
            all_vars = [getattr(down_conv.connectivity, f.name) for f in down_conv.connectivity.DESCRIPTOR.fields]
            rf_source_fields: List[api_pb2.RFSource] = [
                rf_source for rf_source in all_vars if isinstance(rf_source, api_pb2.RFSource)
            ]

            for rf_source in rf_source_fields:
                source_type = get_rf_source_type(rf_source)
                if source_type == RfSourceType.synth_output:
                    if rf_source.synth_output.index not in synths:
                        rf_source.ClearField("synth_output")
                        rf_source.constant_source = api_pb2.ConstantSource.CONSTANT_SOURCE_OPEN
                elif source_type == RfSourceType.rf_up_conv_output and rf_source.rf_up_conv_output.index not in rf_outs:
                    rf_source.ClearField("rf_up_conv_output")
                    rf_source.constant_source = api_pb2.ConstantSource.CONSTANT_SOURCE_OPEN

    def _remove_synths_from_rf_up(self, synths: List[int]) -> None:
        up_convs = self.identity_response_filtered.rf_up_converters
        for up_conv in up_convs[:]:
            source = up_conv.connectivity.lo_input
            source_type = get_rf_source_type(source)
            if source_type == RfSourceType.synth_output:
                if source.synth_output.index not in synths:
                    up_conv.connectivity.lo_input.CopyFrom(
                        api_pb2.RFSource(constant_source=api_pb2.ConstantSource.CONSTANT_SOURCE_OPEN)
                    )
            elif source_type == RfSourceType.rf_up_conv_output:
                raise ValueError(f"LO Source {source_type} is not supported")

    def _remove_synths_from_panel_output(self, synths: List[int]) -> None:
        synth_outputs = self.identity_response_filtered.panel_identity.synth_outputs
        remove_list = []
        for panel_synth in synth_outputs:
            source = get_rf_source_from_synth_panel_output(panel_synth.source)
            if source.index not in synths:
                remove_list.append(panel_synth)

        for panel_synth in remove_list:
            synth_outputs.remove(panel_synth)

    def _filter_by_identity_module_and_explore_module(
        self, identity_modules: MutableSequence[_T], explore_modules: List[Optional[str]]
    ) -> None:
        index_list = [i for i, v in enumerate(explore_modules) if v is not None]
        remove_list = []
        for module in identity_modules:
            if (module.index - 1) not in index_list:
                self.missing_modules.append(
                    api_pb2.ModuleReference(
                        type=identity_object_to_module_ref_type_mapping[type(module)], index=module.index
                    )
                )
                remove_list.append(module)

        for module in remove_list:
            identity_modules.remove(module)
