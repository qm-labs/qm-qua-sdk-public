import copy
import time
import logging
import dataclasses
from pprint import PrettyPrinter
from typing import Any, Dict, List, Tuple, Union, Callable, Optional, Sequence, NamedTuple, cast

import grpc
from google.protobuf.json_format import ParseDict, MessageToDict

from qm.grpc.octave.v1 import api_pb2
from qm.utils.protobuf_utils import which_one_of
from qm.octave_sdk.batch import Batched, BatchSingleton
from qm.grpc.octave.v1.api_pb2_grpc import OctaveServiceStub
from qm.octave_sdk.connectivity.connectivity_util import (
    slot_index_to_panel_mapping,
    octave_module_to_module_name_mapping,
)

logger = logging.getLogger("qm")

"""
# OctaveClient
#
#   This is a gRPC based Octave. The standard setup is the whole Octave product.
#   Namely, we access the SOM on its motherboard via ethernet and from there
#   communicate with all the boards via the main PIC.
#
#   A temporary alternative is using a mini SOM eval board which is connected
#   to a mini motherboard, directly into the serial lines of its PIC.
#
#   The specific variation is passed to the constructor.
"""

module_type_to_class = {
    api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER: "rf_up_conv",
    api_pb2.OctaveModule.OCTAVE_MODULE_RF_DOWNCONVERTER: "rf_down_conv",
    api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER: "synth",
    api_pb2.OctaveModule.OCTAVE_MODULE_IF_DOWNCONVERTER: "if_down_conv",
    api_pb2.OctaveModule.OCTAVE_MODULE_MOTHERBOARD: "motherboard",
}


class DebugSetException(Exception):
    pass


def _build_grpc_channel(
    host: str,
    port: int,
    octave_name: Optional[str] = None,
    credentials: Optional[grpc.ChannelCredentials] = None,
    options: Optional[List[tuple[str, int]]] = None,
) -> grpc.Channel:
    target = f"{host}:{port}"

    # Default options for message size
    default_options = [
        ("grpc.max_receive_message_length", 100 * 1024 * 1024),
        ("grpc.max_send_message_length", 100 * 1024 * 1024),
    ]

    if options:
        default_options.extend(options)

    if credentials:
        channel = grpc.secure_channel(target, credentials, options=default_options)
    else:
        channel = grpc.insecure_channel(target, options=default_options)

    return channel


@dataclasses.dataclass
class MonitorData:
    temp: float
    errors: List[api_pb2.MonitorResponse.ModuleStatusError]


class MonitorResult:
    def __init__(self, results_pb: api_pb2.MonitorResponse):
        rf_upconverters: List[Optional[MonitorData]] = [None for _ in range(5)]
        rf_downconverters: List[Optional[MonitorData]] = [None for _ in range(2)]
        if_downconverters: List[Optional[MonitorData]] = [None for _ in range(2)]
        synthesizers: List[Optional[MonitorData]] = [None for _ in range(6)]
        motherboard: List[Optional[MonitorData]] = [None for _ in range(1)]
        self.modules: Dict[api_pb2.OctaveModule, List[Optional[MonitorData]]] = {
            api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER: rf_upconverters,
            api_pb2.OctaveModule.OCTAVE_MODULE_RF_DOWNCONVERTER: rf_downconverters,
            api_pb2.OctaveModule.OCTAVE_MODULE_IF_DOWNCONVERTER: if_downconverters,
            api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER: synthesizers,
            api_pb2.OctaveModule.OCTAVE_MODULE_SOM: motherboard,
        }
        for module in results_pb.modules:
            self.modules[module.module.type][module.module.index - 1] = MonitorData(
                temp=module.temperature, errors=list(module.errors)
            )

    def __repr__(self) -> str:
        pp = PrettyPrinter(width=150)
        return pp.pformat(self.modules)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MonitorResult):
            return False
        # Basically compare all elements except temp
        self_copy = copy.deepcopy(self)
        self._clear_temp_values(self_copy)
        other_copy = copy.deepcopy(other)
        self._clear_temp_values(other_copy)

        return self_copy.modules == other_copy.modules

    def _clear_temp_values(self, monitor_result: "MonitorResult") -> None:
        for module_list in monitor_result.modules.values():
            for monitor_data in module_list:
                if monitor_data is not None:
                    monitor_data.temp = 0

    @property
    def temperatures(self) -> Dict[str, float]:
        res = {}
        for module_type, module_list in self.modules.items():
            for index, monitor_data in enumerate(module_list):
                if monitor_data is not None:
                    key = f"{octave_module_to_module_name_mapping[module_type]} {slot_index_to_panel_mapping(index + 1, module_type)}"
                    res[key] = monitor_data.temp
        return res


class ExploreResult:
    def __init__(self, results_pb: api_pb2.ExploreResponse):
        rf_upconverters: List[Optional[str]] = [None for _ in range(5)]
        rf_downconverters: List[Optional[str]] = [None for _ in range(2)]
        if_downconverters: List[Optional[str]] = [None for _ in range(2)]
        synthesizers: List[Optional[str]] = [None for _ in range(6)]
        motherboard: List[Optional[str]] = [None for _ in range(1)]
        self.modules = {
            api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER: rf_upconverters,
            api_pb2.OctaveModule.OCTAVE_MODULE_RF_DOWNCONVERTER: rf_downconverters,
            api_pb2.OctaveModule.OCTAVE_MODULE_IF_DOWNCONVERTER: if_downconverters,
            api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER: synthesizers,
            api_pb2.OctaveModule.OCTAVE_MODULE_MOTHERBOARD: motherboard,
        }
        for module in results_pb.modules:
            self.modules[module.module.type][module.module.index - 1] = module.id

    def __repr__(self) -> str:
        module_types = [
            api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER,
            api_pb2.OctaveModule.OCTAVE_MODULE_RF_DOWNCONVERTER,
            api_pb2.OctaveModule.OCTAVE_MODULE_IF_DOWNCONVERTER,
            api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER,
        ]

        m_id = self.modules[api_pb2.OctaveModule.OCTAVE_MODULE_MOTHERBOARD][0]
        if m_id is None or m_id == "":
            res = "MOTHERBOARD [\x1b[38;5;208m?? ?\x1b[0m]\n"
        else:
            res = f"MOTHERBOARD [\x1b[38;5;154m{m_id}\x1b[0m]\n"

        res += "    RF_UPCONVs          RF_DOWNCONVs        IF_DOWNCONVs        " "SYNTHESIZERs\n"
        for index in range(6):
            res += "     "
            for t in module_types:
                if index < len(self.modules[t]):
                    m_id = self.modules[t][index]
                    if m_id is None:
                        res += f"\x1b[38;5;241m{index + 1}. {'---':17s}\x1b[0m"
                    elif m_id == "":
                        res += f"{index + 1}. \x1b[38;5;208m{'???':17s}\x1b[0m"
                    else:
                        res += f"{index + 1}. \x1b[38;5;154m{m_id:17s}\x1b[0m"
                else:
                    res += f"{'':20s}"
            res += "\n"
        return res


MetadataValue = Union[str, bytes]


class _ClientCallDetails(NamedTuple):
    method: str
    timeout: Optional[float]
    metadata: Optional[Sequence[Tuple[str, MetadataValue]]]
    credentials: Optional[grpc.CallCredentials]
    wait_for_ready: Optional[bool]


class OctaveMetadataInterceptor(grpc.UnaryUnaryClientInterceptor):
    """Interceptor to add custom metadata to all gRPC calls"""

    def __init__(self, metadata: Dict[str, str]) -> None:
        self._metadata: List[Tuple[str, str]] = list(metadata.items())

    def intercept_unary_unary(
        self,
        continuation: Callable[..., Any],
        client_call_details: grpc.ClientCallDetails,
        request: Any,
    ) -> Any:
        # Add custom metadata to the call
        new_metadata: List[Tuple[str, Union[str, bytes]]] = list(client_call_details.metadata or [])
        new_metadata.extend(self._metadata)

        new_details = _ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=new_metadata,
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )

        return continuation(new_details, request)


class OctaveClient(Batched):
    def __init__(
        self,
        host: str,
        port: int,
        octave_name: Optional[str] = None,
        connection_headers: Optional[Dict[str, str]] = None,
        credentials: Optional[grpc.ChannelCredentials] = None,
        options: Optional[List[tuple[str, int]]] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._octave_name = octave_name or "null"
        self._headers = connection_headers or {}
        super().__init__()

        # Create the channel
        self._channel = _build_grpc_channel(host, port, octave_name, credentials, options)

        # Create interceptor for headers if needed
        if self._headers:
            interceptor = OctaveMetadataInterceptor(self._headers)
            self._channel = grpc.intercept_channel(self._channel, interceptor)

        # Add octave service header if specified
        if octave_name is not None:
            octave_interceptor = OctaveMetadataInterceptor({"x-grpc-service": octave_name})
            self._channel = grpc.intercept_channel(self._channel, octave_interceptor)

        self._service = OctaveServiceStub(self._channel)  # type: ignore[no-untyped-call]

    def __hash__(self) -> int:
        return hash((self._octave_name, self._host, self._port) + tuple(sorted(self._headers.items())))

    @property
    def name(self) -> str:
        return self._octave_name

    def __del__(self) -> None:
        self._service = None  # type: ignore[assignment]
        self._channel.close()

    def _control(self, w_data: bytes = b"", r_length: int = 0) -> api_pb2.ControlResponse:
        control_request = api_pb2.ControlRequest(w_data=w_data, r_length=r_length)
        return cast(api_pb2.ControlResponse, self._service.Control(control_request))

    def _format_cached_modules(self, modules: api_pb2.AquireResponse) -> None:
        cached_modules = {}
        for update in modules.state.updates:
            module_type, message = which_one_of(update, "update")
            if isinstance(
                message,
                (api_pb2.RFUpConvUpdate, api_pb2.RFDownConvUpdate, api_pb2.IFDownConvUpdate, api_pb2.SynthUpdate),
            ):
                update_id = message.index
            else:
                update_id = 0

            cache_key = (update_id, module_type)
            cached_modules[cache_key] = update
        BatchSingleton().set_cached_modules(self, cached_modules)

    def _start_batch_callback(self) -> None:
        self._format_cached_modules(self.acquire_all_modules())

    def _end_batch_callback(self) -> None:
        self._send_update(list(BatchSingleton().get_cached_updates(self).values()))

    def update(self, updates: List[api_pb2.SingleUpdate]) -> None:
        if BatchSingleton().is_batch_mode:
            for update in updates:
                self._cache_update(update)
        else:
            self._send_update(updates)

    def _cache_update(self, update: api_pb2.SingleUpdate) -> None:
        module_type, message = which_one_of(update, "update")

        if isinstance(
            message, (api_pb2.RFUpConvUpdate, api_pb2.RFDownConvUpdate, api_pb2.IFDownConvUpdate, api_pb2.SynthUpdate)
        ):
            update_id = message.index
        else:
            update_id = 0

        cache_key = (update_id, module_type)
        current_updates = BatchSingleton().get_cached_updates(self)
        if current_updates.get(cache_key):
            previous_cached_update = MessageToDict(getattr(current_updates.get(cache_key), module_type))
        else:
            previous_cached_update = {}

        assert message is not None
        previous_cached_update.update(MessageToDict(message))

        new_update = api_pb2.SingleUpdate()
        ParseDict(previous_cached_update, getattr(new_update, module_type))
        current_updates[cache_key] = new_update
        BatchSingleton().set_cached_updates(self, current_updates)

    def _send_update(self, updates: List[api_pb2.SingleUpdate]) -> api_pb2.UpdateResponse:
        update_request = api_pb2.UpdateRequest(updates=updates)
        response = self._service.Update(update_request)
        if not response.success:
            raise Exception(f"Octave update failed: {response.error_message}")
        return cast(api_pb2.UpdateResponse, response)

    def debug_request_clock_print(self) -> None:
        self._control(
            w_data=bytes([0xFF, 0xB9]),
            r_length=1,
        )

    def debug_set(
        self,
        monitor_enabled: Optional[bool] = None,
        monitor_timeout: Optional[int] = None,
        monitor_print_rate: Optional[int] = None,
        monitor_update_fan: Optional[bool] = None,
        uart_debug_mode: Optional[bool] = None,
        print_updates: Optional[bool] = None,
        min_fan_speed: Optional[bool] = None,
        min_temp: Optional[int] = None,
        max_temp_modules: Optional[int] = None,
        max_temp_fpga: Optional[int] = None,
    ) -> None:
        if monitor_timeout is not None:
            if monitor_timeout < 1 or monitor_timeout > 15:
                print("OctaveClientBase.debug_set   ERROR    monitor_timeout should be" " 1..15")
                return
        else:
            monitor_timeout = 0x00

        if monitor_print_rate is not None:
            if monitor_print_rate < 0 or monitor_print_rate > 255:
                print(
                    "OctaveClientBase.debug_set   ERROR    monitor_print_rate should either 0 (no printings) or 1..255"
                )
                return

        activate = 0x00
        state = 0x00

        if monitor_enabled is not None:
            activate |= 0x01
            state |= 0x01 if monitor_enabled else 0x00

        if uart_debug_mode is not None:
            activate |= 0x02
            state |= 0x02 if uart_debug_mode else 0x00

        if print_updates is not None:
            activate |= 0x04
            state |= 0x04 if print_updates else 0x00

        if monitor_print_rate is not None:
            activate |= 0x08
        else:
            monitor_print_rate = 0

        if monitor_update_fan is not None:
            activate |= 0x10
            state |= 0x10 if monitor_update_fan else 0x00

        if min_fan_speed is not None:
            activate |= 0x20
            min_fan_speed = min(int(min_fan_speed), 31)  # type: ignore[assignment]
            # Not sure what's going on here, where min_fan_speed is actually a bool
            state |= (min_fan_speed & 1) << 5
            monitor_timeout |= (min_fan_speed & 0x1E) << 3

        if min_temp is not None:
            if min_temp < 1 or min_temp > 60:
                print("OctaveClientBase.debug_set   ERROR    min_temp should be between 1 to 60")
                return
            activate |= 0x40
        else:
            min_temp = 0x00

        if (max_temp_modules and not max_temp_fpga) or (max_temp_fpga and not max_temp_modules):
            logger.error("max_temp_modules and max_temp_fpga must come in paris")
            return

        if max_temp_modules and max_temp_fpga:
            if max_temp_modules < 1 or max_temp_modules > 65:
                print("OctaveClientBase.debug_set   ERROR    max_temp_modlues should be between 1 to 65")
                return
            if max_temp_fpga < 1 or max_temp_fpga > 75:
                print("OctaveClientBase.debug_set   ERROR    max_temp_fpga should be between 1 to 75")
                return
            activate |= 0x80
        else:
            max_temp_modules = 0
            max_temp_fpga = 0

        control_payload_old: bytes = bytes(
            [
                0xFF,
                0xFF,
                activate,
                state,
                monitor_timeout,
                monitor_print_rate,
            ]
        )

        control_payload_new = control_payload_old + bytes(
            [
                min_temp,
                max_temp_modules,
                max_temp_fpga,
            ]
        )

        # Try new format
        res = (
            self._control(
                w_data=control_payload_new,
                r_length=1,
            )
        ).r_data
        res_int = int.from_bytes(res, "little")
        if res_int == api_pb2.ControlResponse.RdataDebug.RDATA_DEBUG_SUCCESS_RESPONSE:
            return

        # Fall back to old format
        res = (
            self._control(
                w_data=control_payload_old,
                r_length=1,
            )
        ).r_data
        res_int = int.from_bytes(res, "little")
        if res_int != api_pb2.ControlResponse.RdataDebug.RDATA_DEBUG_SUCCESS_RESPONSE:
            raise DebugSetException("Failed to set debug params")

    def save_modules(
        self,
        m_id: Optional[str] = None,
        module_refs: Optional[List[api_pb2.ModuleReference]] = None,
        overwrite: bool = True,
    ) -> api_pb2.SaveResponse:
        module_id = m_id or "default"
        module_references = module_refs if module_refs else []
        save_request = api_pb2.SaveRequest(
            id=module_id, modules=module_references, overwrite=overwrite, timestamp=int(time.time())
        )

        return cast(api_pb2.SaveResponse, self._service.Save(save_request))

    def _fetch_acquire_from_cache(self, modules: List[api_pb2.ModuleReference]) -> api_pb2.AquireResponse:
        res = api_pb2.AquireResponse(state=api_pb2.UpdateRequest(updates=[]))
        for module in modules:
            module_type = module_type_to_class[module.type]
            if module_type != "motherboard":
                update_id = module.index
            else:
                update_id = 0

            cache_key = (update_id, module_type)
            cached_modules = BatchSingleton().get_cached_modules(self)
            cached_updates = BatchSingleton().get_cached_updates(self)

            if cache_key in cached_modules:
                cached_module = MessageToDict(cached_modules[cache_key])
                cached_update = MessageToDict(cached_updates.get(cache_key, api_pb2.SingleUpdate()))

                cached_module.update(cached_update)
                new_update = api_pb2.SingleUpdate()
                ParseDict(cached_module, new_update)
                res.state.updates.append(new_update)
        return res

    def aquire_modules(
        self, modules: List[api_pb2.ModuleReference], use_cache: bool = True
    ) -> Union[api_pb2.AquireResponse, api_pb2.SingleUpdate]:
        res = self.acquire_modules(modules, use_cache)

        if len(modules) == 1 and len(res.state.updates) == 1:
            return res.state.updates[0]

        return res

    def acquire_modules(
        self, modules: Sequence[api_pb2.ModuleReference] = tuple(), use_cache: bool = True
    ) -> api_pb2.AquireResponse:
        modules = list(modules)
        if BatchSingleton().is_batch_mode:
            return self._fetch_acquire_from_cache(modules)
        else:
            request = api_pb2.AquireRequest(modules=modules, use_cache=use_cache)
            res = self._service.Aquire(request)
        return cast(api_pb2.AquireResponse, res)

    def acquire_all_modules(self, use_cache: bool = True) -> api_pb2.AquireResponse:
        return self.acquire_modules(use_cache=use_cache)

    def acquire_module(self, module: api_pb2.ModuleReference, use_cache: bool = True) -> api_pb2.SingleUpdate:
        return self.acquire_modules([module], use_cache=use_cache).state.updates[0]

    def recall(self, m_id: Optional[str] = None) -> api_pb2.RecallResponse:
        recall_request = api_pb2.RecallRequest(id="default" if m_id is None else m_id)
        return cast(api_pb2.RecallResponse, self._service.Recall(recall_request))

    def configs(self) -> List[api_pb2.SaveInfo]:
        return cast(List[api_pb2.SaveInfo], self._service.List(api_pb2.ListRequest()).save_infos)

    def version(self) -> api_pb2.GetVersionResponse:
        return cast(api_pb2.GetVersionResponse, self._service.GetVersion(api_pb2.GetVersionRequest()))

    def monitor(self, sense_only: bool = True) -> MonitorResult:
        monitor_request = api_pb2.MonitorRequest(sense_only=sense_only)
        return MonitorResult(self._service.Monitor(monitor_request))

    def explore(self) -> ExploreResult:
        return ExploreResult(self._service.Explore(api_pb2.ExploreRequest()))

    def identify(self) -> api_pb2.IdentifyResponse:
        return cast(api_pb2.IdentifyResponse, self._service.Identify(api_pb2.IdentifyRequest()))

    def reset(self) -> api_pb2.ResetResponse:
        return cast(api_pb2.ResetResponse, self._service.Reset(api_pb2.ResetRequest()))

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def octave_name(self) -> str:
        return self._octave_name
