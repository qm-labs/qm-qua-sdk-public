import warnings

from qm.utils import deprecation_message


def create_capabilities_container(qua_implementation: None) -> None:
    """This is here just to check if the CI passes, SW-validation imports this function and call it with None"""
    # TODO - tell validation to remove this call
    warnings.warn(
        deprecation_message(
            "create_capabilities_container",
            "1.2.4",
            "1.2.5",
            "This function does nothing, and will be removed in the next version. Please remove it",
        )
    )
    return None
