from typing import Any
from collections.abc import Mapping, Callable

from google.protobuf.message import Message
from google._upb._message import RepeatedCompositeContainer

from qm.utils import list_fields
from qm.utils.protobuf_utils import Node


class QuaNodeVisitor:
    def _default_enter(self, node: Message) -> bool:
        return True

    def _default_leave(self, node: Message) -> None:
        return

    def _default_visit(self, node: Message) -> None:
        for field in list_fields(node).values():
            self.visit(field)

    @property
    def _node_to_enter(self) -> Mapping[type, Callable[[Any], bool]]:
        return {}

    @property
    def _node_to_visit(self) -> Mapping[type, Callable[[Any], None]]:
        return {}

    @property
    def _node_to_leave(self) -> Mapping[type, Callable[[Any], None]]:
        return {}

    def _call_enter(self, node: Message) -> bool:
        if type(node) in self._node_to_enter:
            func = self._node_to_enter[type(node)]
            return func(node)
        return self._default_enter(node)

    def _call_visit(self, node: Message) -> None:
        if type(node) in self._node_to_visit:
            func = self._node_to_visit[type(node)]
            func(node)
        else:
            self._default_visit(node)

    def _call_leave(self, node: Message) -> None:
        if type(node) in self._node_to_leave:
            func = self._node_to_leave[type(node)]
            func(node)
        else:
            self._default_leave(node)

    def visit(self, node: Node) -> None:
        if isinstance(node, Message):
            self._enter_visit_leave(node)
        elif isinstance(node, RepeatedCompositeContainer):
            for n in node:
                self.visit(n)

    def _enter_visit_leave(self, node: Message) -> None:
        should_visit = self._call_enter(node)
        if should_visit:
            self._call_visit(node)
        self._call_leave(node)
