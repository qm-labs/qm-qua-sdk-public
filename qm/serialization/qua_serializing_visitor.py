import re
import logging
from typing import Any, Optional
from collections.abc import Mapping, Callable, MutableSequence

from google.protobuf.message import Message
from google.protobuf.struct_pb2 import Value, ListValue

from qm.exceptions import QmQuaException
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm.serialization.qua_node_visitor import QuaNodeVisitor
from qm.grpc.qm.pb.inc_qua_pb2 import QuaProgram, QuaResultAnalysis
from qm.utils.protobuf_utils import Node, which_one_of, serialized_on_wire
from qm.serialization.expression_serializing_visitor import ExpressionSerializingVisitor

logger = logging.getLogger(__name__)


class InvalidIdentifierError(Exception):
    pass


def _safe_str(value: str) -> str:
    """Safely escape strings for code generation to prevent injection attacks.

    Uses repr() to ensure the string is properly escaped when embedded in generated code.
    This prevents code injection through malicious strings in protobuf fields.

    Args:
        value: The string to escape

    Returns:
        A properly escaped string literal safe for code generation

    Example:
        >>> _safe_str('hello')
        "'hello'"
        >>> _safe_str('x"); os.system("evil')
        '\'x"); os.system("evil\''
    """
    return repr(value)


def _safe_identifier(value: str) -> str:
    """Validate that a string is a safe Python identifier.

    Ensures the value can be used as a variable name without injection risks.

    Args:
        value: The string to validate as an identifier

    Returns:
        The validated identifier

    Raises:
        InvalidIdentifierError: If the value is not a valid Python identifier

    Example:
        >>> _safe_identifier('my_var')
        'my_var'
        >>> _safe_identifier('123invalid')
        InvalidIdentifierError: Invalid Python identifier for a variable name: '123invalid'
    """
    if not value.isidentifier():
        raise InvalidIdentifierError(f"Invalid Python identifier for a variable name: {repr(value)}")
    return value


class StructDeclaration:
    def __init__(self, type_name: str, variable_name: str) -> None:
        self._name: str = type_name
        self.variable_name: str = variable_name
        self._variables: dict[str, tuple[str, int]] = {}

    def variables(self) -> list[str]:
        return list(self._variables.keys())

    def add_variable(self, name: str, var_type: QuaProgram.Type, size: int) -> None:
        self._variables[name] = (_var_type_dec[var_type], size)

    def get_struct_declaration(self) -> str:
        return f"    {self.variable_name} = declare_struct({self._name})"

    def __str__(self) -> str:
        output = f"@qua_struct\nclass {self._name}:\n"
        for name, [var_type, size] in self._variables.items():
            output += f"    {name}: QuaArray[{var_type}, Literal[{size}]]\n"
        output += "\n"
        return output


class QuaSerializingVisitor(QuaNodeVisitor):
    def __init__(self) -> None:
        super().__init__()
        self._indent = 0
        self.structs: list[StructDeclaration] = []
        self._lines: list[str] = []
        self.tags: list[str] = []
        self._used_global_vars: bool = False

    def _format_imports(self) -> str:
        output = ""

        if self.structs:
            output += "\nfrom typing import Literal\n"

        output += """
from qm import CompilerOptionArguments
from qm.qua import *
"""
        if self._used_global_vars:
            output += "from qm.qua._dsl.global_var import assign_global_var, global_var_read, global_var_xor\n"

        output += "\n"
        return output

    def out(self) -> str:
        output = self._format_imports()

        struct_declarations = []
        for struct in self.structs:
            output += str(struct)
            if struct.variable_name:
                struct_declarations.append(struct.get_struct_declaration())

        self._lines = self._lines[0:1] + struct_declarations + self._lines[1:]
        output += "\n".join(self._lines)
        return output

    def _out_lines(self) -> list[str]:
        return self._lines

    def _default_enter(self, node: Node) -> bool:
        if not isinstance(node, tuple(_dont_print)):
            logger.info(f"entering {type(node).__module__}.{type(node).__name__}")
        statement: Optional[Callable[[Node, "QuaSerializingVisitor"], str]] = _statements.get(type(node), None)  # type: ignore[assignment]

        if statement is not None:
            line = statement(node, self)
            self._line(line)

        block: Optional[Callable[[Node, "QuaSerializingVisitor"], str]] = _blocks.get(type(node), None)  # type: ignore[assignment]
        if block is not None:
            self._enter_block(block(node, self))
        return statement is None

    @staticmethod
    def _search_auto_added_stream(values: MutableSequence[Value]) -> bool:
        v2 = values[2]
        is_auto_added_result = False
        if isinstance(v2, Value):
            name, value = which_one_of(v2, "kind")
            if isinstance(value, str):
                is_auto_added_result = name == "string_value" and value == "auto"

        return is_auto_added_result

    def _fix_legacy_save(self, sp_line: str, node: ListValue) -> None:
        split_sp_line = sp_line.split(".")
        trace_name = split_sp_line[0]
        save_name = split_sp_line[-1].split('"')[1]
        save_name = re.sub(r"_input\d", "", save_name)
        is_auto_added_stream = self._search_auto_added_stream(node.values)
        if is_auto_added_stream:
            self._lines.pop()
            line_to_remove_index = None
            for i in range(len(self._lines)):
                if self._lines[i].find(f"{trace_name} = declare_output_stream") > 0:
                    line_to_remove_index = i
                self._lines[i] = re.sub(r"(?<=\W|\^)" + trace_name + r"(?=\W|\$)", f'"{save_name}"', self._lines[i])
            if line_to_remove_index:
                self._lines.pop(line_to_remove_index)

    @property
    def _node_to_enter(self) -> Mapping[type, Callable[[Any], bool]]:
        return {
            ListValue: self.enter_list_value,
            QuaProgram.CompilerOptions: self.enter_compiler_options,
            QuaResultAnalysis: self.enter_result_analysis,
            QuaProgram.SaveStatement: self.enter_save,
            QuaProgram.VarDeclaration: self.enter_variable_declaration,
            QuaProgram.ExternalStreamDeclaration: self.enter_external_stream_declaration,
            QuaProgram.MeasureStatement: self.enter_measure,
        }

    def enter_compiler_options(self, node: QuaProgram.CompilerOptions) -> bool:
        options_list = []
        if node.strict:
            options_list.append(f"strict={node.strict}")
        if len(node.flags) > 0:
            options_list.append(f"flags={node.flags}")
        options_string = ", ".join(options_list)
        if len(options_string) > 0:
            self._lines.insert(0, f"compiler_options = CompilerOptionArguments({options_string})\n")

        return False

    def enter_result_analysis(self, node: QuaResultAnalysis) -> bool:
        if len(node.model) > 0:
            self._enter_block("with stream_processing():")
            return True
        else:
            return False

    def enter_save(self, node: QuaProgram.SaveStatement) -> bool:
        if node.tag not in self.tags:
            self._line(f"{_safe_identifier(node.tag)} = declare_output_stream()")
            self.tags.append(node.tag)
        save_line = f"save({self.serialize_expression(node.source)}, {_safe_identifier(node.tag)})"
        self._line(save_line)
        return False

    def enter_variable_declaration(self, node: QuaProgram.VarDeclaration) -> bool:
        if self._check_if_has_struct(node):
            return False

        args = self._get_declare_var_args(node)

        if node.isInputStream:
            # Removes the '_input_stream' from the end of the name
            stream_name = node.name[13:]
            self._line(
                f"{_safe_identifier(node.name)} = declare_input_stream({_var_type_dec[node.type]}, {_safe_str(stream_name)}, {_dict_to_python_call(args)})"
            )
        else:
            self._line(
                f"{_safe_identifier(node.name)} = declare({_var_type_dec[node.type]}, {_dict_to_python_call(args)})"
            )

        return False

    def _check_if_has_struct(self, node: QuaProgram.VarDeclaration) -> bool:
        if node.structMember is None or not serialized_on_wire(node.structMember):
            return False

        struct: Optional[StructDeclaration] = None
        for _struct in self.structs:
            if _struct.variable_name == node.structMember.name:
                struct = _struct
                break

        if struct is None:
            struct = StructDeclaration(f"Struct{node.structMember.name}", node.structMember.name)
            self.structs.append(struct)

        struct.add_variable(node.name, node.type, node.size)
        return True

    def enter_external_stream_declaration(self, node: QuaProgram.ExternalStreamDeclaration) -> bool:
        struct_type = self._create_struct_from_expected_types(node)
        if node.direction == QuaProgram.Direction.INCOMING:
            name_prefix = "i"
        else:
            name_prefix = "o"

        var_name = f"s{name_prefix}{node.stream_id}"

        if node.direction == QuaProgram.Direction.INCOMING:
            declare_function = "declare_input_stream"
        else:
            declare_function = "declare_output_stream"

        self._line(f'{var_name} = {declare_function}("opnic", {node.stream_id}, {struct_type})')

        return False

    def _create_struct_from_expected_types(self, node: QuaProgram.ExternalStreamDeclaration) -> str:
        struct_class_name = (
            f"StructStream{self.stream_direction_to_string(node.direction).capitalize()}{node.stream_id}"
        )
        struct = StructDeclaration(struct_class_name, "")

        for index, expected_type in enumerate(node.expectedTypes):
            struct.add_variable(f"variable_{index}", expected_type.type, expected_type.size)
        self.structs.append(struct)
        return struct_class_name

    @staticmethod
    def stream_direction_to_string(stream_direction: QuaProgram.Direction) -> str:
        if stream_direction == QuaProgram.Direction.INCOMING:
            return "INCOMING"
        elif stream_direction == QuaProgram.Direction.OUTGOING:
            return "OUTGOING"
        else:
            raise ValueError(f"Unknown stream direction {stream_direction}")

    def enter_list_value(self, node: ListValue) -> bool:
        line = _stream_processing_terminal_statement(node, self)
        self._line(line)
        self._fix_legacy_save(line, node)
        return False

    @property
    def _node_to_leave(self) -> Mapping[type, Callable[[Any], None]]:
        return {QuaProgram: self.leave_program}

    def leave_program(self, node: QuaProgram) -> None:
        if self._lines[-1].find("with stream_processing():") > 0:
            self._lines.pop()

    def _get_declare_var_args(self, node: QuaProgram.VarDeclaration) -> dict[str, str]:
        size = node.size
        dim = node.dim
        args = {}
        if dim > 0:
            args["size"] = f"{size}"
        if dim > 0 and len(node.value) > 0:
            args["value"] = "[" + ", ".join([self.serialize_expression(it) for it in node.value]) + "]"
        elif len(node.value) == 1:
            args["value"] = self.serialize_expression(node.value[0])
        if "value" in args and "size" in args:
            del args["size"]
        return args

    def enter_measure(self, node: QuaProgram.MeasureStatement) -> bool:
        if node.timestampLabel and node.timestampLabel not in self.tags:
            self._line(f"{_safe_identifier(node.timestampLabel)} = declare_output_stream()")
            self.tags.append(node.timestampLabel)
        if node.streamAs and node.streamAs not in self.tags:
            if node.streamAs.startswith("atr_"):  # Support for legacy adc stream naming
                self._line(f"{_safe_identifier(node.streamAs)} = declare_output_stream(adc_trace=True)")
            else:
                self._line(f"{_safe_identifier(node.streamAs)} = declare_output_stream()")
            self.tags.append(node.streamAs)
        return self._default_enter(node)

    @property
    def _node_to_visit(self) -> Mapping[type, Callable[[Any], None]]:
        return {
            QuaProgram.ForStatement: self.visit_for,
            QuaProgram.ForEachStatement: self.visit_for_each,
            QuaProgram.IfStatement: self.visit_if,
            QuaProgram.GlobalVariableAssignmentStatement: self.visit_global_variable_assignment,
            QuaProgram.PlayStatement: self.visit_play,
        }

    def visit_for(self, node: QuaProgram.ForStatement) -> None:
        if len(node.body.statements) > 0:
            super()._default_visit(node.body)
        else:
            self._line("pass")

    def visit_for_each(self, node: QuaProgram.ForEachStatement) -> None:
        if len(node.body.statements) > 0:
            super()._default_visit(node.body)
        else:
            self._line("pass")

    def visit_if(self, node: QuaProgram.IfStatement) -> None:
        if len(node.body.statements) > 0:
            super()._default_visit(node.body)
        else:
            self._line("pass")
        elseifs_list = node.elseifs
        for elseif in elseifs_list:
            elseif_block = elseif.body
            condition = elseif.condition
            self._leave_block()
            self._line(f"with elif_({self.serialize_expression(condition)}):")
            self._enter_block()
            if len(elseif_block.statements) > 0:
                super()._default_visit(elseif_block)
            else:
                self._line("pass")

        else_block = getattr(node, "else")
        if len(else_block.statements) > 0:  # Cannot ID else_() with pass
            self._leave_block()
            self._line("with else_():")
            self._enter_block()
            super()._default_visit(else_block)

    def visit_global_variable_assignment(self, node: QuaProgram.GlobalVariableAssignmentStatement) -> None:
        self._used_global_vars = True
        self._line(f"assign_global_var({', '.join([self.serialize_expression(v) for v in node.variables])})")

    def visit_play(self, node: QuaProgram.PlayStatement) -> None:
        pulse_one_of, value = which_one_of(node, "pulseType")
        if pulse_one_of == "namedPulse":
            pulse = _safe_str(node.namedPulse.name)
            # node.pulse - duplicate with namedPulse
        elif pulse_one_of == "rampPulse":
            pulse = f"ramp({self.serialize_expression(node.rampPulse)})"
        else:
            raise QmQuaException(f"Unknown pulse type {pulse_one_of}")

        element = node.qe.name
        amp = ""
        if serialized_on_wire(node.amp):
            v0 = self.serialize_expression(node.amp.v0)
            v1 = self.serialize_expression(node.amp.v1)
            v2 = self.serialize_expression(node.amp.v2)
            v3 = self.serialize_expression(node.amp.v3)
            if v0 != "":
                if v1 != "":
                    amp = f"*amp({v0}, {v1}, {v2}, {v3})"
                else:
                    amp = f"*amp({v0})"
        args = []

        _, duration = which_one_of(node.duration, "expression_oneof")
        if duration is not None:
            args.append(f"duration={self.serialize_expression(duration)}")

        _, condition = which_one_of(node.condition, "expression_oneof")
        if condition is not None:
            args.append(f"condition={self.serialize_expression(condition)}")

        if node.targetInput:
            args.append(f"target={_safe_str(node.targetInput)}")

        if serialized_on_wire(node.chirp):
            rate_one_of, value = which_one_of(node.chirp, "rate")
            if isinstance(value, (QuaProgram.AnyScalarExpression, QuaProgram.ArrayVarRefExpression)):
                rate = self.serialize_expression(value)
            else:
                raise QmQuaException(f"Unknown chirp rate {rate_one_of}")

            unit_mapping = {
                QuaProgram.Chirp.Units.HzPerNanoSec: "Hz/nsec",
                QuaProgram.Chirp.Units.mHzPerNanoSec: "mHz/nsec",
                QuaProgram.Chirp.Units.uHzPerNanoSec: "uHz/nsec",
                QuaProgram.Chirp.Units.nHzPerNanoSec: "nHz/nsec",
                QuaProgram.Chirp.Units.pHzPerNanoSec: "pHz/nsec",
            }
            s_units = node.chirp.units
            if s_units in unit_mapping:
                units = unit_mapping[s_units]
            else:
                raise QmQuaException(f"Unsupported units {s_units}")

            times_builder = []
            for time in node.chirp.times:
                times_builder.append(f"{time}")

            if len(times_builder) > 0:
                times = f'[{", ".join(times_builder)}]'
            else:
                times = "None"

            if node.chirp.continueChirp:
                args.append("continue_chirp=True")

            args.append(f'chirp=({rate},{times},"{units}")')

        _, truncate = which_one_of(node.truncate, "expression_oneof")
        if truncate is not None:
            args.append(f"truncate={self.serialize_expression(truncate)}")

        if node.timestampLabel:
            if node.timestampLabel not in self.tags:
                self._line(f"{_safe_identifier(node.timestampLabel)} = declare_output_stream()")
                self.tags.append(node.timestampLabel)
            args.append(f"timestamp_stream={_safe_identifier(node.timestampLabel)}")

        # TODO maybe make sure no other fields?

        if len(args) > 0:
            args_str = f', {", ".join(args)}'
        else:
            args_str = ""
        indent = ""
        if serialized_on_wire(node.port_condition):
            self._line(f"with port_condition({self.serialize_expression(node.port_condition)}):")
            indent = " " * 4
        self._line(f"{indent}play({pulse}{amp}, {_safe_str(element)}{args_str})")

    def _default_leave(self, node: Message) -> None:
        if isinstance(node, tuple(_blocks)):
            self._leave_block()
        super()._default_leave(node)

    def _enter_block(self, line: Optional[str] = None) -> None:
        if line is not None:
            self._line(line)
        self._indent += 1

    def _leave_block(self) -> None:
        self._indent -= 1

    def _line(self, line: str) -> None:
        self._lines.append((self._indent * "    ") + line)

    @property
    def _expression_visitor(self) -> ExpressionSerializingVisitor:
        return ExpressionSerializingVisitor(self)

    def serialize_expression(self, value: Node) -> str:
        return self._expression_visitor.serialize(value)


def _dict_to_python_call(d: dict[Any, Any]) -> str:
    return ", ".join([f"{k}={v}" for k, v in d.items()])


def _ramp_to_zero_statement(node: QuaProgram.RampToZeroStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(_safe_str(node.qe.name))
    if node.duration is not None:
        args.append(str(node.duration.value))
    return f'ramp_to_zero({", ".join(args)})'


def _measure_statement(node: QuaProgram.MeasureStatement, visitor: QuaSerializingVisitor) -> str:
    args = []

    amp = ""
    v0 = visitor.serialize_expression(node.amp.v0)
    v1 = visitor.serialize_expression(node.amp.v1)
    v2 = visitor.serialize_expression(node.amp.v2)
    v3 = visitor.serialize_expression(node.amp.v3)
    if v0 != "":
        if v1 != "":
            amp = f"*amp({v0}, {v1}, {v2}, {v3})"
        else:
            amp = f"*amp({v0})"

    args.append(f"{_safe_str(node.pulse.name)}{amp}")
    args.append(_safe_str(node.qe.name))

    if len(node.measureProcesses) > 0:
        for process in node.measureProcesses:
            args.append(visitor.serialize_expression(process))
    if node.timestampLabel:
        args.append(f"timestamp_stream={_safe_identifier(node.timestampLabel)}")
    if node.streamAs:
        args.append(f"adc_stream={_safe_identifier(node.streamAs)}")
    return f'measure({", ".join(args)})'


def _load_waveform_statement(node: QuaProgram.LoadWaveformStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(f"pulse={_safe_str(node.pulse.name)}")
    args.append(f"waveform_index={visitor.serialize_expression(node.waveform_index)}")
    args.append(f"element={_safe_str(node.qe.name)}")
    return f'load_waveform({", ".join(args)})'


def _wait_statement(node: QuaProgram.WaitStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    _, wait_value = which_one_of(node.time, "expression_oneof")
    if wait_value is not None:
        args.append(f"{visitor.serialize_expression(wait_value)}")
    qes = []
    for qe in node.qe:
        qes.append(_safe_str(qe.name))
    args.append(", ".join(qes))
    return f'wait({", ".join(args)})'


def _align_statement(node: QuaProgram.AlignStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    for qe in node.qe:
        args.append(_safe_str(qe.name))
    return f'align({", ".join(args)})'


def _wait_for_trigger_statement(node: QuaProgram.WaitForTriggerStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    for qe in node.qe:
        args.append(_safe_str(qe.name))
    if node.pulseToPlay.name:
        args.append(_safe_str(node.pulseToPlay.name))
    output = which_one_of(node, "source")[1]
    if isinstance(output, QuaProgram.WaitForTriggerStatement.ElementOutput) and output.element:
        if node.elementOutput.output:
            args.append(
                f"trigger_element=({_safe_str(node.elementOutput.element)}, {_safe_str(node.elementOutput.output)})"
            )
        else:
            args.append(f"trigger_element={_safe_str(node.elementOutput.element)}")
    if which_one_of(node.timeTagTarget, "var_oneof")[0] == "name":
        args.append(f"time_tag_target={_safe_identifier(node.timeTagTarget.name)}")
    return f'wait_for_trigger({", ".join(args)})'


def _frame_rotation_statement(node: QuaProgram.ZRotationStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(f"{visitor.serialize_expression(node.value)}")
    args.append(_safe_str(node.qe.name))
    return f'frame_rotation_2pi({", ".join(args)})'


def _fast_frame_rotation_statement(node: QuaProgram.FastFrameRotationStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(f"{visitor.serialize_expression(node.cosine)}")
    args.append(f"{visitor.serialize_expression(node.sine)}")
    args.append(_safe_str(node.qe.name))
    return f'fast_frame_rotation({", ".join(args)})'


def _send_to_external_stream(node: QuaProgram.SendToExternalStreamStatement, visitor: QuaSerializingVisitor) -> str:
    name = f"so{node.stream.stream_id}"  # send is only to outgoing streams
    return f"send_to_stream({name}, {_safe_identifier(node.struct.name)})"


def _receive_from_external_stream(
    node: QuaProgram.ReceiveFromExternalStreamStatement, visitor: QuaSerializingVisitor
) -> str:
    name = f"si{node.stream.stream_id}"  # receive is only to incoming streams
    return f"receive_from_stream({name}, target_variable={_safe_identifier(node.struct.name)})"


def _reset_frame_statement(node: QuaProgram.ResetFrameStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(_safe_str(node.qe.name))
    return f'reset_frame({", ".join(args)})'


def _update_frequency_statement(node: QuaProgram.UpdateFrequencyStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(_safe_str(node.qe.name))
    args.append(f"{visitor.serialize_expression(node.value)}")
    args.append(_safe_str(QuaProgram.UpdateFrequencyStatement.Units.Name(node.units)))
    args.append(f"{node.keepPhase}")
    return f'update_frequency({", ".join(args)})'


def _set_dc_offset_statement(node: QuaProgram.SetDcOffsetStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(_safe_str(node.qe.name))
    args.append(_safe_str(node.qeInputReference))
    args.append(f"{visitor.serialize_expression(node.offset)}")
    return f'set_dc_offset({", ".join(args)})'


def _advance_input_stream_statement(
    node: QuaProgram.AdvanceInputStreamStatement, visitor: QuaSerializingVisitor
) -> str:
    stream_value = which_one_of(node, "stream_oneof")[1]
    if isinstance(stream_value, QuaProgram.ArrayVarRefExpression) and stream_value.name != "":
        input_stream = visitor.serialize_expression(stream_value)
    elif isinstance(stream_value, QuaProgram.VarRefExpression) and stream_value.name != "":
        input_stream = visitor.serialize_expression(stream_value)
    else:
        raise RuntimeError("unsupported type for pop input stream")
    return f"advance_input_stream({input_stream})"


def _for_block_statement(node: QuaProgram.ForStatement, visitor: QuaSerializingVisitor) -> str:
    condition = visitor.serialize_expression(node.condition)
    if len(node.init.statements) == 0 and len(node.update.statements) == 0:
        if condition == "True":
            return "with infinite_loop_():"
        else:
            return f"with while_({condition}):"
    else:
        if len(node.init.statements) != 1:
            raise Exception("for is not valid")
        if len(node.update.statements) != 1:
            raise Exception("for is not valid")

        init = node.init.statements[0].assign
        update = node.update.statements[0].assign

        if init is None:
            raise Exception("for is not valid")
        if update is None:
            raise Exception("for is not valid")

        return f"with for_({visitor.serialize_expression(init.target)},{visitor.serialize_expression(init.expression)},{condition},{visitor.serialize_expression(update.expression)}):"


def _for_each_block_statement(node: QuaProgram.ForEachStatement, visitor: QuaSerializingVisitor) -> str:
    variables = []
    arrays = []
    for it in node.iterator:
        variables.append(visitor.serialize_expression(it.variable))
        arrays.append(it.array.name)
    return f'with for_each_(({",".join(variables)}),({",".join(arrays)})):'


def _if_block_statement(node: QuaProgram.IfStatement, visitor: QuaSerializingVisitor) -> str:
    condition = visitor.serialize_expression(node.condition)
    if node.unsafe is True:
        unsafe = ", unsafe=True"
    else:
        unsafe = ""
    return f"with if_({condition}{unsafe}):"


def _strict_timing_block_statement(_: Any, __: Any) -> str:
    return "with strict_timing_():"


def _stream_processing_function(array: MutableSequence[Value]) -> str:
    function = array[0].string_value

    if function == "average":
        if len(array) > 1:
            first_element = array[1]
            v = which_one_of(first_element, "kind")[1]
            if isinstance(v, str):
                var = v
            elif isinstance(v, ListValue):
                var = _stream_processing_operator(v.values)
            else:
                raise NotImplementedError
        else:
            var = ""
        return f"average({var})"

    if function == "dot":
        if len(array) == 1:
            return "tuple_dot_product()"
        else:
            vector = _stream_processing_operator(array[1].list_value.values)
            return f"dot_product({vector})"

    if function == "vmult":
        vector = _stream_processing_operator(array[1].list_value.values)
        return f"multiply_by({vector})"

    if function == "smult":
        return f"multiply_by({array[1].string_value})"

    if function == "tmult":
        return "tuple_multiply()"

    if function == "conv":
        if len(array) == 2:
            if array[1].string_value:
                mode = f'"{array[1].string_value}"'
            else:
                mode = ""
            return f"tuple_convolution({mode})"
        else:
            vector = _stream_processing_operator(array[2].list_value.values)
            if array[1].string_value:
                mode = f',"{array[1].string_value}"'
            else:
                mode = ""
            return f"convolution({vector}{mode})"

    if function == "fft":
        return "fft()"

    if function == "booleancast":
        return "boolean_to_int()"

    if function == "demod":
        if len(array[2].list_value.values) > 0:
            cos = _stream_processing_operator(array[2].list_value.values)
        else:
            cos = array[2].string_value
        if len(array[3].list_value.values) > 0:
            sin = _stream_processing_operator(array[3].list_value.values)
        else:
            sin = array[3].string_value
        return f"demod({array[1].string_value},{cos},{sin})"

    print(f"missing function: {function}")
    return "default_function()"


def _stream_processing_operator(array: MutableSequence[Value]) -> str:
    operator = array[0].string_value

    if operator == "@macro_input":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.input{array[1].string_value}()"

    if operator == "@array":
        values = []
        for a in array[1:]:
            value = _stream_processing_statement(a)
            values.append(value)
        return f'[{", ".join(values)}]'

    if operator == "@macro_auto_reshape":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.auto_reshape()"

    if operator == "+":
        left = _stream_processing_statement(array[1])
        right = _stream_processing_statement(array[2])
        return f"{left}.add({right})"  # arithmetic stream

    if operator == "-":
        left = _stream_processing_statement(array[1])
        right = _stream_processing_statement(array[2])
        return f"{left}.subtract({right})"  # arithmetic stream

    if operator == "/":
        left = _stream_processing_statement(array[1])
        right = _stream_processing_statement(array[2])
        return f"{left}.divide({right})"  # arithmetic stream

    if operator == "*":
        left = _stream_processing_statement(array[1])
        right = _stream_processing_statement(array[2])
        return f"{left}.multiply({right})"  # arithmetic stream

    if operator == "zip":
        left = _stream_processing_statement(array[1])
        right = _stream_processing_statement(array[2])
        return f"{right}.zip({left})"  # arithmetic stream

    if operator == "take":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.take({array[1].string_value})"

    if operator == "buffer":
        chain = _default_stream_processing_chain(array)
        dims = [dim.string_value for dim in array[1:-1]]
        return f'{chain}.buffer({", ".join(dims)})'

    if operator == "bufferAndSkip":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.buffer_and_skip({array[1].string_value}, {array[2].string_value})"

    if operator == "skip":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.skip({array[1].string_value})"

    if operator == "skipLast":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.skip_last({array[1].string_value})"

    if operator == "histogram":
        chain = _default_stream_processing_chain(array)
        bins = _stream_processing_operator(array[1].list_value.values)
        return f"{chain}.histogram({bins})"

    if operator == "average":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.average()"

    if operator == "real":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.real()"

    if operator == "image":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.image()"

    if operator == "flatten":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.flatten()"

    if operator == "map":
        chain = _default_stream_processing_chain(array)
        return f"{chain}.map(FUNCTIONS.{_stream_processing_function(array[1].list_value.values)})"

    if operator == "@re":
        chain = _default_stream_processing_chain(array)
        timestamp_mode = int(array[1].string_value)
        if timestamp_mode == 0:  # values
            return f"{chain}"
        elif timestamp_mode == 1:  # timestamps
            return f"{chain}.timestamps()"
        elif timestamp_mode == 2:  # ValuesAndTimestamps
            return f"{chain}.with_timestamps()"

    if operator == "@macro_adc_trace":
        chain = _default_stream_processing_chain(array)
        return f"{chain}"

    print(f"missing operator: {operator}")
    chain = _default_stream_processing_chain(array)
    return f"{chain}"


def _default_stream_processing_chain(array: MutableSequence[Value]) -> str:
    last_index = len(array) - 1
    chain = _stream_processing_statement(array[last_index])
    return f"{chain}"


def _stream_processing_statement(node: Value) -> str:
    _value = which_one_of(node, "kind")[1]
    if isinstance(_value, ListValue) and len(_value.values) > 0:
        return _stream_processing_operator(_value.values)
    elif isinstance(_value, str):
        return _value
    else:
        raise NotImplementedError(f"Unsupported stream processing statement: {_value}")


def _stream_processing_terminal_statement(node: ListValue, visitor: QuaSerializingVisitor) -> str:
    last_index = len(node.values) - 1
    chain = _stream_processing_statement(node.values[last_index])
    terminal = node.values[0].string_value
    terminal = "save_all" if terminal == "saveAll" else terminal  # normalize save all
    return f'{chain}.{terminal}("{node.values[1].string_value}")'


def _update_correction_statement(node: QuaProgram.UpdateCorrectionStatement, visitor: QuaSerializingVisitor) -> str:
    return (
        f"update_correction({_safe_str(node.qe.name)},{visitor.serialize_expression(node.correction.c0)},"
        f"{visitor.serialize_expression(node.correction.c1)},"
        f"{visitor.serialize_expression(node.correction.c2)},"
        f"{visitor.serialize_expression(node.correction.c3)})"
    )


def _assignment_statement(node: QuaProgram.AssignmentStatement, visitor: QuaSerializingVisitor) -> str:
    return f"assign({visitor.serialize_expression(node.target)}, " f"{visitor.serialize_expression(node.expression)})"


def _serialize(node: Node) -> list[str]:
    visitor = QuaSerializingVisitor()
    visitor.visit(node)
    return visitor._out_lines()


_blocks = {
    QuaProgram: lambda n, v: "with program() as prog:",
    QuaProgram.ForStatement: _for_block_statement,
    QuaProgram.ForEachStatement: _for_each_block_statement,
    QuaProgram.IfStatement: _if_block_statement,
    QuaProgram.StrictTimingStatement: _strict_timing_block_statement,
}


_statements = {
    QuaProgram.MeasureStatement: _measure_statement,
    QuaProgram.WaitStatement: _wait_statement,
    QuaProgram.AssignmentStatement: _assignment_statement,
    QuaProgram.PauseStatement: lambda n, v: "pause()",
    QuaProgram.ResetPhaseStatement: lambda n, v: f"reset_if_phase({_safe_str(n.qe.name)})",
    QuaProgram.ResetGlobalPhaseStatement: lambda n, v: "reset_global_phase()",
    QuaProgram.UpdateFrequencyStatement: _update_frequency_statement,
    QuaProgram.AlignStatement: _align_statement,
    QuaProgram.WaitForTriggerStatement: _wait_for_trigger_statement,
    QuaProgram.ZRotationStatement: _frame_rotation_statement,
    QuaProgram.RampToZeroStatement: _ramp_to_zero_statement,
    QuaProgram.ResetFrameStatement: _reset_frame_statement,
    ListValue: _stream_processing_terminal_statement,
    # list value statement is assumed just as stream processing for now
    QuaProgram.UpdateCorrectionStatement: _update_correction_statement,
    QuaProgram.SetDcOffsetStatement: _set_dc_offset_statement,
    QuaProgram.AdvanceInputStreamStatement: _advance_input_stream_statement,
    QuaProgram.FastFrameRotationStatement: _fast_frame_rotation_statement,
    QuaProgram.LoadWaveformStatement: _load_waveform_statement,
    QuaProgram.SendToExternalStreamStatement: _send_to_external_stream,
    QuaProgram.ReceiveFromExternalStreamStatement: _receive_from_external_stream,
}

_var_type_dec = {
    QuaProgram.Type.INT: "int",
    QuaProgram.Type.BOOL: "bool",
    QuaProgram.Type.REAL: "fixed",
}

_nodes_to_ignore = {
    QuaProgram.Script,
    QuaProgram.StatementsCollection,
    QuaProgram.AnyStatement,
    QuaProgram.AnyScalarExpression,
    QuaProgram.BinaryExpression,
    QuaProgram.VarRefExpression,
    QuaProgram.LiteralExpression,
    QuaProgram.PlayStatement,
    QuaConfig,
}

_dont_print = set(_blocks) | set(_statements) | _nodes_to_ignore
