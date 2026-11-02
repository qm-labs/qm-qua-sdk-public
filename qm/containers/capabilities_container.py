from typing_extensions import deprecated

from qm.utils.deprecation_utils import QmQuaDeprecationWarning


@deprecated(
    'create_capabilities_container is deprecated since "1.2.4" and will be removed in "2.0.0". '
    "This function does nothing, and will be removed in the next version. Please remove it",
    category=QmQuaDeprecationWarning,
    stacklevel=1,
)
def create_capabilities_container(qua_implementation: None) -> None:
    """This is here just to check if the CI passes, SW-validation imports this function and call it with None.

    Deprecated since 1.2.4; will be removed in 2.0.0. This function does nothing; please remove the call.

    Args:
        qua_implementation: Unused; kept only for backward compatibility. Should be ``None``.
    """
    # TODO - tell validation to remove this call
    return None
