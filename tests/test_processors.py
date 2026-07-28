import tempfile
from pathlib import Path

import pytest

from processors import PROCESSADORES, processar_arquivo


class TestFileProcessors:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_txt_file(self, temp_dir):
        test_file = temp_dir / "test.txt"
        test_file.write_text("Hello world\nThis is a test")

        result = processar_arquivo(str(test_file), base_dir=temp_dir)
        assert "Hello world" in result
        assert "This is a test" in result

    def test_python_file(self, temp_dir):
        test_file = temp_dir / "test.py"
        test_file.write_text("print('hello')\n# comment")

        result = processar_arquivo(str(test_file), base_dir=temp_dir)
        assert "print('hello')" in result

    def test_json_file(self, temp_dir):
        test_file = temp_dir / "test.json"
        test_file.write_text('{"key": "value", "num": 42}')

        result = processar_arquivo(str(test_file), base_dir=temp_dir)
        assert "key" in result
        assert "value" in result

    def test_unsupported_format(self, temp_dir):
        test_file = temp_dir / "test.xyz"
        test_file.write_text("content")

        result = processar_arquivo(str(test_file), base_dir=temp_dir)
        assert "nao suportado" in result.lower()

    def test_path_traversal_blocked(self, temp_dir):
        test_file = temp_dir / "test.txt"
        test_file.write_text("secret")

        # Try to access via path traversal
        result = processar_arquivo(str(test_file) + "/../../etc/passwd", base_dir=temp_dir)
        assert (
            "Path traversal" in result
            or "nao suportado" in result.lower()
            or "erro" in result.lower()
        )

    def test_processor_registry(self):
        assert ".pdf" in PROCESSADORES
        assert ".docx" in PROCESSADORES
        assert ".png" in PROCESSADORES
        assert ".mp3" in PROCESSADORES
        assert ".txt" in PROCESSADORES  # now handled by ProcessadorTexto
        assert ".py" in PROCESSADORES
        assert ".json" in PROCESSADORES
