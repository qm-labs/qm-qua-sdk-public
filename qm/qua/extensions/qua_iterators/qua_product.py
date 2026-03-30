from typing import Any, List, Optional

from qm.qua.extensions.qua_iterators.qua_iterators_base import IterableBase
from qm.qua.extensions.qua_iterators.qua_iterators_types import QuaNamedTuple, MultiIteratorType, IteratorContentTypes


class QuaProduct:
    """
    Combine iterables into nested loops, similarly to Python's
    ``itertools.product``.

    ``QuaProduct`` expands a sequence of iterable helpers into nested loops.
    The first iterable becomes the outermost loop and the last iterable becomes
    the innermost loop, so reordering the list changes the loop nesting order.

    A product can mix QUA iterables and native iterables. The yielded value is
    a named tuple whose field names match the iterable names.

    Note:
        Use ``QuaProduct`` as the outer combinator. Do not pass a
        ``QuaProduct`` instance into another iterable helper such as
        [QuaZip][qm.qua.extensions.qua_iterators.QuaZip].

    Example:
        ```python
        with program() as prog:
            for args in QuaProduct(
                [
                    QuaIterableRange("shot", 100),
                    NativeIterable("element", ["q1", "q2"]),
                    QuaZip(
                        [
                            QuaIterable("amp", [0.2, 0.5, 0.8]),
                            QuaIterable("tau", [16, 32, 64]),
                        ],
                        name="drive",
                    ),
                ]
            ):
                play("x90" * amp(args.drive.amp), args.element)
                wait(args.drive.tau)
        ```
    """

    def __init__(self, iterables: List[IterableBase[Any]]):
        self._iterables = iterables
        self._iterable_names = [itr.name for itr in self._iterables]

    @property
    def iterables(self) -> tuple[IterableBase[Any], ...]:
        return tuple(self._iterables)

    def _traverse_iterables(
        self, iterables_id: int = 0, yielded_itr: Optional[List[IteratorContentTypes]] = None
    ) -> MultiIteratorType:
        """
        Recursively traverse the product iterables from first to last.

        Args:
            iterables_id: Index of the iterable currently being traversed.
            yielded_itr: Values yielded by the iterables visited so far.
        """
        if not yielded_itr:
            yielded_itr = []
        if iterables_id == len(self._iterables):
            yield QuaNamedTuple(self._iterable_names, yielded_itr)
        else:
            for curr_itr in self._iterables[iterables_id]:
                if iterables_id == len(yielded_itr):
                    yielded_itr.append(curr_itr)
                else:
                    yielded_itr[iterables_id] = curr_itr
                yield from self._traverse_iterables(iterables_id + 1, yielded_itr)

    def __iter__(self) -> MultiIteratorType:
        yield from self._traverse_iterables()
