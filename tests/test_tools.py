import pytest

import ai.tools
from ai.tools import REGISTRO_FERRAMENTAS, _validate_path, obter_schemas_openai
from core.settings import SecuritySettings, Settings


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
