import warnings
from typing import Any, TypeVar, Optional


def throw_warning(message: str, category: Optional[type] = None, stacklevel: int = 1, source: Any = None) -> None:
    """
    This function wraps `warnings.warn`, this enables IPython to display the warning when importing.
    """
    warnings.warn(message, category=category, stacklevel=stacklevel + 1, source=source)


def deprecation_message(method: str, deprecated_in: str, removed_in: str, details: str = "") -> str:
    """
    Generates a deprecation message for deprecation a function.

    This call:
        warnings.warn(deprecation_message("foo", "1.0.0", "1.1.0", "reason), category=DeprecationWarning)

    Will result in:
        "foo is deprecated since "1.0.0" and will be removed in "1.1.1. reason"

    Args:
        method: The name of the deprecated method.

        deprecated_in: The version at which the method is considered deprecated.
                   This will usually be the next version to be released when the warning is added.

        removed_in: The version when the method will be removed.

        details: Extra details to be added to the method docstring and warning.
                    For example, the details may point users to a replacement method, such as "Use the foo_bar method instead"
    """
    to_return = f'{method} is deprecated since "{deprecated_in}" and will be removed in "{removed_in}".'
    if details:
        to_return += f" {details}"
    return to_return


T = TypeVar("T")
