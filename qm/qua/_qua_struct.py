import dataclasses
from typing_extensions import dataclass_transform
from typing import (
    Any,
    List,
    Type,
    Union,
    Generic,
    Literal,
    Mapping,
    TypeVar,
    Callable,
    Protocol,
    get_args,
    overload,
    get_origin,
    get_type_hints,
)

from qm.type_hinting import NumberT
from qm.grpc.qua import QuaProgramVarDeclaration
from qm.type_hinting.general import DataclassProtocol
from qm.qua._dsl.variable_handling import _declare_struct_array_variable
from qm.exceptions import ReservedFieldNameError, InvalidQuaArraySubclassError
from qm.qua._expressions import NSize, QuaStructReference, QuaStructArrayVariable

# A more user-friendly alias for QuaStructArrayVariable.
# In the future, we might want to use QuaArray for other types beyond QuaStructArrayVariable.
# For now, it's simply set to QuaStructArrayVariable since that's the only current use case.
QuaArray = QuaStructArrayVariable


class StructArrayFactory(Generic[NumberT]):
    def __init__(self, array_type: Type[NumberT], size: int, position: int):
        self._array_type: Type[NumberT] = array_type
        self._size = size
        self._position = position

    def create(self, struct_ref: QuaStructReference) -> QuaStructArrayVariable[NumberT, NSize]:
        return _declare_struct_array_variable(
            t=self._array_type, size=self._size, position=self._position, struct_ref=struct_ref
        )

    @property
    def underlying_declaration(self) -> QuaProgramVarDeclaration:
        # This function is called before 'create', so the real struct member declaration isn't available yet.
        # We do not really need a real declaration, only the 'metadata' of the struct array - type, size and position in struct.
        return QuaStructArrayVariable(
            "", self._array_type, self._size, self._position, QuaStructReference("")
        ).declaration_statement


class _QuaStruct(DataclassProtocol, Protocol):
    __members_initializers__: Mapping[str, StructArrayFactory[Any]]
    __underlying_declarations__: List[QuaProgramVarDeclaration]
    struct_reference: QuaStructReference


_T = TypeVar("_T")


@dataclass_transform()
@overload
def qua_struct(_cls: Union[Type[_T], None]) -> Type[_T]:
    ...


@dataclass_transform()
@overload
def qua_struct() -> Callable[[Type[_T]], Type[_T]]:
    ...


@dataclass_transform()
def qua_struct(_cls: Union[Type[_T], None] = None) -> Union[Callable[[Type[_T]], Type[_T]], Type[_T]]:
    """
    Decorator to define a QUA struct.
    """

    def validate_field_type(annotation: Any) -> None:
        field_type = get_origin(annotation)
        # Check whether the field type is a class, and if it is specifically a subclass of QuaArray
        if isinstance(field_type, type) and issubclass(field_type, QuaArray):
            if len(get_args(annotation)) != 2:
                raise InvalidQuaArraySubclassError(
                    f"Invalid QuaArray subclass: {field_type}. "
                    "Expected exactly two type arguments (e.g., QuaArray[int, 5]) "
                    "representing the element type and array size."
                )
        else:
            # The field might not be annotated with generics, causing get_origin to return None.
            if field_type is None:
                field_type = annotation
            raise TypeError(f"Type '{field_type.__name__}' is not supported as a QUA struct field type")

    def get_members_initializers(cls: Type[_T]) -> Mapping[str, StructArrayFactory[Any]]:
        output = {}
        for index, (name, annotation) in enumerate(get_type_hints(cls).items()):
            if name in get_type_hints(_QuaStruct).keys():
                raise ReservedFieldNameError(f"Field name '{name}' is reserved for internal use within a QUA struct")

            validate_field_type(annotation)

            array_type, array_size = get_args(annotation)
            array_size_type = get_origin(array_size)
            if array_size_type == Literal:  # For "proper" type hinting
                array_size = get_args(array_size)[0]

            output[name] = StructArrayFactory(array_type, array_size, index)

        return output

    def add_reference_field(cls: Type[_T]) -> None:
        # Add the `_struct_reference` field to the class
        cls.__annotations__["_struct_reference"] = QuaStructReference  # noqa
        setattr(cls, "_struct_reference", dataclasses.field())  # noqa: B010

        # Add a read-only property for 'reference'
        @property  # type: ignore
        def struct_reference(self) -> QuaStructReference:  # type: ignore[no-untyped-def]
            return self._struct_reference  # type: ignore

        cls.struct_reference = struct_reference  # type: ignore[attr-defined]

    def create_qua_struct(cls: Type[_T]) -> Type[_T]:
        members_initializers = get_members_initializers(cls)
        underlying_declarations = [
            member_factory.underlying_declaration for member_factory in members_initializers.values()
        ]

        add_reference_field(cls)
        cls.__members_initializers__ = members_initializers  # type: ignore[attr-defined]
        cls.__underlying_declarations__ = underlying_declarations  # type: ignore[attr-defined]

        dataclass_cls = dataclasses.dataclass(cls)
        return dataclass_cls

    return create_qua_struct(_cls) if _cls is not None else create_qua_struct
