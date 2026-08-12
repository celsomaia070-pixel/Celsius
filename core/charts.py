"""Deterministic local rendering for business charts and KPI indicators."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

SUPPORTED_CHART_TYPES = {
    "bar",
    "barh",
    "grouped_bar",
    "stacked_bar",
    "pie",
    "donut",
    "line",
    "area",
    "histogram",
    "scatter",
    "radar",
    "heatmap",
    "waterfall",
    "funnel",
    "boxplot",
    "combo",
    "gauge",
    "kpi",
}

DEFAULT_COLORS = (
    "#2563EB",
    "#DC2626",
    "#16A34A",
    "#D97706",
    "#7C3AED",
    "#0891B2",
    "#EA580C",
    "#DB2777",
    "#0D9488",
    "#65A30D",
)


class ChartError(ValueError):
    """Raised when a chart specification cannot be rendered safely."""


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise ChartError("valores booleanos nao sao aceitos")
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).strip().replace("%", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError as exc:
        raise ChartError(f"valor nao numerico: {value}") from exc


def _numeric_values(values: list) -> list[float] | list[list[float]]:
    if not values:
        raise ChartError("o grafico precisa de valores")
    if isinstance(values[0], list):
        return [[_number(value) for value in series] for series in values]
    return [_number(value) for value in values]


def _single_series(values: list[float] | list[list[float]]) -> list[float]:
    return values[0] if values and isinstance(values[0], list) else values


def _validate_series_lengths(labels: list[str], values: list[float] | list[list[float]]) -> None:
    series = values if values and isinstance(values[0], list) else [values]
    if any(len(item) != len(labels) for item in series):
        raise ChartError("a quantidade de labels deve corresponder aos valores")


def render_business_chart(
    *,
    chart_type: str,
    title: str,
    labels: list,
    values: list,
    output_dir: Path,
    legends: list | None = None,
    colors: list | None = None,
    xlabel: str = "",
    ylabel: str = "",
    target: float = 0,
    unit: str = "",
    subtitle: str = "",
) -> Path:
    """Render a chart locally and return its PNG path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Wedge

    chart_type = str(chart_type).strip().lower()
    if chart_type not in SUPPORTED_CHART_TYPES:
        valid = ", ".join(sorted(SUPPORTED_CHART_TYPES))
        raise ChartError(f"tipo '{chart_type}' nao suportado; use: {valid}")

    labels = [str(label) for label in labels]
    if not labels:
        raise ChartError("o grafico precisa de labels")
    numeric_values = _numeric_values(values)
    legends = [str(item) for item in (legends or [])]
    palette = list(colors or DEFAULT_COLORS)
    if not palette:
        palette = list(DEFAULT_COLORS)

    no_label_match_required = {
        "histogram",
        "scatter",
        "heatmap",
        "boxplot",
        "gauge",
        "kpi",
    }
    if chart_type not in no_label_match_required:
        _validate_series_lengths(labels, numeric_values)

    output_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = repr(
        (
            chart_type,
            title,
            labels,
            numeric_values,
            legends,
            palette,
            target,
            unit,
            subtitle,
        )
    )
    filename = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16] + ".png"
    filepath = output_dir / filename
    if filepath.exists() and filepath.stat().st_size > 0:
        return filepath

    plt.style.use(
        "seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default"
    )
    subplot_kw = {"polar": True} if chart_type == "radar" else {}
    fig, ax = plt.subplots(figsize=(10, 6), subplot_kw=subplot_kw)
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    def series_name(index: int) -> str:
        return legends[index] if index < len(legends) else f"Serie {index + 1}"

    def apply_style(*, horizontal: bool = False) -> None:
        ax.set_title(title, fontsize=16, fontweight="bold", color="#111827", pad=16)
        if subtitle:
            ax.text(
                0.5,
                1.01,
                subtitle,
                transform=ax.transAxes,
                ha="center",
                va="bottom",
                color="#6B7280",
                fontsize=10,
            )
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=11, color="#374151")
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=11, color="#374151")
        ax.tick_params(axis="both", labelsize=9, colors="#4B5563")
        axis = "x" if horizontal else "y"
        ax.grid(True, axis=axis, color="#E5E7EB", linewidth=0.8)
        ax.grid(False, axis="y" if horizontal else "x")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#D1D5DB")
        ax.spines["bottom"].set_color("#D1D5DB")

    try:
        if chart_type in {"bar", "grouped_bar"}:
            positions = np.arange(len(labels))
            if isinstance(numeric_values[0], list):
                width = 0.76 / len(numeric_values)
                for index, series in enumerate(numeric_values):
                    offset = (index - (len(numeric_values) - 1) / 2) * width
                    ax.bar(
                        positions + offset,
                        series,
                        width,
                        label=series_name(index),
                        color=palette[index % len(palette)],
                        zorder=3,
                    )
                ax.legend(frameon=False)
            else:
                ax.bar(
                    positions,
                    numeric_values,
                    width=0.64,
                    color=[palette[index % len(palette)] for index in range(len(labels))],
                    zorder=3,
                )
            ax.set_xticks(positions, labels, rotation=30 if len(labels) > 6 else 0)
            apply_style()

        elif chart_type == "barh":
            series = _single_series(numeric_values)
            positions = np.arange(len(labels))
            ax.barh(
                positions,
                series,
                color=[palette[index % len(palette)] for index in range(len(labels))],
                zorder=3,
            )
            ax.set_yticks(positions, labels)
            ax.invert_yaxis()
            apply_style(horizontal=True)

        elif chart_type == "stacked_bar":
            series_list = (
                numeric_values if isinstance(numeric_values[0], list) else [numeric_values]
            )
            positions = np.arange(len(labels))
            bottom = np.zeros(len(labels))
            for index, series in enumerate(series_list):
                ax.bar(
                    positions,
                    series,
                    bottom=bottom,
                    label=series_name(index),
                    color=palette[index % len(palette)],
                    zorder=3,
                )
                bottom += np.asarray(series)
            ax.set_xticks(positions, labels, rotation=30 if len(labels) > 6 else 0)
            ax.legend(frameon=False)
            apply_style()

        elif chart_type in {"pie", "donut"}:
            series = _single_series(numeric_values)
            wedge = {"edgecolor": "#FAFAFA", "linewidth": 2}
            if chart_type == "donut":
                wedge["width"] = 0.42
            _, _, autotexts = ax.pie(
                series,
                labels=labels,
                colors=[palette[index % len(palette)] for index in range(len(labels))],
                autopct="%1.1f%%",
                startangle=90,
                textprops={"fontsize": 10, "color": "#111827"},
                pctdistance=0.78,
                wedgeprops=wedge,
            )
            for text in autotexts:
                text.set_color("white")
                text.set_fontweight("bold")
            ax.set_title(
                title,
                fontsize=16,
                fontweight="bold",
                color="#111827",
                pad=16,
            )
            ax.axis("equal")

        elif chart_type in {"line", "area"}:
            series_list = (
                numeric_values if isinstance(numeric_values[0], list) else [numeric_values]
            )
            for index, series in enumerate(series_list):
                color = palette[index % len(palette)]
                label = series_name(index) if len(series_list) > 1 else None
                ax.plot(
                    labels,
                    series,
                    marker="o",
                    linewidth=2.4,
                    color=color,
                    label=label,
                    zorder=3,
                )
                if chart_type == "area":
                    ax.fill_between(labels, series, alpha=0.18, color=color)
            if len(series_list) > 1:
                ax.legend(frameon=False)
            ax.tick_params(axis="x", rotation=30 if len(labels) > 8 else 0)
            apply_style()

        elif chart_type == "histogram":
            series = _single_series(numeric_values)
            ax.hist(
                series,
                bins=max(5, min(20, round(math.sqrt(len(series))))),
                color=palette[0],
                edgecolor="#FAFAFA",
                linewidth=1.5,
                zorder=3,
            )
            apply_style()

        elif chart_type == "scatter":
            if isinstance(numeric_values[0], list) and all(
                len(point) == 2 for point in numeric_values
            ):
                x_values = [point[0] for point in numeric_values]
                y_values = [point[1] for point in numeric_values]
            elif isinstance(numeric_values[0], list) and len(numeric_values) >= 2:
                x_values, y_values = numeric_values[:2]
            else:
                x_values = list(range(1, len(numeric_values) + 1))
                y_values = numeric_values
            ax.scatter(
                x_values,
                y_values,
                color=palette[0],
                s=80,
                alpha=0.75,
                edgecolors="white",
                linewidths=1.2,
                zorder=3,
            )
            apply_style()

        elif chart_type == "radar":
            series_list = (
                numeric_values if isinstance(numeric_values[0], list) else [numeric_values]
            )
            angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
            closed_angles = angles + angles[:1]
            for index, series in enumerate(series_list):
                closed_values = list(series) + list(series[:1])
                color = palette[index % len(palette)]
                ax.plot(
                    closed_angles,
                    closed_values,
                    color=color,
                    linewidth=2,
                    label=series_name(index),
                )
                ax.fill(closed_angles, closed_values, color=color, alpha=0.12)
            ax.set_xticks(angles, labels)
            ax.set_title(
                title,
                fontsize=16,
                fontweight="bold",
                color="#111827",
                pad=16,
            )
            if len(series_list) > 1:
                ax.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.2, 1.1))
            ax.grid(color="#D1D5DB", alpha=0.7)

        elif chart_type == "heatmap":
            matrix = (
                np.asarray(numeric_values)
                if isinstance(numeric_values[0], list)
                else np.asarray([numeric_values])
            )
            image = ax.imshow(matrix, cmap="Blues", aspect="auto")
            row_labels = labels[: matrix.shape[0]]
            row_labels.extend(
                f"Linha {index + 1}" for index in range(len(row_labels), matrix.shape[0])
            )
            column_labels = legends[: matrix.shape[1]]
            column_labels.extend(
                f"Coluna {index + 1}" for index in range(len(column_labels), matrix.shape[1])
            )
            ax.set_yticks(range(matrix.shape[0]), row_labels)
            ax.set_xticks(range(matrix.shape[1]), column_labels)
            for row in range(matrix.shape[0]):
                for column in range(matrix.shape[1]):
                    ax.text(
                        column,
                        row,
                        f"{matrix[row, column]:g}",
                        ha="center",
                        va="center",
                        color="#111827",
                        fontsize=9,
                    )
            fig.colorbar(image, ax=ax, fraction=0.035, pad=0.03)
            ax.set_title(
                title,
                fontsize=16,
                fontweight="bold",
                color="#111827",
                pad=16,
            )

        elif chart_type == "waterfall":
            series = _single_series(numeric_values)
            starts = np.cumsum([0, *series[:-1]])
            bar_colors = [palette[2] if value >= 0 else palette[1] for value in series]
            ax.bar(labels, series, bottom=starts, color=bar_colors, zorder=3)
            ax.axhline(0, color="#6B7280", linewidth=1)
            ax.tick_params(axis="x", rotation=30 if len(labels) > 6 else 0)
            apply_style()

        elif chart_type == "funnel":
            series = _single_series(numeric_values)
            order = sorted(range(len(series)), key=lambda index: series[index], reverse=True)
            ordered_values = [series[index] for index in order]
            ordered_labels = [labels[index] for index in order]
            positions = np.arange(len(ordered_labels))
            ax.barh(
                positions,
                ordered_values,
                color=[palette[index % len(palette)] for index in range(len(ordered_labels))],
            )
            ax.set_yticks(positions, ordered_labels)
            ax.invert_yaxis()
            apply_style(horizontal=True)

        elif chart_type == "boxplot":
            series_list = (
                numeric_values if isinstance(numeric_values[0], list) else [numeric_values]
            )
            box = ax.boxplot(series_list, patch_artist=True, tick_labels=labels[: len(series_list)])
            for index, patch in enumerate(box["boxes"]):
                patch.set_facecolor(palette[index % len(palette)])
                patch.set_alpha(0.7)
            apply_style()

        elif chart_type == "combo":
            if not isinstance(numeric_values[0], list) or len(numeric_values) < 2:
                raise ChartError("grafico combinado requer duas series")
            positions = np.arange(len(labels))
            ax.bar(
                positions,
                numeric_values[0],
                color=palette[0],
                alpha=0.75,
                label=series_name(0),
            )
            second_axis = ax.twinx()
            second_axis.plot(
                positions,
                numeric_values[1],
                color=palette[1],
                marker="o",
                linewidth=2.4,
                label=series_name(1),
            )
            ax.set_xticks(positions, labels, rotation=30 if len(labels) > 6 else 0)
            ax.legend(frameon=False, loc="upper left")
            second_axis.legend(frameon=False, loc="upper right")
            apply_style()

        elif chart_type == "gauge":
            value = _single_series(numeric_values)[0]
            target = float(target or 100)
            ratio = max(0.0, min(1.0, value / target if target else 0.0))
            color = palette[2] if ratio >= 0.9 else palette[3] if ratio >= 0.7 else palette[1]
            ax.add_patch(Wedge((0, 0), 1, 0, 180, width=0.28, color="#E5E7EB"))
            ax.add_patch(Wedge((0, 0), 1, 180 - ratio * 180, 180, width=0.28, color=color))
            ax.text(
                0,
                0.2,
                f"{value:g}{unit}",
                ha="center",
                va="center",
                fontsize=30,
                fontweight="700",
                color="#111827",
            )
            ax.text(
                0,
                -0.05,
                f"Meta: {target:g}{unit}",
                ha="center",
                va="center",
                fontsize=11,
                color="#6B7280",
            )
            ax.set_xlim(-1.15, 1.15)
            ax.set_ylim(-0.2, 1.15)
            ax.axis("off")
            ax.set_title(
                title,
                fontsize=16,
                fontweight="bold",
                color="#111827",
                pad=16,
            )

        elif chart_type == "kpi":
            value = _single_series(numeric_values)[0]
            target = float(target or 0)
            attainment = value / target * 100 if target else None
            ax.axis("off")
            ax.text(
                0.5,
                0.68,
                f"{value:g}{unit}",
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=42,
                fontweight="700",
                color=palette[0],
            )
            ax.text(
                0.5,
                0.48,
                title,
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=17,
                fontweight="bold",
                color="#111827",
            )
            detail = subtitle
            if attainment is not None:
                detail = f"{attainment:.1f}% da meta de {target:g}{unit}"
            if detail:
                ax.text(
                    0.5,
                    0.34,
                    detail,
                    transform=ax.transAxes,
                    ha="center",
                    va="center",
                    fontsize=12,
                    color="#6B7280",
                )

        plt.tight_layout()
        fig.savefig(
            str(filepath),
            dpi=180,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
            transparent=False,
        )
    except Exception:
        plt.close(fig)
        raise
    plt.close(fig)

    if not filepath.exists() or filepath.stat().st_size <= 0:
        raise ChartError("o arquivo PNG nao foi criado")
    return filepath
