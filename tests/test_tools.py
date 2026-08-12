import importlib

import pytest

import ai.react
import ai.tools
from ai.react import (
    _chart_arguments_from_markdown_table,
    _execute_textual_chart_call,
    _extract_textual_tool_call,
    _inventory_chart_arguments,
    _response_has_generated_chart,
    _try_direct_business_chart,
    _filtrar_ferramentas,
    _try_direct_business_report,
    loop_react,
)
from ai.tools import (
    REGISTRO_FERRAMENTAS,
    _normalize_chart_arguments,
    _validate_path,
    obter_schemas_openai,
)
from core.settings import SecuritySettings, Settings


class TestToolRegistry:
    def test_registry_not_empty(self):
        assert len(REGISTRO_FERRAMENTAS) > 0

    def test_required_tools_exist(self):
        names = {f.nome for f in REGISTRO_FERRAMENTAS}
        for required in ["processar_arquivo", "pesquisar_web", "executar_codigo"]:
            assert required in names, f"Required tool '{required}' not found"

    def test_agenda_tools_exist(self):
        names = {f.nome for f in REGISTRO_FERRAMENTAS}

        assert "listar_agenda" in names
        assert "criar_compromisso_agenda" in names
        assert "marcar_lembrete_agenda" in names

    def test_each_tool_has_schema(self):
        for f in REGISTRO_FERRAMENTAS:
            assert f.schema is not None
            assert "properties" in f.schema

    def test_obter_schemas_openai_format(self):
        schemas = obter_schemas_openai()
        assert len(schemas) == len(REGISTRO_FERRAMENTAS)
        for s in schemas:
            assert "function" in s
            assert "name" in s["function"]
            assert "parameters" in s["function"]


class TestChartToolCompatibility:
    def test_normalizes_record_list_emitted_by_local_model(self):
        arguments = {
            "data": (
                '[{"nome": "Alicate", "quantidade": 52, "categoria": "Geral"}, '
                '{"nome": "Chave", "quantidade": 3, "categoria": "Geral"}]'
            ),
            "tipo": "barras",
            "titulo": "Quantidade em estoque",
        }

        normalized = _normalize_chart_arguments(arguments)

        assert normalized["tipo"] == "bar"
        assert normalized["labels"] == '["Alicate", "Chave"]'
        assert normalized["valores"] == "[52, 3]"
        assert "data" not in normalized

    def test_recovers_and_executes_visible_chart_tool_json(self, monkeypatch):
        response = (
            '{"name": "gerar_grafico", "arguments": {'
            '"data": "[{\\"nome\\": \\"Alicate\\", \\"quantidade\\": 52}]", '
            '"tipo": "barras", "titulo": "Estoque"}}'
        )
        captured = {}

        def fake_execute(name, arguments):
            captured["name"] = name
            captured["arguments"] = arguments
            return (
                "Grafico 'bar' gerado com sucesso.\n"
                "Arquivo: C:\\cache\\estoque.png\n"
                "Exiba-o com: ![Grafico - Estoque](C:\\cache\\estoque.png)"
            )

        monkeypatch.setattr(ai.react, "executar_ferramenta", fake_execute)
        monkeypatch.setattr(
            ai.react,
            "_inventory_report_summary",
            lambda: "**Dados confirmados no inventory.json**",
        )
        monkeypatch.setattr(
            ai.react,
            "_chart_response_from_tool_result",
            lambda _result, _title: "![Grafico - Estoque](C:\\cache\\estoque.png)",
        )

        assert _extract_textual_tool_call(response)[0] == "gerar_grafico"
        result = _execute_textual_chart_call(response)

        assert captured["name"] == "gerar_grafico"
        assert captured["arguments"]["labels"] == '["Alicate"]'
        assert captured["arguments"]["valores"] == "[52]"
        assert "![Grafico - Estoque]" in result
        assert "gerar_grafico" not in result

    def test_remote_image_is_not_accepted_as_generated_chart(self):
        response = "![Grafico](https://example.com/estoque.png)"

        assert _response_has_generated_chart(response) is False

    def test_extracts_chart_data_from_markdown_table(self):
        response = """
| Produto | Quantidade | Categoria |
|---|---:|---|
| Alicate | 52 un. | Geral |
| Chave | 3 un. | Geral |
"""

        arguments = _chart_arguments_from_markdown_table(
            "Crie um grafico de barras da quantidade",
            response,
        )

        assert arguments["labels"] == ["Alicate", "Chave"]
        assert arguments["valores"] == [52.0, 3.0]
        assert arguments["tipo"] == "bar"

    def test_builds_inventory_efficiency_indicator(self):
        items = [
            type("Item", (), {"precisa_repor": False})(),
            type("Item", (), {"precisa_repor": False})(),
            type("Item", (), {"precisa_repor": True})(),
            type("Item", (), {"precisa_repor": True})(),
        ]

        arguments, summary = _inventory_chart_arguments(
            "Crie um indicador de eficiencia do estoque",
            items,
        )

        assert arguments["tipo"] == "kpi"
        assert arguments["valores"] == [50.0]
        assert arguments["meta"] == 90
        assert arguments["unidade"] == "%"
        assert "2 de 4" in summary

    def test_inventory_chart_is_generated_without_waiting_for_llm(self, monkeypatch):
        items = [
            type(
                "Item",
                (),
                {
                    "nome": "Alicate",
                    "categoria": "Ferramentas",
                    "quantidade": 52,
                    "estoque_min": 5,
                    "estoque_max": 70,
                    "precisa_repor": False,
                },
            )(),
            type(
                "Item",
                (),
                {
                    "nome": "Chave",
                    "categoria": "Ferramentas",
                    "quantidade": 3,
                    "estoque_min": 10,
                    "estoque_max": 40,
                    "precisa_repor": True,
                },
            )(),
        ]
        service = type("Inventory", (), {"get_all_items": lambda self: items})()
        captured = {}

        inventory_module = importlib.import_module("core.inventory")
        monkeypatch.setattr(inventory_module, "get_inventory_service", lambda: service)

        def fake_execute(name, arguments):
            captured["name"] = name
            captured["arguments"] = arguments
            return "Arquivo: C:\\cache\\chart.png"

        monkeypatch.setattr(ai.react, "executar_ferramenta", fake_execute)
        monkeypatch.setattr(
            ai.react,
            "_chart_response_from_tool_result",
            lambda _result, _title: "![Grafico](C:\\cache\\chart.png)",
        )

        result = _try_direct_business_chart(
            "Crie um grafico de barras mostrando todos os itens do estoque"
        )

        assert captured["name"] == "gerar_grafico"
        assert captured["arguments"]["tipo"] == "bar"
        assert captured["arguments"]["labels"] == '["Alicate", "Chave"]'
        assert "![Grafico]" in result


class TestBusinessDataToolAccess:
    def test_report_request_exposes_inventory_and_report_tools(self):
        names = {tool.nome for tool in _filtrar_ferramentas("Gere um relatorio do estoque em PDF")}

        assert "listar_estoque" in names
        assert "gerar_relatorio_local" in names

    def test_read_tools_cover_local_business_databases(self):
        names = {tool.nome for tool in _filtrar_ferramentas("Mostre meus dados locais")}

        assert {
            "listar_agenda",
            "listar_clientes",
            "listar_estoque",
            "listar_fornecedores",
            "listar_orcamentos",
            "listar_processos_prazos",
            "listar_produtos_servicos",
        } <= names

    def test_stock_report_is_generated_without_model_tool_choice(self, monkeypatch):
        captured = {}

        def fake_execute(name, arguments):
            captured["name"] = name
            captured["arguments"] = arguments
            return "Relatorio gerado localmente."

        monkeypatch.setattr(ai.react, "executar_ferramenta", fake_execute)

        result = _try_direct_business_report("Crie um relatorio do estoque em PDF")

        assert result.startswith("Relatorio gerado localmente.")
        assert "Dados confirmados no inventory.json" in result
        assert captured["name"] == "gerar_relatorio_local"
        assert captured["arguments"]["fonte"] == "Estoque"
        assert captured["arguments"]["formato"] == "pdf"

    def test_stock_context_does_not_disable_deterministic_report(self, monkeypatch):
        monkeypatch.setattr(
            ai.react,
            "_try_direct_business_report",
            lambda _question: "Relatorio confirmado pelo inventory.json",
        )
        monkeypatch.setattr(
            ai.react,
            "get_multi_model_manager",
            lambda: pytest.fail("O LLM nao deve ser usado para este relatorio"),
        )

        response, _steps = loop_react(
            {
                "pergunta": "gere um relatorio de meu estoque",
                "documento": "Dados do estoque do usuario (2 itens)",
                "nome_documento": "Dados do Estoque",
            }
        )

        assert response == "Relatorio confirmado pelo inventory.json"


class TestToolPathSecurity:
    def test_validate_relative_path_inside_base_dir(self, tmp_path, monkeypatch):
        allowed_file = tmp_path / "allowed.txt"
        allowed_file.write_text("ok", encoding="utf-8")
        settings = Settings(
            base_dir=tmp_path,
            security=SecuritySettings(allowed_file_roots=(str(tmp_path),)),
        )
        monkeypatch.setattr(ai.tools, "get_settings", lambda: settings)

        assert _validate_path("allowed.txt") == allowed_file.resolve()

    def test_validate_path_denies_outside_allowed_roots(self, tmp_path, monkeypatch):
        allowed = tmp_path / "allowed"
        outside = tmp_path / "outside"
        allowed.mkdir()
        outside.mkdir()
        outside_file = outside / "secret.txt"
        outside_file.write_text("secret", encoding="utf-8")
        settings = Settings(
            base_dir=allowed,
            security=SecuritySettings(allowed_file_roots=(str(allowed),)),
        )
        monkeypatch.setattr(ai.tools, "get_settings", lambda: settings)

        with pytest.raises(PermissionError):
            _validate_path(str(outside_file))
