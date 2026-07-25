from ai.tools import REGISTRO_FERRAMENTAS, obter_schemas_openai


class TestToolRegistry:
    def test_registry_not_empty(self):
        assert len(REGISTRO_FERRAMENTAS) > 0

    def test_required_tools_exist(self):
        names = {f.nome for f in REGISTRO_FERRAMENTAS}
        for required in ["processar_arquivo", "pesquisar_web", "executar_codigo"]:
            assert required in names, f"Required tool '{required}' not found"

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
