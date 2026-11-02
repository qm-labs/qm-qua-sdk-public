import re
import logging

logger = logging.getLogger(__name__)


def natural_sort_key(name: str) -> tuple[int | str, ...]:
    """Splits a name into text/number chunks so e.g. "port2" sorts before "port10".

    The proto map holding the two output port names carries no ordering of its own
    (neither insertion order nor wire order survives), so this is a
    best-effort tie-breaker for the common "portN" naming pattern, not a guarantee
    of the original construction order for arbitrary custom names.
    """
    to_return = tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name))
    if not any(isinstance(x, int) for x in to_return):
        logger.warning("No number was found in ports, resorting to lexicographical ordering.")
    return to_return
