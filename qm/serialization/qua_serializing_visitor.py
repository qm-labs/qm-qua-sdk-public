import re
import logging
from typing import Any, Dict, List, Tuple, Callable, Optional

import betterproto
from betterproto.lib.google.protobuf import Value, ListValue

import qm
from qm.grpc import qua
from qm.exceptions import QmQuaException
from qm.grpc.qua_config import QuaConfig
from qm.utils.protobuf_utils import Node
from qm.serialization.qua_node_visitor import QuaNodeVisitor
from qm.serialization.expression_serializing_visitor import ExpressionSerializingVisitor
from qm.grpc.qua import (
    QuaProgram,
    QuaProgramType,
    QuaProgramScript,
    QuaProgramIfStatement,
    QuaProgramAnyStatement,
    QuaProgramForStatement,
    QuaProgramPlayStatement,
    QuaProgramWaitStatement,
    QuaProgramAlignStatement,
    QuaProgramPauseStatement,
    QuaProgramVarDeclaration,
    QuaProgramBinaryExpression,
    QuaProgramForEachStatement,
    QuaProgramMeasureStatement,
    QuaProgramVarRefExpression,
    QuaProgramLiteralExpression,
    QuaProgramZRotationStatement,
    QuaProgramAnyScalarExpression,
    QuaProgramAssignmentStatement,
    QuaProgramRampToZeroStatement,
    QuaProgramResetFrameStatement,
    QuaProgramResetPhaseStatement,
    QuaProgramSetDcOffsetStatement,
    QuaProgramStatementsCollection,
    QuaProgramArrayVarRefExpression,
    QuaProgramLoadWaveformStatement,
    QuaProgramStrictTimingStatement,
    QuaProgramWaitForTriggerStatement,
    QuaProgramUpdateFrequencyStatement,
    QuaProgramResetGlobalPhaseStatement,
    QuaProgramUpdateCorrectionStatement,
    QuaProgramFastFrameRotationStatement,
    QuaProgramAdvanceInputStreamStatement,
    QuaProgramSendToExternalStreamStatement,
    QuaProgramReceiveFromExternalStreamStatement,
    QuaProgramWaitForTriggerStatementElementOutput,
)

logger = logging.getLogger(__name__)


class StructDeclaration:
    def __init__(self, type_name: str, variable_name: str) -> None:
        self._name: str = type_name
        self.variable_name: str = variable_name
        self._variables: Dict[str, Tuple[str, int]] = {}

    def variables(self) -> List[str]:
        return list(self._variables.keys())

    def add_variable(self, name: str, var_type: QuaProgramType, size: int) -> None:
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
        self.structs: List[StructDeclaration] = []
        self._lines: List[str] = []
        self.tags: List[str] = []

    def _format_imports(self) -> str:
        output = ""

        if self.structs:
            output += "\nfrom typing import Literal\n"

        output += """
from qm import CompilerOptionArguments
from qm.qua import *

"""
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

    def _out_lines(self) -> List[str]:
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
    def _search_auto_added_stream(values: List[Value]) -> bool:
        v2 = values[2]
        is_auto_added_result = isinstance(v2, Value) and betterproto.which_one_of(v2, "kind") == (
            "string_value",
            "auto",
        )
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
                if self._lines[i].find(f"{trace_name} = declare_stream") > 0:
                    line_to_remove_index = i
                self._lines[i] = re.sub(r"(?<=\W|\^)" + trace_name + r"(?=\W|\$)", f'"{save_name}"', self._lines[i])
            if line_to_remove_index:
                self._lines.pop(line_to_remove_index)

    def enter_qm_grpc_qua_QuaProgramCompilerOptions(self, node: qua.QuaProgramCompilerOptions) -> bool:
        options_list = []
        if node.strict:
            options_list.append(f"strict={node.strict}")
        if len(node.flags) > 0:
            options_list.append(f"flags={node.flags}")
        options_string = ", ".join(options_list)
        if len(options_string) > 0:
            self._lines.insert(0, f"compiler_options = CompilerOptionArguments({options_string})\n")

        return False

    def enter_qm_grpc_qua_QuaResultAnalysis(self, node: qua.QuaResultAnalysis) -> bool:
        if len(node.model) > 0:
            self._enter_block("with stream_processing():")
            return True
        else:
            return False

    def enter_qm_grpc_qua_QuaProgramSaveStatement(self, node: qua.QuaProgramSaveStatement) -> bool:
        if node.tag not in self.tags:
            self._line(f"{node.tag} = declare_stream()")
            self.tags.append(node.tag)
        save_line = f"save({self.serialize_expression(node.source)}, {node.tag})"
        self._line(save_line)
        return False

    def enter_qm_grpc_qua_QuaProgramVarDeclaration(self, node: qua.QuaProgramVarDeclaration) -> bool:
        if self._check_if_has_struct(node):
            return False

        args = self._get_declare_var_args(node)

        if node.is_input_stream:
            # Removes the '_input_stream' from the end of the name
            stream_name = node.name[13:]
            self._line(
                f"{node.name} = declare_input_stream({_var_type_dec[node.type]}, '{stream_name}', {_dict_to_python_call(args)})"
            )
        else:
            self._line(f"{node.name} = declare({_var_type_dec[node.type]}, {_dict_to_python_call(args)})")

        return False

    def _check_if_has_struct(self, node: qua.QuaProgramVarDeclaration) -> bool:
        if node.struct_member is None or not betterproto.serialized_on_wire(node.struct_member):
            return False

        struct: Optional[StructDeclaration] = None
        for _struct in self.structs:
            if _struct.variable_name == node.struct_member.name:
                struct = _struct
                break

        if struct is None:
            struct = StructDeclaration(f"Struct{node.struct_member.name}", node.struct_member.name)
            self.structs.append(struct)

        struct.add_variable(node.name, node.type, node.size)
        return True

    def enter_qm_grpc_qua_QuaProgramExternalStreamDeclaration(
        self, node: qua.QuaProgramExternalStreamDeclaration
    ) -> bool:
        struct_type = self._create_struct_from_expected_types(node)
        if node.direction == qua.QuaProgramDirection.INCOMING:
            name_prefix = "i"
        else:
            name_prefix = "o"

        var_name = f"s{name_prefix}{node.stream_id}"
        self._line(
            f"{var_name} = declare_external_stream({struct_type}, {node.stream_id}, QuaStreamDirection.{self.stream_direction_to_string(node.direction)})"
        )

        return False

    def _create_struct_from_expected_types(self, node: qua.QuaProgramExternalStreamDeclaration) -> str:
        struct_class_name = (
            f"StructStream{self.stream_direction_to_string(node.direction).capitalize()}{node.stream_id}"
        )
        struct = StructDeclaration(struct_class_name, "")

        for index, expected_type in enumerate(node.expected_types):
            struct.add_variable(f"variable_{index}", expected_type.type, expected_type.size)
        self.structs.append(struct)
        return struct_class_name

    @staticmethod
    def stream_direction_to_string(stream_direction: qua.QuaProgramDirection) -> str:
        if stream_direction == qua.QuaProgramDirection.INCOMING:
            return "INCOMING"
        elif stream_direction == qua.QuaProgramDirection.OUTGOING:
            return "OUTGOING"
        else:
            raise ValueError(f"Unknown stream direction {stream_direction}")

    def enter_betterproto_lib_std_google_protobuf_ListValue(
        self, node: betterproto.lib.google.protobuf.ListValue
    ) -> bool:
        line = _stream_processing_terminal_statement(node, self)
        self._line(line)
        self._fix_legacy_save(line, node)
        return False

    def leave_qm_grpc_qua_QuaProgram(self, node: qm.grpc.qua.QuaProgram) -> bool:
        if self._lines[-1].find("with stream_processing():") > 0:
            self._lines.pop()
        return False

    def _get_declare_var_args(self, node: QuaProgramVarDeclaration) -> Dict[str, str]:
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

    def enter_qm_grpc_qua_QuaProgramMeasureStatement(self, node: qua.QuaProgramMeasureStatement) -> bool:
        if node.timestamp_label and node.timestamp_label not in self.tags:
            self._line(f"{node.timestamp_label} = declare_stream()")
            self.tags.append(node.timestamp_label)
        if node.stream_as and node.stream_as not in self.tags:
            if node.stream_as.startswith("atr_"):
                self._line(f"{node.stream_as} = declare_stream(adc_trace=True)")
            else:
                self._line(f"{node.stream_as} = declare_stream()")
            self.tags.append(node.stream_as)
        return self._default_enter(node)

    def visit_qm_grpc_qua_QuaProgramForStatement(self, node: qua.QuaProgramForStatement) -> None:
        if len(node.body.statements) > 0:
            super()._default_visit(node.body)
        else:
            self._line("pass")

    def visit_qm_grpc_qua_QuaProgramForEachStatement(self, node: qua.QuaProgramForEachStatement) -> None:
        if len(node.body.statements) > 0:
            super()._default_visit(node.body)
        else:
            self._line("pass")

    def visit_qm_grpc_qua_QuaProgramIfStatement(self, node: qua.QuaProgramIfStatement) -> None:
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

        else_block = node.else_
        if len(else_block.statements) > 0:  # Cannot ID else_() with pass
            self._leave_block()
            self._line("with else_():")
            self._enter_block()
            super()._default_visit(else_block)

    def visit_qm_grpc_qua_QuaProgramPlayStatement(self, node: qua.QuaProgramPlayStatement) -> None:
        pulse_one_of, value = betterproto.which_one_of(node, "pulseType")
        if pulse_one_of == "named_pulse":
            pulse = f'"{node.named_pulse.name}"'
            # node.pulse - duplicate with namedPulse
        elif pulse_one_of == "ramp_pulse":
            pulse = f"ramp({self.serialize_expression(node.ramp_pulse)})"
        else:
            raise QmQuaException(f"Unknown pulse type {pulse_one_of}")

        element = node.qe.name
        amp = ""
        if betterproto.serialized_on_wire(node.amp):
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

        _, duration = betterproto.which_one_of(node.duration, "expression_oneof")
        if duration is not None:
            args.append(f"duration={self.serialize_expression(duration)}")

        _, condition = betterproto.which_one_of(node.condition, "expression_oneof")
        if condition is not None:
            args.append(f"condition={self.serialize_expression(condition)}")

        if node.target_input:
            args.append(f'target="{node.target_input}"')

        if betterproto.serialized_on_wire(node.chirp):
            rate_one_of, value = betterproto.which_one_of(node.chirp, "rate")
            if isinstance(value, (QuaProgramAnyScalarExpression, QuaProgramArrayVarRefExpression)):
                rate = self.serialize_expression(value)
            else:
                raise QmQuaException(f"Unknown chirp rate {rate_one_of}")

            unit_mapping = {
                qua.QuaProgramChirpUnits.HzPerNanoSec: "Hz/nsec",
                qua.QuaProgramChirpUnits.mHzPerNanoSec: "mHz/nsec",
                qua.QuaProgramChirpUnits.uHzPerNanoSec: "uHz/nsec",
                qua.QuaProgramChirpUnits.nHzPerNanoSec: "nHz/nsec",
                qua.QuaProgramChirpUnits.pHzPerNanoSec: "pHz/nsec",
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

            if node.chirp.continue_chirp:
                args.append("continue_chirp=True")

            args.append(f'chirp=({rate},{times},"{units}")')

        _, truncate = betterproto.which_one_of(node.truncate, "expression_oneof")
        if truncate is not None:
            args.append(f"truncate={self.serialize_expression(truncate)}")

        if node.timestamp_label:
            if node.timestamp_label not in self.tags:
                self._line(f"{node.timestamp_label} = declare_stream()")
                self.tags.append(node.timestamp_label)
            args.append(f"timestamp_stream={node.timestamp_label}")

        # TODO maybe make sure no other fields?

        if len(args) > 0:
            args_str = f', {", ".join(args)}'
        else:
            args_str = ""
        indent = ""
        if betterproto.serialized_on_wire(node.port_condition):
            self._line(f"with port_condition({self.serialize_expression(node.port_condition)}):")
            indent = " " * 4
        self._line(f'{indent}play({pulse}{amp}, "{element}"{args_str})')

    def _default_leave(self, node: Node) -> None:
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


def _dict_to_python_call(d: Dict[Any, Any]) -> str:
    return ", ".join([f"{k}={v}" for k, v in d.items()])


def _ramp_to_zero_statement(node: QuaProgramRampToZeroStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(f'"{node.qe.name}"')
    if node.duration is not None:
        args.append(str(node.duration))
    return f'ramp_to_zero({", ".join(args)})'


def _measure_statement(node: qua.QuaProgramMeasureStatement, visitor: QuaSerializingVisitor) -> str:
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

    args.append(f'"{node.pulse.name}"{amp}')
    args.append(f'"{node.qe.name}"')

    if len(node.measure_processes) > 0:
        for process in node.measure_processes:
            args.append(visitor.serialize_expression(process))
    if node.timestamp_label:
        args.append(f"timestamp_stream={node.timestamp_label}")
    if node.stream_as:
        args.append(f"adc_stream={node.stream_as}")
    return f'measure({", ".join(args)})'


def _load_waveform_statement(node: qua.QuaProgramLoadWaveformStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(f'pulse="{node.pulse.name}"')
    args.append(f"waveform_index={visitor.serialize_expression(node.waveform_index)}")
    args.append(f'element="{node.qe.name}"')
    return f'load_waveform({", ".join(args)})'


def _wait_statement(node: qua.QuaProgramWaitStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    _, wait_value = betterproto.which_one_of(node.time, "expression_oneof")
    if wait_value is not None:
        args.append(f"{visitor.serialize_expression(wait_value)}")
    qes = []
    for qe in node.qe:
        qes.append(f'"{qe.name}"')
    args.append(", ".join(qes))
    return f'wait({", ".join(args)})'


def _align_statement(node: QuaProgramAlignStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    for qe in node.qe:
        args.append(f'"{qe.name}"')
    return f'align({", ".join(args)})'


def _wait_for_trigger_statement(node: qua.QuaProgramWaitForTriggerStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    for qe in node.qe:
        args.append(f'"{qe.name}"')
    if node.pulse_to_play.name:
        args.append(f'"{node.pulse_to_play.name}"')
    output = betterproto.which_one_of(node, "source")[1]
    if isinstance(output, QuaProgramWaitForTriggerStatementElementOutput) and output.element:
        if node.element_output.output:
            args.append(f'trigger_element=("{node.element_output.element}", "{node.element_output.output}")')
        else:
            args.append(f'trigger_element="{node.element_output.element}"')
    if betterproto.which_one_of(node.time_tag_target, "var_oneof")[0] == "name":
        args.append(f"time_tag_target={node.time_tag_target.name}")
    return f'wait_for_trigger({", ".join(args)})'


def _frame_rotation_statement(node: QuaProgramZRotationStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(f"{visitor.serialize_expression(node.value)}")
    args.append(f'"{node.qe.name}"')
    return f'frame_rotation_2pi({", ".join(args)})'


def _fast_frame_rotation_statement(node: QuaProgramFastFrameRotationStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(f"{visitor.serialize_expression(node.cosine)}")
    args.append(f"{visitor.serialize_expression(node.sine)}")
    args.append(f'"{node.qe.name}"')
    return f'fast_frame_rotation({", ".join(args)})'


def _send_to_external_stream(node: QuaProgramSendToExternalStreamStatement, visitor: QuaSerializingVisitor) -> str:
    name = f"so{node.stream.stream_id}"  # send is only to outgoing streams
    return f"send_to_external_stream({name}, {node.struct.name})"


def _receive_from_external_stream(
    node: QuaProgramReceiveFromExternalStreamStatement, visitor: QuaSerializingVisitor
) -> str:
    name = f"si{node.stream.stream_id}"  # receive is only to incoming streams
    return f"receive_from_external_stream({name}, {node.struct.name})"


def _reset_frame_statement(node: QuaProgramResetFrameStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(f'"{node.qe.name}"')
    return f'reset_frame({", ".join(args)})'


def _update_frequency_statement(node: QuaProgramUpdateFrequencyStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(f'"{node.qe.name}"')
    args.append(f"{visitor.serialize_expression(node.value)}")
    args.append(f'"{qua.QuaProgramUpdateFrequencyStatementUnits(node.units).name}"')
    args.append(f"{node.keep_phase}")
    return f'update_frequency({", ".join(args)})'


def _set_dc_offset_statement(node: qua.QuaProgramSetDcOffsetStatement, visitor: QuaSerializingVisitor) -> str:
    args = []
    args.append(f'"{node.qe.name}"')
    args.append(f'"{node.qe_input_reference}"')
    args.append(f"{visitor.serialize_expression(node.offset)}")
    return f'set_dc_offset({", ".join(args)})'


def _advance_input_stream_statement(node: QuaProgramAdvanceInputStreamStatement, visitor: QuaSerializingVisitor) -> str:
    stream_value = betterproto.which_one_of(node, "stream_oneof")[1]
    if isinstance(stream_value, QuaProgramArrayVarRefExpression) and stream_value.name != "":
        input_stream = visitor.serialize_expression(stream_value)
    elif isinstance(stream_value, QuaProgramVarRefExpression) and stream_value.name != "":
        input_stream = visitor.serialize_expression(stream_value)
    else:
        raise RuntimeError("unsupported type for pop input stream")
    return f"advance_input_stream({input_stream})"


def _for_block_statement(node: QuaProgramForStatement, visitor: QuaSerializingVisitor) -> str:
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


def _for_each_block_statement(node: QuaProgramForEachStatement, visitor: QuaSerializingVisitor) -> str:
    variables = []
    arrays = []
    for it in node.iterator:
        variables.append(visitor.serialize_expression(it.variable))
        arrays.append(it.array.name)
    return f'with for_each_(({",".join(variables)}),({",".join(arrays)})):'


def _if_block_statement(node: QuaProgramIfStatement, visitor: QuaSerializingVisitor) -> str:
    condition = visitor.serialize_expression(node.condition)
    if node.unsafe is True:
        unsafe = ", unsafe=True"
    else:
        unsafe = ""
    return f"with if_({condition}{unsafe}):"


def _strict_timing_block_statement(_: Any, __: Any) -> str:
    return "with strict_timing_():"


def _stream_processing_function(array: List[Value]) -> str:
    function = array[0].string_value

    if function == "average":
        if len(array) > 1:
            first_element = array[1]
            v = betterproto.which_one_of(first_element, "kind")[1]
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


def _stream_processing_operator(array: List[Value]) -> str:
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


def _default_stream_processing_chain(array: List[Value]) -> str:
    last_index = len(array) - 1
    chain = _stream_processing_statement(array[last_index])
    return f"{chain}"


def _stream_processing_statement(node: Value) -> str:
    _value = betterproto.which_one_of(node, "kind")[1]
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


def _update_correction_statement(node: QuaProgramUpdateCorrectionStatement, visitor: QuaSerializingVisitor) -> str:
    return (
        f'update_correction("{node.qe.name}",{visitor.serialize_expression(node.correction.c0)},'
        f"{visitor.serialize_expression(node.correction.c1)},"
        f"{visitor.serialize_expression(node.correction.c2)},"
        f"{visitor.serialize_expression(node.correction.c3)})"
    )


def _assignment_statement(node: QuaProgramAssignmentStatement, visitor: QuaSerializingVisitor) -> str:
    return f"assign({visitor.serialize_expression(node.target)}, " f"{visitor.serialize_expression(node.expression)})"


def _serialize(node: Node) -> List[str]:
    visitor = QuaSerializingVisitor()
    visitor.visit(node)
    return visitor._out_lines()


_blocks = {
    QuaProgram: lambda n, v: "with program() as prog:",
    QuaProgramForStatement: _for_block_statement,
    QuaProgramForEachStatement: _for_each_block_statement,
    QuaProgramIfStatement: _if_block_statement,
    QuaProgramStrictTimingStatement: _strict_timing_block_statement,
}


_statements = {
    QuaProgramMeasureStatement: _measure_statement,
    QuaProgramWaitStatement: _wait_statement,
    QuaProgramAssignmentStatement: _assignment_statement,
    QuaProgramPauseStatement: lambda n, v: "pause()",
    QuaProgramResetPhaseStatement: lambda n, v: f'reset_if_phase("{n.qe.name}")',
    QuaProgramResetGlobalPhaseStatement: lambda n, v: "reset_global_phase()",
    QuaProgramUpdateFrequencyStatement: _update_frequency_statement,
    QuaProgramAlignStatement: _align_statement,
    QuaProgramWaitForTriggerStatement: _wait_for_trigger_statement,
    QuaProgramZRotationStatement: _frame_rotation_statement,
    QuaProgramRampToZeroStatement: _ramp_to_zero_statement,
    QuaProgramResetFrameStatement: _reset_frame_statement,
    ListValue: _stream_processing_terminal_statement,
    # list value statement is assumed just as stream processing for now
    QuaProgramUpdateCorrectionStatement: _update_correction_statement,
    QuaProgramSetDcOffsetStatement: _set_dc_offset_statement,
    QuaProgramAdvanceInputStreamStatement: _advance_input_stream_statement,
    QuaProgramFastFrameRotationStatement: _fast_frame_rotation_statement,
    QuaProgramLoadWaveformStatement: _load_waveform_statement,
    QuaProgramSendToExternalStreamStatement: _send_to_external_stream,
    QuaProgramReceiveFromExternalStreamStatement: _receive_from_external_stream,
}

_var_type_dec = {QuaProgramType.INT: "int", QuaProgramType.BOOL: "bool", QuaProgramType.REAL: "fixed"}

_nodes_to_ignore = {
    QuaProgramScript,
    QuaProgramStatementsCollection,
    QuaProgramAnyStatement,
    QuaProgramAnyScalarExpression,
    QuaProgramBinaryExpression,
    QuaProgramVarRefExpression,
    QuaProgramLiteralExpression,
    QuaProgramPlayStatement,
    QuaConfig,
}

_dont_print = set(_blocks) | set(_statements) | _nodes_to_ignore
