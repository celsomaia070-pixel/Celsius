from workers.code_worker import executar_codigo


class TestCodeSandbox:
    def test_simple_execution(self):
        result = executar_codigo("print('hello')")
        assert result.success
        assert "hello" in result.stdout

    def test_math_calculation(self):
        result = executar_codigo("x = 2 + 2\nprint(x)")
        assert result.success
        assert "4" in result.stdout

    def test_data_processing(self):
        code = """
import json
data = {"a": 1, "b": 2}
print(json.dumps(data))
"""
        result = executar_codigo(code)
        assert result.success
        assert '"a": 1' in result.stdout

    def test_error_handling(self):
        result = executar_codigo("x = 1 / 0")
        assert not result.success
        assert "ZeroDivisionError" in result.stderr

    def test_timeout(self):
        code = """
import time
time.sleep(10)
"""
        result = executar_codigo(code, timeout=1)
        assert result.timed_out

    def test_blocked_import_os(self):
        result = executar_codigo("import os\nos.system('ls')")
        assert not result.success
        assert "Blocked import" in result.stderr

    def test_blocked_import_subprocess(self):
        result = executar_codigo("import subprocess\nsubprocess.run(['ls'])")
        assert not result.success
        assert "Blocked import" in result.stderr

    def test_blocked_eval(self):
        result = executar_codigo("eval('1+1')")
        assert not result.success
        assert "Blocked function" in result.stderr

    def test_blocked_exec(self):
        result = executar_codigo("exec('print(1)')")
        assert not result.success
        assert "Blocked function" in result.stderr

    def test_blocked_open(self):
        result = executar_codigo("open('/etc/passwd').read()")
        assert not result.success
        assert "Blocked function" in result.stderr

    def test_allowed_imports(self):
        # These should work
        for module in ["math", "random", "json", "datetime", "collections"]:
            result = executar_codigo(f"import {module}\nprint({module}.__name__)")
            assert result.success, f"Failed for {module}: {result.stderr}"

    def test_no_file_access(self):
        result = executar_codigo("""
import pathlib
pathlib.Path('/etc/passwd').read_text()
""")
        assert not result.success

    def test_output_limit(self):
        result = executar_codigo("print('x' * 100000)")
        assert result.success
        assert len(result.stdout) <= 50000  # max_output limit
