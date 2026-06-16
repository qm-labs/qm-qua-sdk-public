import hashlib
from abc import ABC, abstractmethod
from typing import Generic, Literal, TypeVar, TypeAlias, overload

from qm.exceptions import ConfigValidationException


def _change_case(name: str) -> str:
    res = ""
    for i in name:
        if i.isupper():
            res += "_" + i.lower()
        else:
            res += i
    return res[1:]


T = TypeVar("T")


class Frequency:
    """A frequency value [Hz] with sign-preserving accessors.

    The legacy schema serializes a single frequency into both an unsigned int field and
    a (signed) double field, plus a separate "is negative" flag. ``Frequency`` keeps the
    raw value and exposes whichever view a converter needs.
    """

    def __init__(self, value: float) -> None:
        self._value = value

    @property
    def as_int(self) -> int:
        return int(self._value)

    @property
    def as_uint(self) -> int:
        return abs(self.as_int)

    @property
    def as_ufloat(self) -> float:
        return abs(float(self._value))

    @property
    def is_negative(self) -> bool:
        return self._value < 0

    @property
    def as_float(self) -> float:
        return float(self._value)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self._value)})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Frequency):
            return self.as_float == other.as_float
        if isinstance(other, (int, float)):
            return self.as_float == other
        return False


class ConfigObject(ABC):  # noqa: B024
    def __eq__(self, other: object) -> bool:
        if type(other) is not type(self):
            return False
        return self.__dict__ == other.__dict__

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


class ConfigValue(Generic[T], ABC):
    """A field value that distinguishes "explicitly set" from "default" / "not set".

    Three concrete forms (``SetValue``, ``DefaultValue``, ``NoDefaultValue``) let
    converters decide whether to emit a field on the wire even when the resolved value
    matches the default.
    """

    @overload
    def get_value(self, return_none_if_not_set: Literal[False] = ...) -> T: ...

    @overload
    def get_value(self, return_none_if_not_set: Literal[True]) -> T | None: ...

    @abstractmethod
    def get_value(self, return_none_if_not_set: bool = False) -> T | None:
        pass

    @property
    @abstractmethod
    def is_set(self) -> bool:
        pass

    @abstractmethod
    def __repr__(self) -> str:
        pass

    def __eq__(self, other: object) -> bool:
        if type(other) is not type(self):
            return False
        assert isinstance(other, ConfigValue)
        return (self.get_value() == other.get_value()) and (self.is_set == other.is_set)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


class SetValue(ConfigValue[T]):
    def __init__(self, value: T) -> None:
        self._value = value

    def get_value(self, return_none_if_not_set: bool = False) -> T:
        return self._value

    @property
    def is_set(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self._value)})"


class DefaultValue(ConfigValue[T]):
    def __init__(self, value: T) -> None:
        self._value = value

    @overload
    def get_value(self, return_none_if_not_set: Literal[False] = ...) -> T: ...

    @overload
    def get_value(self, return_none_if_not_set: Literal[True]) -> T | None: ...

    def get_value(self, return_none_if_not_set: bool = False) -> T | None:
        if return_none_if_not_set:
            return None
        return self._value

    @property
    def is_set(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self._value)})"


class NoDefaultValue(ConfigValue[T]):
    @overload
    def get_value(self, return_none_if_not_set: Literal[False] = ...) -> T: ...

    @overload
    def get_value(self, return_none_if_not_set: Literal[True]) -> T | None: ...

    def get_value(self, return_none_if_not_set: bool = False) -> T | None:
        if return_none_if_not_set:
            return None
        raise ConfigValidationException("There is no default value for this field, thus it should be declared")

    @property
    def is_set(self) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        # The base ConfigValue.__eq__ would call get_value() with default args, which raises here.
        # Two NoDefaultValue instances both represent "unset, no default" → equal.
        return type(other) is type(self)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class NamedObject(ConfigObject, ABC):
    def __init__(self, name: str = ""):
        if name:
            self.name = name
        else:
            suffix = hashlib.md5(f"{self.__class__.__name__}-{self}".encode()).hexdigest()[:4]
            class_name = _change_case(self.__class__.__name__)
            self.name = f"{class_name}_{suffix}"


class _NotSet:
    pass


NOT_SET = _NotSet()
ConfigOptional: TypeAlias = T | _NotSet | ConfigValue[T]


def create_value(data: ConfigOptional[T], default_value: T | _NotSet) -> ConfigValue[T]:
    # Default value of NOT_SET means no default value.
    if isinstance(data, _NotSet):
        if isinstance(default_value, _NotSet):
            return NoDefaultValue()
        return DefaultValue(default_value)
    if isinstance(data, ConfigValue):
        return data
    return SetValue(data)
