"""Tests for deterministic local business chart rendering."""

from pathlib import Path

import pytest

from core.charts import ChartError, render_business_chart


@pytest.mark.parametrize(
    ("chart_type", "labels", "values", "legends", "target", "unit"),
    [
        ("bar", ["A", "B", "C"], [10, 20, 15], [], 0, ""),
        ("donut", ["A", "B", "C"], [10, 20, 15], [], 0, ""),
        (
            "stacked_bar",
            ["Jan", "Fev", "Mar"],
            [[10, 20, 15], [5, 8, 9]],
            ["Vendas", "Servicos"],
            0,
            "",
        ),
        ("radar", ["Prazo", "Custo", "Qualidade"], [80, 70, 90], [], 0, "%"),
        (
            "heatmap",
            ["Produto A", "Produto B"],
            [[12, 5, 20], [7, 10, 30]],
            ["Atual", "Minimo", "Maximo"],
            0,
            "",
        ),
        ("gauge", ["Eficiencia"], [82.5], [], 90, "%"),
        ("kpi", ["Conversao"], [24.3], [], 30, "%"),
        ("scatter", ["A", "B", "C"], [[1, 5], [2, 8], [3, 7]], [], 0, ""),
    ],
)
def test_renders_supported_business_charts(
    tmp_path: Path,
    chart_type,
    labels,
    values,
    legends,
    target,
    unit,
):
    output = render_business_chart(
        chart_type=chart_type,
        title="Indicador empresarial",
        labels=labels,
        values=values,
        legends=legends,
        target=target,
        unit=unit,
        output_dir=tmp_path,
    )

    assert output.is_file()
    assert output.read_bytes().startswith(b"\x89PNG")


def test_rejects_unknown_chart_type(tmp_path):
    with pytest.raises(ChartError, match="nao suportado"):
        render_business_chart(
            chart_type="inventado",
            title="Teste",
            labels=["A"],
            values=[1],
            output_dir=tmp_path,
        )


def test_rejects_mismatched_labels_and_values(tmp_path):
    with pytest.raises(ChartError, match="corresponder"):
        render_business_chart(
            chart_type="bar",
            title="Teste",
            labels=["A", "B"],
            values=[1],
            output_dir=tmp_path,
        )
