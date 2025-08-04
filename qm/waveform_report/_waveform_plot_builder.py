import base64
import logging
import os.path
import datetime
from dataclasses import dataclass
from typing import Set, Dict, List, Tuple, Union, Literal, Sequence, cast

import numpy as np
import plotly.colors  # type: ignore[import-untyped]
import plotly.graph_objects as go  # type: ignore[import-untyped]

from qm.simulate import SimulatorControllerSamples
from qm.waveform_report._utils import pretty_string_freq
from qm.waveform_report._waveform_report import (
    AdcAcquisition,
    PlayedWaveform,
    WaveformReport,
    PlayedAnalogWaveform,
    _SingleControllerMapping,
)


@dataclass
class _MaxParallelTracesPerRow:
    analog: Dict[str, int]
    digital: Dict[str, int]


class _WaveformPlotBuilder:
    def __init__(self, wf_report: WaveformReport, job_id: Union[int, str] = -1):
        self._report = wf_report
        if wf_report.num_controllers_in_use > 1:
            raise RuntimeError(
                f"Plot Builder does not support plotting more than 1 controllers, yet. {os.linesep}"
                "Please provide a report containing a single controller."
            )
        self._job_id = job_id
        self._figure = go.Figure()
        self._already_registered_qe: Set[str] = set()
        self._colormap = self._get_qe_colorscale(wf_report.elements_in_report)
        report_by_output_ports = cast(_SingleControllerMapping, wf_report.get_report_by_output_ports())
        self._max_parallel_traces_per_row = self._calculate_max_parallel_traces_per_row(report_by_output_ports)
        self._num_rows = self._get_num_rows(report_by_output_ports)

        self._report_by_output_ports = report_by_output_ports
        self._setup_figure(self._num_rows)
        self._add_data()
        self._update_extra_features()

    @property
    def _samples_factor(self) -> int:
        return 1

    @staticmethod
    def _get_qe_colorscale(qe_in_use: Sequence[str]) -> Dict[str, str]:
        n_colors = len(qe_in_use)
        samples = plotly.colors.qualitative.Pastel + plotly.colors.qualitative.Safe
        if n_colors > len(samples):
            samples += plotly.colors.sample_colorscale(
                "turbo",
                [n / (n_colors - len(samples)) for n in range(n_colors - len(samples))],
            )
        return dict(zip(qe_in_use, samples))

    @staticmethod
    def _calculate_max_parallel_traces_per_row(
        report_by_output_port: _SingleControllerMapping,
    ) -> _MaxParallelTracesPerRow:
        def calc_row(_waveform_list: Sequence[PlayedWaveform]) -> int:
            max_in_row = 0
            functional_ts = sorted(
                [(r.timestamp, 1) for r in _waveform_list] + [(r.ends_at, -1) for r in _waveform_list],
                key=lambda t: t[0],
            )
            for _, f in functional_ts:
                max_in_row = max(max_in_row, max_in_row + f)
            return max_in_row

        analog_traces_per_row = {}
        digital_traces_per_row = {}
        for fem_idx, report in report_by_output_port.items():
            for output_port, waveform_list in report.analog_out.items():
                analog_traces_per_row[f"{fem_idx}-{output_port}"] = calc_row(waveform_list)
            for output_port, digital_waveform_list in report.digital_out.items():
                digital_traces_per_row[f"{fem_idx}-{output_port}"] = calc_row(digital_waveform_list)

        return _MaxParallelTracesPerRow(analog=analog_traces_per_row, digital=digital_traces_per_row)

    def _get_num_rows(self, report_by_output_ports: _SingleControllerMapping) -> int:
        num_rows = report_by_output_ports.num_analog_out_ports + report_by_output_ports.num_digital_out_ports
        num_rows *= self._samples_factor
        num_rows += report_by_output_ports.num_analog_in_ports
        return num_rows

    @property
    def _num_output_rows(self) -> int:
        return self._num_rows - self._report_by_output_ports.num_analog_in_ports

    @property
    def _num_analog_rows(self) -> int:
        return self._report_by_output_ports.num_analog_out_ports * self._samples_factor

    @property
    def _num_digital_rows(self) -> int:
        return self._report_by_output_ports.num_digital_out_ports * self._samples_factor

    def _is_row_analog(self, r: int) -> bool:
        return 1 <= r <= self._num_analog_rows

    def _is_row_digital(self, r: int) -> bool:
        return self._num_analog_rows < r <= self._num_output_rows

    def _is_row_analog_input(self, r: int) -> bool:
        return self._num_output_rows < r <= self._num_rows

    @property
    def _xrange(self) -> int:
        return max(self._report.waveforms, key=lambda x: x.ends_at).ends_at + 100

    @staticmethod
    def _is_intersect(r1: Tuple[int, int], r2: Tuple[int, int]) -> bool:
        return (r1[0] <= r2[0] <= r1[1]) or (r1[0] <= r2[1] <= r1[1]) or (r2[0] < r1[0] and r2[1] > r1[1])

    @staticmethod
    def _get_hover_text(played_waveform: PlayedWaveform) -> str:
        waveform_desc = played_waveform.to_string()
        if isinstance(played_waveform, PlayedAnalogWaveform):
            if played_waveform.chirp_info is not None:
                waveform_desc = played_waveform.to_custom_string(False)
                s = (
                    f"rate={played_waveform.chirp_info['rate']},units={played_waveform.chirp_info['units']},"
                    f" times={played_waveform.chirp_info['times']}\n"
                    + f"start_freq={pretty_string_freq(played_waveform.chirp_info['startFrequency'])}, "
                    + f"end_freq={pretty_string_freq(played_waveform.chirp_info['endFrequency'])}"
                )

                waveform_desc = f"<b>Chirp Pulse</b>\n({s})\n" + waveform_desc
        return "%{x}ns<br>" + waveform_desc.replace("\n", "</br>") + "<extra></extra>"

    def _get_output_port_waveform_plot_data(
        self, port_played_waveforms: Sequence[PlayedWaveform], x_axis_name: str, max_in_row: int
    ) -> List[go.Scatter]:
        graph_data: List[go.Scatter] = []
        levels: List[Tuple[int, int]] = []
        diff_between_traces, start_y = (0.2, 1.2) if max_in_row <= 7 else (1.4 / max_in_row, 1.45)
        y_level = [start_y] * 3
        for wf in port_played_waveforms:
            x_axis_points = (wf.timestamp, wf.ends_at)
            num_intersections = len([l for l in levels if self._is_intersect(l, x_axis_points)])
            levels.append(x_axis_points)
            prev_y = start_y if num_intersections == 0 else y_level[0]
            y_level = [prev_y - diff_between_traces] * 3
            graph_data.append(
                go.Scatter(
                    x=[x_axis_points[0], sum(x_axis_points) // 2, x_axis_points[1]],
                    y=y_level,
                    mode="lines+markers+text",
                    text=[
                        "",
                        f"{wf.pulse_name.removeprefix('OriginPulseName=')}"
                        + (f"({wf.get_iq_association})" if wf.is_iq else ""),
                        "",
                    ],
                    hovertemplate=self._get_hover_text(wf),
                    textfont=dict(size=10),
                    xaxis=x_axis_name,
                    name=wf.element,
                    legendgroup=wf.element,
                    showlegend=not (wf.element in self._already_registered_qe),
                    marker=dict(
                        line=dict(width=2, color=self._colormap[wf.element]),
                        symbol=["line-ns", "line-ew", "line-ns"],
                    ),
                    line=dict(color=self._colormap[wf.element], width=5),
                )
            )
            self._already_registered_qe.add(wf.element)

        return graph_data

    def _add_plot_data_for_analog_output_port(
        self, figure_row_number: int, output_port: str, port_waveforms: Sequence[PlayedWaveform]
    ) -> None:
        self._add_plot_data_for_port(
            figure_row_number, self._max_parallel_traces_per_row.analog[output_port], port_waveforms
        )

    def _add_plot_data_for_port(
        self, figure_row_number: int, _max_parallel_traces_per_row: int, port_waveforms: Sequence[PlayedWaveform]
    ) -> None:
        if len(port_waveforms) == 0:
            return

        x_axis_name = self._get_x_axis_name(figure_row_number)
        port_wf_plot = self._get_output_port_waveform_plot_data(
            port_waveforms,
            x_axis_name,
            max_in_row=_max_parallel_traces_per_row,
        )
        row_number = figure_row_number * self._samples_factor
        self._figure.add_traces(port_wf_plot, rows=row_number, cols=1)

    @staticmethod
    def _get_x_axis_name(figure_row_number: int) -> str:
        return f"x{figure_row_number}"

    def _add_plot_data_for_digital_output_port(
        self, figure_row_number: int, output_port: str, port_waveforms: Sequence[PlayedWaveform]
    ) -> None:
        self._add_plot_data_for_port(
            figure_row_number, self._max_parallel_traces_per_row.digital[output_port], port_waveforms
        )

    def _add_plot_data_for_adc_port(
        self,
        figure_row_number: int,
        adc_port_acquisitions: List[AdcAcquisition],
    ) -> None:
        graph_data: List[go.Scatter] = []
        levels: List[Tuple[int, int]] = []
        y_level = [1.2] * 3
        for adc in adc_port_acquisitions:
            x_axis_points = (adc.start_time, adc.end_time)
            num_intersections = len([l for l in levels if self._is_intersect(l, x_axis_points)])
            levels.append(x_axis_points)
            prev_y = 1.2 if num_intersections == 0 else y_level[0]
            y_level = [prev_y - 0.2] * 3
            graph_data.append(
                go.Scatter(
                    x=[x_axis_points[0], sum(x_axis_points) // 2, x_axis_points[1]],
                    y=y_level,
                    mode="lines+markers+text",
                    text=["", f"{adc.process}", ""],
                    textfont=dict(size=10),
                    hovertemplate="%{x}ns<br>" + adc.to_string().replace("\n", "</br>") + "<extra></extra>",
                    name=adc.quantum_element,
                    legendgroup=adc.quantum_element,
                    showlegend=not (adc.quantum_element in self._already_registered_qe),
                    marker=dict(
                        line=dict(width=2, color=self._colormap[adc.quantum_element]),
                        symbol=["line-ns", "line-ew", "line-ns"],
                    ),
                    line=dict(color=self._colormap[adc.quantum_element], width=5),
                )
            )
            self._already_registered_qe.add(adc.quantum_element)

        self._figure.add_traces(graph_data, rows=figure_row_number, cols=1)

    def _add_data(self) -> None:
        for figure_row_number, (output_port, port_waveforms_list) in enumerate(
            self._report_by_output_ports.flat_analog_out.items()
        ):
            self._add_plot_data_for_analog_output_port(figure_row_number + 1, output_port, port_waveforms_list)

        for (figure_row_number, (output_port, digital_port_waveforms_list)) in enumerate(
            self._report_by_output_ports.flat_digital_out.items()
        ):
            self._add_plot_data_for_digital_output_port(
                figure_row_number + self._report_by_output_ports.num_analog_out_ports + 1,
                output_port,
                digital_port_waveforms_list,
            )

        for figure_row_number, adc_acquisition_list in enumerate(self._report_by_output_ports.flat_analog_in.values()):
            self._add_plot_data_for_adc_port(figure_row_number + self._num_output_rows + 1, adc_acquisition_list)

    def _update_extra_features(self) -> None:
        all_x_axis_names = sorted(
            [a for a in self._figure.layout.__dir__() if a.startswith("xaxis")],
            key=lambda s: int(s.removeprefix("xaxis")) if s.removeprefix("xaxis").isnumeric() else 0,
        )
        all_xaxis_names_short = {
            k: "x" + k.removeprefix("xaxis") if k.removeprefix("xaxis").isnumeric() else "" for k in all_x_axis_names
        }
        bottommost_x_axis = all_x_axis_names[-1]
        self._figure.update_layout(
            updatemenus=[
                dict(
                    type="buttons",
                    direction="left",
                    active=0,
                    buttons=list(
                        [
                            dict(
                                args=[
                                    {k + ".matches": all_xaxis_names_short[bottommost_x_axis] for k in all_x_axis_names}
                                ],
                                label="Shared",
                                method="relayout",
                            ),
                            dict(
                                args=[{k + ".matches": v for k, v in all_xaxis_names_short.items()}],
                                label="Distinct",
                                method="relayout",
                            ),
                        ]
                    ),
                    showactive=True,
                    x=1,
                    xanchor="right",
                    y=1,
                    yanchor="bottom",
                    font=dict(size=10),
                ),
            ]
        )
        self._figure.add_annotation(
            dict(
                text="X-Axis scrolling method:",
                showarrow=False,
                x=1,
                y=1,
                yref="paper",
                yshift=40,
                yanchor="bottom",
                xref="paper",
                align="left",
            )
        )
        self._figure.update_layout(
            modebar_remove=[
                "autoscale",
                "autoscale2d",
                "lasso",
            ]
        )

        source_path = os.path.join(os.path.dirname(__file__), "..", "sources", "logo_qm_square.png")

        im = base64.b64encode(open(source_path, "rb").read())
        self._figure.add_layout_image(
            source="data:image/png;base64,{}".format(im.decode()),
            xref="paper",
            yref="paper",
            x=0,
            y=1,
            sizex=0.1,
            sizey=0.1,
            xanchor="center",
            yanchor="bottom",
        )

    @property
    def _subplot_titles(self) -> Sequence[Union[str, Sequence[str]]]:
        titles = (
            [_calc_label(a, "Analog", "Out") for a in self._report_by_output_ports.flat_analog_out]
            + [_calc_label(d, "Digital", "Out") for d in self._report_by_output_ports.flat_digital_out]
            + [_calc_label(ai, "Analog", "In") for ai in self._report_by_output_ports.flat_analog_in]
        )
        return titles

    def _get_subplot_specs(self, num_rows: int) -> List[List[Dict[str, float]]]:
        return [[{"t": 1 / (num_rows * 4)}]] * num_rows

    def _setup_figure(self, num_rows: int, minimum_number_of_rows: int = 4) -> None:
        num_rows = max(num_rows, minimum_number_of_rows)
        self._figure.set_subplots(
            rows=num_rows,
            cols=1,
            subplot_titles=self._subplot_titles,
            vertical_spacing=0.1 / num_rows,
            specs=self._get_subplot_specs(num_rows),
        )

        self._figure.update_layout(
            hovermode="closest",
            hoverdistance=5,
            height=160 * num_rows,
            title=dict(
                text=(
                    f"Waveform Report (connection: {self._report.controllers_in_use[0]})"
                    + (" for job: {}".format(self._job_id) if self._job_id != -1 else "")
                ),
                x=0.5,
                xanchor="center",
                yanchor="auto",
                xref="paper",
            ),
            legend=dict(title="Elements", y=0.98, yanchor="top"),
        )
        self._figure.add_annotation(
            dict(
                text=f"Created at {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                showarrow=False,
                x=0.5,
                y=1,
                yref="paper",
                yshift=20,
                yanchor="bottom",
                xref="paper",
                xanchor="center",
            )
        )

        for idx in range(1, num_rows + 1):
            self._figure.update_xaxes(range=[0, self._xrange], row=idx, col=1)

        self._update_axes_for_samples()

        inc = self._samples_factor
        input_rows_first_idx = self._num_output_rows + 1
        output_rows_indices = list(range(inc, input_rows_first_idx, inc))
        input_rows_indices = list(
            range(input_rows_first_idx, input_rows_first_idx + self._report_by_output_ports.num_analog_in_ports)
        )
        for idx in output_rows_indices + input_rows_indices:
            self._figure.update_yaxes(
                range=[-0.5, 1.5],
                showticklabels=False,
                tickvals=[-0.5],
                ticklen=50,
                tickcolor="#000000",
                showgrid=False,
                zeroline=False,
                row=idx,
                col=1,
            )
            self._figure.update_xaxes(title=dict(text="Time(ns)", standoff=5, font=dict(size=9)), row=idx, col=1)

    def _update_axes_for_samples(self) -> None:
        return

    def plot(self) -> None:
        self._figure.show(renderer="browser")

    def save(self, basedir: str = "", filename: str = "") -> None:
        os.makedirs(basedir, exist_ok=True)
        if filename == "":
            filename = f"waveform_report_{self._job_id}"
        if not os.path.splitext(filename)[1] == "html":
            filename += ".html"

        path = os.path.join(basedir, filename)
        with open(path, "w", encoding="UTF-8") as f:
            self._figure.write_html(f)


class _WaveformPlotBuilderWithSamples(_WaveformPlotBuilder):
    def __init__(self, wf_report: WaveformReport, samples: SimulatorControllerSamples, job_id: Union[int, str] = -1):
        self._samples = samples
        super().__init__(wf_report, job_id)

    @property
    def _samples_factor(self) -> int:
        return 2

    @property
    def _xrange(self) -> int:
        first_key = next(iter(self._samples.analog.keys()))
        return len(self._samples.analog[first_key])

    def _add_plot_data_for_analog_output_port(
        self, figure_row_number: int, output_port: str, port_waveforms: Sequence[PlayedWaveform]
    ) -> None:
        if len(port_waveforms) == 0:
            return

        self._add_plot_data_for_port(
            figure_row_number, self._max_parallel_traces_per_row.analog[output_port], port_waveforms
        )

        port_samples = self._samples.analog[output_port]
        sampling_rate = self._samples.analog_sampling_rate[output_port] / 1e9
        t = list(x / sampling_rate for x in range(len(port_samples)))
        self._add_trace_to_figure(figure_row_number, t, np.real(port_samples).tolist())
        if isinstance(port_samples[0], complex):
            self._add_trace_to_figure(figure_row_number, t, np.imag(port_samples).tolist())

    def _add_plot_data_for_digital_output_port(
        self, figure_row_number: int, output_port: str, port_waveforms: Sequence[PlayedWaveform]
    ) -> None:
        if len(port_waveforms) == 0:
            return

        self._add_plot_data_for_port(
            figure_row_number, self._max_parallel_traces_per_row.digital[output_port], port_waveforms
        )

        port_samples = self._fetch_digital_samples(output_port)
        t = list(range(len(port_samples)))  # here we assume 1ns sampling rate
        self._add_trace_to_figure(figure_row_number, t, port_samples)

    def _fetch_digital_samples(self, output_port: Union[int, str]) -> Sequence[int]:
        port_samples = self._samples.digital.get(str(output_port))
        if port_samples is None:
            logging.log(logging.WARNING, f"Could not find digital samples for output port {output_port}")
            return [0] * self._xrange
        return [int(_x) for _x in port_samples]

    def _add_trace_to_figure(
        self, figure_row_number: int, t: Sequence[float], port_samples: Union[Sequence[int], Sequence[float]]
    ) -> None:
        self._figure.add_trace(
            go.Scatter(
                x=t,
                y=port_samples,
                showlegend=False,
                xaxis=self._get_x_axis_name(figure_row_number),
                hovertemplate="%{x}ns, %{y}v<extra></extra>",
            ),
            row=figure_row_number * 2 - 1,
            col=1,
        )

    @property
    def _subplot_titles(self) -> Sequence[Union[str, Sequence[str]]]:
        _titles = [_calc_label(a, "Analog", "Out") for a in self._report_by_output_ports.flat_analog_out] + [
            _calc_label(d, "Digital", "Out") for d in self._report_by_output_ports.flat_digital_out
        ]
        zipped: Sequence[Tuple[str, Sequence[str]]] = list(zip(_titles, [[]] * len(_titles)))
        titles: Sequence[Union[str, Sequence[str]]] = [item for z in zipped for item in z] + [
            _calc_label(a, "Analog", "In") for a in self._report_by_output_ports.flat_analog_in
        ]
        return titles

    def _get_subplot_specs(self, num_rows: int) -> List[List[Dict[str, float]]]:
        specs = ([[{"t": 1.2 / (num_rows * 5)}]] + [[{"b": 1.2 / (num_rows * 5)}]]) * (self._num_output_rows // 2) + [
            [{"t": 1 / (num_rows * 4)}]
        ] * self._report_by_output_ports.num_analog_in_ports
        if len(specs) < num_rows:
            specs += [[{}]] * (num_rows - len(specs))
        return specs

    def _update_axes_for_samples(self) -> None:
        for r in range(1, self._num_output_rows, 2):
            sample_y_range = [-0.1, 1.1] if self._is_row_digital(r) else [-0.6, 0.6]
            self._figure.update_yaxes(range=sample_y_range, row=r, col=1)
            self._figure.update_xaxes(showticklabels=False, row=r, col=1)
            self._figure.update_yaxes(title=dict(text="Voltage(v)", standoff=5, font=dict(size=9)), row=r, col=1)


def _calc_label(port: str, port_type: Literal["Analog", "Digital"], direction: Literal["Out", "In"]) -> str:
    address = port.split("-")
    if len(address) == 2:
        return f"FEM{address[0]} - {port_type} {direction} {address[1]}"
    if len(address) == 3:
        return f"FEM{address[0]} - {port_type} {direction} {address[1]} - Upconverter {address[2]}"
    return port
