import sys
import types
import logging
import datetime
import traceback
from typing import Any, Dict, List, Mapping, Callable, Optional

import numpy as np
from marshmallow import ValidationError
from google.protobuf.message import Message
from google.protobuf.json_format import MessageToDict, MessageToJson

from qm.program import load_config
from qm.utils.protobuf_utils import Node
from qm import Program, FullQuaConfig, version
from qm.grpc.qm.pb.inc_qua_pb2 import QuaProgram
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm.api.models.capabilities import offline_capabilities
from qm.serialization.qua_node_visitor import QuaNodeVisitor
from qm.program._dict_to_pb_converter import DictToQuaConfigConverter
from qm.utils.list_compression_utils import Chunk, split_list_to_chunks
from qm.serialization.qua_serializing_visitor import QuaSerializingVisitor
from qm.exceptions import ConfigValidationException, ConfigSerializationException, CapabilitiesNotInitializedError

SERIALIZATION_VALIDATION_ERROR = "SERIALIZATION VALIDATION ERROR"

LOADED_CONFIG_ERROR = "LOADED CONFIG SERIALIZATION ERROR"

CONFIG_ERROR = "CONFIG SERIALIZATION ERROR"

SERIALIZATION_NOT_COMPLETE = "SERIALIZATION WAS NOT COMPLETE"

logger = logging.getLogger(__name__)


def standardize_program_for_comparison(prog: QuaProgram) -> QuaProgram:
    """There are things in the PB model that if they are different, the programs behaves exactly the same.
    These 3 things are
    1. the value of the loc field, that tells where the command was defined
    2. the names of the variables, as long as the commands are the same.
    3. the order of the variables in the result analysis
    """
    prog_copy = QuaProgram()
    prog_copy.CopyFrom(prog)

    StripLocationVisitor.strip(prog_copy)
    RenameStreamVisitor().visit(prog_copy)

    # Sort the model list in result analysis
    # Note: In regular protobuf, repeated fields are lists, so we need to sort them differently
    model_list = list(prog_copy.resultAnalysis.model)
    model_list.sort(key=str)

    # Clear and repopulate the sorted list
    prog_copy.resultAnalysis.ClearField("model")
    for item in model_list:
        prog_copy.resultAnalysis.model.append(item)

    return prog_copy


def assert_programs_are_equal(prog1: QuaProgram, prog2: QuaProgram) -> None:
    prog1 = standardize_program_for_comparison(prog1)
    prog2 = standardize_program_for_comparison(prog2)
    assert MessageToDict(prog1) == MessageToDict(prog2)


def generate_qua_script(prog: Program, config: Optional[FullQuaConfig] = None) -> str:
    if prog.is_in_scope():
        raise RuntimeError("Can not generate script inside the qua program scope")

    proto_config = None
    if config is not None:
        try:
            proto_config = load_config(config)
        except (ConfigValidationException, ValidationError) as e:
            raise RuntimeError("Can not generate script - bad config") from e
        except CapabilitiesNotInitializedError as e:
            logger.warning(f"Could not generate a loaded config. {e}")

    proto_prog = prog.qua_program
    return _generate_qua_script_pb(proto_prog, proto_config, config)


def _generate_qua_script_pb(
    proto_prog: QuaProgram,
    proto_config: Optional[QuaConfig],
    original_config: Optional[FullQuaConfig],
) -> str:
    extra_info = ""
    serialized_program = ""
    pretty_original_config = None

    if original_config is not None:
        try:
            pretty_original_config = _print_config(original_config)
        except Exception as e:
            trace = traceback.format_exception(*sys.exc_info())
            extra_info = extra_info + _error_string(e, trace, CONFIG_ERROR)
            pretty_original_config = f"{original_config}"

    pretty_proto_config = None
    if proto_config is not None:
        try:
            converter = DictToQuaConfigConverter(capabilities=offline_capabilities)
            normalized_config = converter.deconvert(proto_config)
            pretty_proto_config = _print_config(normalized_config)
        except Exception as e:
            trace = traceback.format_exception(*sys.exc_info())
            extra_info = extra_info + _error_string(e, trace, LOADED_CONFIG_ERROR)

    try:
        visitor = QuaSerializingVisitor()
        visitor.visit(proto_prog)
        serialized_program = visitor.out()

        extra_info = extra_info + _validate_program(proto_prog, serialized_program)
    except Exception as e:
        trace = traceback.format_exception(*sys.exc_info())
        extra_info = extra_info + _error_string(e, trace, SERIALIZATION_VALIDATION_ERROR)

    return f"""
# Single QUA script generated at {datetime.datetime.now()}
# QUA library version: {version.__version__}

{serialized_program}
{extra_info if extra_info else ""}
config = {pretty_original_config}

loaded_config = {pretty_proto_config}

"""


def _execute_program_safely(serialized_program: str) -> types.ModuleType:
    """Execute serialized QUA program in a restricted environment.

    This function provides defense-in-depth security by:
    1. Restricting available builtins to prevent dangerous operations
    2. Allowing only safe imports (qm.* and typing modules)
    3. Blocking access to exec, eval, open, __import__, and other dangerous functions

    Args:
        serialized_program: The QUA Python code to execute

    Returns:
        The module containing the executed program (with 'prog' attribute)

    Raises:
        ImportError: If code attempts to import non-whitelisted modules
        NameError: If code attempts to use blocked builtin functions
        Any exceptions from the executed code itself
    """
    # Save reference to real import for restricted wrapper
    # __builtins__ can be either a module or a dict depending on context
    if isinstance(__builtins__, dict):
        real_import = __builtins__["__import__"]
    else:
        real_import = __builtins__.__import__

    def safe_import(
        name: str,
        globals: Optional[Mapping[str, Any]] = None,
        locals: Optional[Mapping[str, Any]] = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> types.ModuleType:
        """Only allow importing from qm.* and typing modules."""
        if name in ("typing",) or name.startswith("qm.") or name == "qm":
            return real_import(name, globals, locals, fromlist, level)
        raise ImportError(f"Import of '{name}' is not allowed for security reasons")

    # Create restricted environment with safe builtins
    # Allow essential Python types and functions that are safe
    safe_builtins = {
        "__import__": safe_import,
        "__build_class__": __build_class__,  # Needed for class definitions
        # Boolean and None
        "True": True,
        "False": False,
        "None": None,
        # Basic types
        "int": int,
        "float": float,
        "bool": bool,
        "str": str,
        "list": list,
        "tuple": tuple,
        "dict": dict,
        "set": set,
        # Utility functions
        "all": all,
        "any": any,
        "hasattr": hasattr,
        "getattr": getattr,
        "repr": repr,
        "type": type,
        # Note: Dangerous functions like exec, eval, open, compile, __import__ (raw),
        # input, file operations are intentionally omitted
    }

    generated_mod = types.ModuleType("gen")
    generated_mod.__dict__["__builtins__"] = safe_builtins

    # In Python 3.8 and 3.9, the tests fail with a KeyError because "gen" is missing.
    if sys.version_info < (3, 10):
        sys.modules["gen"] = generated_mod

    try:
        exec(serialized_program, generated_mod.__dict__)
    finally:
        sys.modules.pop("gen", None)

    return generated_mod


def _validate_program(old_prog: QuaProgram, serialized_program: str) -> str:
    generated_mod = _execute_program_safely(serialized_program)
    new_prog = generated_mod.prog.qua_program
    try:
        assert_programs_are_equal(old_prog, new_prog)
        return ""
    except AssertionError:
        new_prog_str = _program_string(new_prog)
        old_prog_str = _program_string(old_prog)
        new_prog_str = new_prog_str.replace("\n", "")
        old_prog_str = old_prog_str.replace("\n", "")
        return f"""

####     {SERIALIZATION_NOT_COMPLETE}     ####
#
#  Original   {old_prog_str}
#  Serialized {new_prog_str}
#
################################################

        """


def _error_string(e: Exception, trace: List[str], error_type: str) -> str:
    return f"""

    ####     {error_type}     ####
    #
    #  {str(e)}
    #
    # Trace:
    #   {str(trace)}
    #
    ################################################

            """


def _program_string(prog: QuaProgram) -> str:
    """Will create a canonized string representation of the program"""
    strip_location_visitor = StripLocationVisitor()
    strip_location_visitor.visit(prog)
    string = MessageToJson(prog, indent=2)
    return string


def _print_config(config_part: Mapping[str, Any], indent_level: int = 1) -> str:
    """Formats a python dictionary into an executable string representation.
    Unlike pretty print, it better supports nested dictionaries. Also, auto converts
    lists into a more compact form.
    Works recursively.

    Args:
        indent_level (int): Internally used by the function to indicate
            the current indention
        config_part: The dictionary to format
    :returns str: The string representation of the dictionary.
    """
    if indent_level > 100:
        raise ConfigSerializationException("Reached maximum depth of config pretty print")

    config_part_str = ""
    if len(config_part) > 0:
        config_part_str += "{\n"

        for key, value in config_part.items():
            config_part_str += "    " * indent_level + f'"{str(key)}": ' + _value_to_str(indent_level, value)

        if indent_level > 1:
            # add an indentation and go down a line
            config_part_str += "    " * (indent_level - 1) + "},\n"
        else:
            # in root indent level, no need to add a line
            config_part_str += "}"

    else:
        config_part_str = "{},\n"

    return config_part_str


def _value_to_str(indent_level: int, value: Any) -> str:
    # To support numpy types, we convert them to normal python types:
    if type(value).__module__ == np.__name__:
        value = value.tolist()

    is_long_list = isinstance(value, list) and len(value) > 1

    if isinstance(value, dict):
        return _print_config(value, indent_level + 1)
    elif isinstance(value, str):
        return f'"{value}"' + ",\n"
    elif is_long_list and isinstance(value[0], dict):
        temp_str = "[\n"
        for v in value:
            temp_str += "    " * (indent_level + 1) + f"{str(v)},\n"
        temp_str += "    " * indent_level + "],\n"
        return temp_str
    elif is_long_list:
        first_value = value[0]
        is_single_value = all(v == first_value for v in value)

        if is_single_value:
            return f"[{value[0]}] * {len(value)}" + ",\n"
        else:
            return f"{_make_compact_string_from_list(value)}" + ",\n"
    else:
        # python basic data types string representation are valid python
        return str(value) + ",\n"


def _serialize_chunks(chunks: List[Chunk[object]]) -> str:
    return " + ".join([str(chunk) for chunk in chunks])


def _make_compact_string_from_list(list_data: List[object]) -> str:
    """
    Turns a multi-value list into the most compact string representation of it,
    replacing identical consecutive values by list multiplication.
    """
    chunks = split_list_to_chunks(list_data)
    return _serialize_chunks(chunks)


class StripLocationVisitor(QuaNodeVisitor):
    """Go over all nodes and if they have a location property, we strip it"""

    def _default_enter(self, node: Node) -> bool:
        if hasattr(node, "loc"):
            node.loc = "stripped"
        return isinstance(node, Message)

    @staticmethod
    def strip(node: Node) -> None:
        StripLocationVisitor().visit(node)


class RenameStreamVisitor(QuaNodeVisitor):
    """This class standardizes the names of the streams, so when comparing two programs, the names will be the same"""

    def __init__(self) -> None:
        self._max_n = 0
        self._old_to_new_map: Dict[str, str] = {}

    def _change_var_name(self, curr_s: str) -> str:
        if curr_s in self._old_to_new_map:
            return self._old_to_new_map[curr_s]
        non_digits = "".join([s for s in curr_s if not s.isdigit()])
        new_name = non_digits + str(self._max_n)
        self._max_n += 1
        self._old_to_new_map[curr_s] = new_name
        return new_name

    @property
    def _node_to_visit(self) -> Mapping[type, Callable[[Any], None]]:
        return {
            QuaProgram.MeasureStatement: self.visit_qm_pb_inc_qua_pb2_QuaProgram_MeasureStatement,
            QuaProgram.SaveStatement: self.visit_qm_pb_inc_qua_pb2_QuaProgram_SaveStatement,
        }

    def visit_qm_pb_inc_qua_pb2_QuaProgram_MeasureStatement(self, node: QuaProgram.MeasureStatement) -> None:
        # In regular protobuf, check if field is set before accessing
        if node.streamAs != "":
            node.streamAs = self._change_var_name(node.streamAs)
        if node.timestampLabel != "":
            node.timestampLabel = self._change_var_name(node.timestampLabel)

    def visit_qm_pb_inc_qua_pb2_QuaProgram_SaveStatement(self, node: QuaProgram.SaveStatement) -> None:
        # In regular protobuf, check if field is set before accessing
        if node.tag != "":
            node.tag = self._change_var_name(node.tag)

    def _default_enter(self, node: Node) -> bool:
        """This function is for the Value of google.protobuf. There is a chance we can visit the object directly"""

        if (
            isinstance(node, Message)
            and hasattr(node, "string_value")
            and node.HasField("string_value")
            and node.string_value  # Check if field is set in regular protobuf
            and node.string_value in self._old_to_new_map
        ):
            node.string_value = self._old_to_new_map[node.string_value]
        return isinstance(node, Message)
