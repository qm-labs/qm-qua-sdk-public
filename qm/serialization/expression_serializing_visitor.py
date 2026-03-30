from typing import TYPE_CHECKING, Any, Union, Literal, Mapping, Callable, Optional

from qm.exceptions import QmQuaException
from qm.grpc.qm.pb.inc_qua_pb2 import QuaProgram
from qm.utils.protobuf_utils import Node, which_one_of
from qm.serialization.qua_node_visitor import QuaNodeVisitor

if TYPE_CHECKING:
    from qm.serialization.qua_serializing_visitor import QuaSerializingVisitor


class ExpressionSerializingVisitor(QuaNodeVisitor):
    def __init__(self, visitor: Optional["QuaSerializingVisitor"]) -> None:
        self._out = ""
        self._visitor = visitor
        super().__init__()

    @property
    def _node_to_visit(self) -> Mapping[type, Callable[[Any], None]]:
        return {
            QuaProgram.LibFunctionExpression: self.visit_lib_function_expression,
            QuaProgram.LibFunctionExpression.Argument: self.visit_lib_function_argument,
            QuaProgram.VarRefExpression: self.visit_var_reference,
            QuaProgram.ArrayVarRefExpression: self.visit_array_var_reference,
            QuaProgram.ArrayCellRefExpression: self.visit_array_cell_reference,
            QuaProgram.ArrayLengthExpression: self.visit_array_length,
            QuaProgram.LiteralExpression: self.visit_literal,
            QuaProgram.BroadcastExpression: self.visit_broadcast_expression,
            QuaProgram.FunctionExpression: self.visit_function_expression,
            QuaProgram.FunctionExpression.ScalarOrVectorArgument: self.visit_function_scalar_or_vector_argument,
            QuaProgram.AnalogMeasureProcess.DemodIntegration: self.visit_analog_measurement_demod_integration,
            QuaProgram.AnalogMeasureProcess.BareIntegration: self.visit_analog_measure_bare_integration,
            QuaProgram.AnalogMeasureProcess.DualDemodIntegration: self.visit_analog_measurement_dual_demod_integration,
            QuaProgram.AnalogMeasureProcess.RawTimeTagging: self.visit_analog_measurement_raw_time_tagging,
            QuaProgram.AnalogMeasureProcess.HighResTimeTagging: self.visit_analog_measurement_high_res_time_tagging,
            QuaProgram.DigitalMeasureProcess.Counting: self.visit_digital_measurement_counting,
            QuaProgram.DigitalMeasureProcess.RawTimeTagging: self.visit_digital_measurement_raw_time_tagging,
            QuaProgram.BinaryExpression: self.visit_binary_expression,
            QuaProgram.GlobalVarRefExpression: self.visit_global_var_reference,
        }

    def visit_lib_function_expression(self, node: QuaProgram.LibFunctionExpression) -> None:
        args = [ExpressionSerializingVisitor(self._visitor).serialize(arg) for arg in node.arguments]
        if node.libraryName == "random":
            seed = args.pop(0)
            self._out = f"Random({seed}).{node.functionName}({', '.join(args)})"
        else:
            library_name = {
                "util": "Util",
                "math": "Math",
                "cast": "Cast",
            }.get(node.libraryName, None)
            function_name = {
                "cond": "cond",
                "unsafe_cast_fixed": "unsafe_cast_fixed",
                "unsafe_cast_bool": "unsafe_cast_bool",
                "unsafe_cast_int": "unsafe_cast_int",
                "to_int": "to_int",
                "to_bool": "to_bool",
                "to_fixed": "to_fixed",
                "mul_fixed_by_int": "mul_fixed_by_int",
                "mul_int_by_fixed": "mul_int_by_fixed",
                "log": "log",
                "pow": "pow",
                "div": "div",
                "exp": "exp",
                "pow2": "pow2",
                "ln": "ln",
                "log2": "log2",
                "log10": "log10",
                "sqrt": "sqrt",
                "inv_sqrt": "inv_sqrt",
                "inv": "inv",
                "MSB": "msb",
                "elu": "elu",
                "aelu": "aelu",
                "selu": "selu",
                "relu": "relu",
                "plrelu": "plrelu",
                "lrelu": "lrelu",
                "sin2pi": "sin2pi",
                "cos2pi": "cos2pi",
                "atan_2pi": "atan_2pi",
                "atan2_2pi": "atan2_2pi",
                "abs": "abs",
                "sin": "sin",
                "cos": "cos",
                "atan": "atan",
                "atan2": "atan2",
                "sum": "sum",
                "max": "max",
                "min": "min",
                "argmax": "argmax",
                "argmin": "argmin",
                "dot": "dot",
            }.get(node.functionName, None)
            if library_name is None:
                raise Exception(f"Unsupported library name {node.libraryName}")
            if function_name is None:
                raise Exception(f"Unsupported function name {node.functionName}")

            self._out = f"{library_name}.{function_name}({','.join(args)})"

    def visit_lib_function_argument(self, node: QuaProgram.LibFunctionExpression.Argument) -> None:
        _, value = which_one_of(node, "argument_oneof")
        if value is not None:
            self._out = ExpressionSerializingVisitor(self._visitor).serialize(value)

    def visit_var_reference(self, node: QuaProgram.VarRefExpression) -> None:
        var_ref = which_one_of(node, "var_oneof")[1]
        self._out = node.name if isinstance(var_ref, str) else f"IO{var_ref}"

    def visit_array_var_reference(self, node: QuaProgram.ArrayVarRefExpression) -> None:
        if self._visitor:
            for struct in self._visitor.structs:
                if node.name in struct.variables():
                    self._out = f"{struct.variable_name}. {node.name}"

        if self._out == "":
            self._out = node.name

    def visit_array_cell_reference(self, node: QuaProgram.ArrayCellRefExpression) -> None:
        var = ExpressionSerializingVisitor(self._visitor).serialize(node.arrayVar)
        index = ExpressionSerializingVisitor(self._visitor).serialize(node.index)
        self._out = f"{var}[{index}]"

    def visit_array_length(self, node: QuaProgram.ArrayLengthExpression) -> None:
        var = ExpressionSerializingVisitor(self._visitor).serialize(node.array)
        self._out = f"{var}.length()"

    def visit_literal(self, node: QuaProgram.LiteralExpression) -> None:
        self._out = node.value

    def visit_broadcast_expression(self, node: QuaProgram.BroadcastExpression) -> None:
        value = node.value
        serialized_value = ExpressionSerializingVisitor(self._visitor).serialize(value)
        self._out = f"broadcast. {serialized_value}"

    def visit_function_expression(self, node: QuaProgram.FunctionExpression) -> None:
        function_name, function_expression = which_one_of(node, "function_oneof")
        # During proto class generation, function names that are reserved keywords are suffixed with an underscore.
        # Conversely, functions already suffixed with an underscore (but are not reserved keywords) are saved without
        # the underscore.  For example, 'xor_' (not a reserved keyword) will be saved as 'xor'.
        if not function_name.endswith("_"):
            function_name += "_"

        # For mypy
        if not isinstance(
            function_expression,
            (
                QuaProgram.FunctionExpression.AndFunction,
                QuaProgram.FunctionExpression.OrFunction,
                QuaProgram.FunctionExpression.XorFunction,
            ),
        ):
            raise QmQuaException(f"Got non expected type for function_oneof, got {type(function_expression)}")

        function_arguments = [
            ExpressionSerializingVisitor(self._visitor).serialize(arg) for arg in function_expression.values
        ]

        self._out = f"{function_name}({', '.join(function_arguments)})"

    def visit_function_scalar_or_vector_argument(
        self, node: QuaProgram.FunctionExpression.ScalarOrVectorArgument
    ) -> None:
        _, value = which_one_of(node, "argument_oneof")
        if value is not None:
            self._out = ExpressionSerializingVisitor(self._visitor).serialize(value)

    def visit_analog_measurement_demod_integration(
        self, node: QuaProgram.AnalogMeasureProcess.DemodIntegration
    ) -> None:
        self._common_integration(node, "demod")

    def visit_analog_measure_bare_integration(self, node: QuaProgram.AnalogMeasureProcess.BareIntegration) -> None:
        self._common_integration(node, "integration")

    def _common_integration(
        self,
        node: Union[QuaProgram.AnalogMeasureProcess.BareIntegration, QuaProgram.AnalogMeasureProcess.DemodIntegration],
        integration_type: Literal["integration", "demod"],
    ) -> None:
        name = node.integration.name
        output = node.elementOutput
        target_name, target_value = which_one_of(node.target, "processTarget")

        if isinstance(target_value, QuaProgram.AnalogProcessTarget.ScalarProcessTarget):
            target = ExpressionSerializingVisitor(self._visitor).serialize(target_value)
            self._out = f'{integration_type}.full("{name}", {target}, "{output}")'
        elif isinstance(target_value, QuaProgram.AnalogProcessTarget.VectorProcessTarget):
            target = ExpressionSerializingVisitor(self._visitor).serialize(target_value.array)

            time_name, time_value = which_one_of(target_value.timeDivision, "timeDivision")
            if isinstance(time_value, QuaProgram.AnalogTimeDivision.Sliced):
                self._out = f'{integration_type}.sliced("{name}", {target}, {time_value.samplesPerChunk}, "{output}")'
            elif isinstance(time_value, QuaProgram.AnalogTimeDivision.Accumulated):
                self._out = (
                    f'{integration_type}.accumulated("{name}", {target}, {time_value.samplesPerChunk}, "{output}")'
                )
            elif isinstance(time_value, QuaProgram.AnalogTimeDivision.MovingWindow):
                self._out = f'{integration_type}.moving_window("{name}", {target}, {time_value.samplesPerChunk}, {time_value.chunksPerWindow}, "{output}")'
            else:
                raise Exception(f"Unsupported analog process target {target_name}")
        else:
            raise Exception(f"Unsupported analog process target {target_name}")

    def _common_dual_measurement(
        self,
        node: Union[
            QuaProgram.AnalogMeasureProcess.DualDemodIntegration,
            QuaProgram.AnalogMeasureProcess.DualBareIntegration,
        ],
        demod_name: str,
    ) -> None:
        name1 = node.integration1.name
        name2 = node.integration2.name
        output1 = node.elementOutput1
        output2 = node.elementOutput2
        target_name, target_value = which_one_of(node.target, "processTarget")
        if output1 == "out1" and output2 == "out2":
            common_args = f'"{name1}", "{name2}"'
        elif output1 == "out2" and output2 == "out1":
            common_args = f'"{name2}", "{name1}"'
        else:
            common_args = f'"{name1}", "{output1}", "{name2}", "{output2}"'
        if isinstance(target_value, QuaProgram.AnalogProcessTarget.ScalarProcessTarget):
            target = ExpressionSerializingVisitor(self._visitor).serialize(target_value)
            self._out = f"{demod_name}.full({common_args}, {target})"
        elif isinstance(target_value, QuaProgram.AnalogProcessTarget.VectorProcessTarget):
            target = ExpressionSerializingVisitor(self._visitor).serialize(target_value.array)

            time_name, time_value = which_one_of(target_value.timeDivision, "timeDivision")
            if isinstance(time_value, QuaProgram.AnalogTimeDivision.Sliced):
                self._out = f"{demod_name}.sliced({common_args}, {time_value.samplesPerChunk}, {target})"
            elif isinstance(time_value, QuaProgram.AnalogTimeDivision.Accumulated):
                self._out = f"{demod_name}. accumulated({common_args}, {time_value.samplesPerChunk}, {target})"
            elif isinstance(time_value, QuaProgram.AnalogTimeDivision.MovingWindow):
                self._out = f"{demod_name}.moving_window({common_args}, {time_value.samplesPerChunk}, {time_value.chunksPerWindow}, {target})"
            else:
                raise Exception(f"Unsupported analog process target {time_name}")
        else:
            raise Exception(f"Unsupported analog process target {target_name}")

    def visit_analog_measurement_dual_demod_integration(
        self, node: QuaProgram.AnalogMeasureProcess.DualDemodIntegration
    ) -> None:
        self._common_dual_measurement(node, "dual_demod")

    def visit_analog_measurement_dual_bare_integration(
        self, node: QuaProgram.AnalogMeasureProcess.DualBareIntegration
    ) -> None:
        self._common_dual_measurement(node, "dual_integration")

    def _common_time_tagging(
        self,
        node: Union[
            QuaProgram.AnalogMeasureProcess.RawTimeTagging,
            QuaProgram.AnalogMeasureProcess.HighResTimeTagging,
            QuaProgram.DigitalMeasureProcess.RawTimeTagging,
        ],
        demod_name: str,
    ) -> None:
        target = ExpressionSerializingVisitor(self._visitor).serialize(node.target)
        target_len = ExpressionSerializingVisitor(self._visitor).serialize(node.targetLen)
        max_time = node.maxTime
        element_output = node.elementOutput
        self._out = f'time_tagging.{demod_name}({target}, {max_time}, {target_len}, "{element_output}")'

    def visit_analog_measurement_raw_time_tagging(self, node: QuaProgram.AnalogMeasureProcess.RawTimeTagging) -> None:
        self._common_time_tagging(node, "analog")

    def visit_analog_measurement_high_res_time_tagging(
        self, node: QuaProgram.AnalogMeasureProcess.HighResTimeTagging
    ) -> None:
        self._common_time_tagging(node, "high_res")

    def visit_digital_measurement_counting(self, node: QuaProgram.DigitalMeasureProcess.Counting) -> None:
        element_outputs = []
        for element_output in node.elementOutputs:
            element_outputs.append(f'"{element_output}"')
        element_outputs_str = ",".join(element_outputs)
        target = ExpressionSerializingVisitor(self._visitor).serialize(node.target)
        max_time = node.maxTime
        self._out = f"counting.digital({target}, {max_time}, ({element_outputs_str}))"

    def visit_digital_measurement_raw_time_tagging(self, node: QuaProgram.DigitalMeasureProcess.RawTimeTagging) -> None:
        self._common_time_tagging(node, "digital")

    def visit_binary_expression(self, node: QuaProgram.BinaryExpression) -> None:
        left = ExpressionSerializingVisitor(self._visitor).serialize(node.left)
        right = ExpressionSerializingVisitor(self._visitor).serialize(node.right)
        sop = node.op
        mapping = {
            QuaProgram.BinaryExpression.BinaryOperator.ADD: "+",
            QuaProgram.BinaryExpression.BinaryOperator.SUB: "-",
            QuaProgram.BinaryExpression.BinaryOperator.GT: ">",
            QuaProgram.BinaryExpression.BinaryOperator.LT: "<",
            QuaProgram.BinaryExpression.BinaryOperator.LET: "<=",
            QuaProgram.BinaryExpression.BinaryOperator.GET: ">=",
            QuaProgram.BinaryExpression.BinaryOperator.EQ: "==",
            QuaProgram.BinaryExpression.BinaryOperator.MULT: "*",
            QuaProgram.BinaryExpression.BinaryOperator.DIV: "/",
            QuaProgram.BinaryExpression.BinaryOperator.OR: "|",
            QuaProgram.BinaryExpression.BinaryOperator.AND: "&",
            QuaProgram.BinaryExpression.BinaryOperator.XOR: "^",
            QuaProgram.BinaryExpression.BinaryOperator.SHL: "<<",
            QuaProgram.BinaryExpression.BinaryOperator.SHR: ">>",
        }
        if sop in mapping:
            op = mapping[sop]
        else:
            raise Exception(f"Unsupported operator {sop}")
        self._out = f"({left}{op}{right})"

    def visit_global_var_reference(self, node: QuaProgram.GlobalVarRefExpression) -> None:
        bits = ", ".join([str(b) for b in node.bits])
        if node.operation == QuaProgram.GlobalVarOperation.xor:
            self._out = f"global_var_xor({bits})"
        elif node.operation == QuaProgram.GlobalVarOperation.read:
            self._out = f"global_var_read({bits})"
        elif node.operation == QuaProgram.GlobalVarOperation.read_shift:
            self._out = f"global_var_read({bits}, shift=True)"

    def serialize(self, node: Node) -> str:
        self.visit(node)
        return self._out
