from qm.grpc.octave.v1 import api_pb2


class _BuilderList:
    def __init__(self) -> None:
        super().__init__()
        self._items: dict[int, api_pb2.SingleUpdate] = {}

    def get_items(self) -> list[api_pb2.SingleUpdate]:
        return list(self._items.values())


class _SynthBuilderList(_BuilderList):
    def __getitem__(self, item: int) -> api_pb2.SynthUpdate:
        if item not in self._items:
            self._items[item] = api_pb2.SingleUpdate(synth=api_pb2.SynthUpdate(index=item))
        return self._items[item].synth


class _DownBuilderList(_BuilderList):
    def __getitem__(self, item: int) -> api_pb2.RFDownConvUpdate:
        if item not in self._items:
            self._items[item] = api_pb2.SingleUpdate(rf_down_conv=api_pb2.RFDownConvUpdate(index=item))
        return self._items[item].rf_down_conv


class _UpBuilderList(_BuilderList):
    def __getitem__(self, item: int) -> api_pb2.RFUpConvUpdate:
        if item not in self._items:
            self._items[item] = api_pb2.SingleUpdate(rf_up_conv=api_pb2.RFUpConvUpdate(index=item))
        return self._items[item].rf_up_conv


class _IFBuilderList(_BuilderList):
    def __getitem__(self, item: int) -> api_pb2.IFDownConvUpdate:
        if item not in self._items:
            self._items[item] = api_pb2.SingleUpdate(if_down_conv=api_pb2.IFDownConvUpdate(index=item))
        return self._items[item].if_down_conv


class _ClockBuilderList(_BuilderList):
    def __getitem__(self, item: int) -> api_pb2.ClockUpdate:
        if item not in self._items:
            self._items[item] = api_pb2.SingleUpdate(clock=api_pb2.ClockUpdate())
        return self._items[item].clock_dist  # type: ignore  # (YR) - seems like a bug


class ClientRequestBuilder:
    def __init__(self) -> None:
        super().__init__()
        self._synth_builder_list = _SynthBuilderList()
        self._up_builder_list = _UpBuilderList()
        self._down_builder_list = _DownBuilderList()
        self._if_builder_list = _IFBuilderList()
        self._clock_builder_list = _ClockBuilderList()
        self._updates: list[api_pb2.SingleUpdate] = []

    @property
    def synth(self) -> _SynthBuilderList:
        return self._synth_builder_list

    @property
    def up(self) -> _UpBuilderList:
        return self._up_builder_list

    @property
    def down(self) -> _DownBuilderList:
        return self._down_builder_list

    @property
    def ifconv(self) -> _IFBuilderList:
        return self._if_builder_list

    @property
    def clk(self) -> _ClockBuilderList:
        return self._clock_builder_list

    def get_updates(self) -> list[api_pb2.SingleUpdate]:
        return (
            self._synth_builder_list.get_items()
            + self._down_builder_list.get_items()
            + self._up_builder_list.get_items()
            + self._if_builder_list.get_items()
            + self._clock_builder_list.get_items()
        )
