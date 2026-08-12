from tools.sync_requirements import render_files


def test_generated_requirement_files_match_pyproject():
    for path, expected in render_files().items():
        assert path.read_text(encoding="utf-8") == expected
