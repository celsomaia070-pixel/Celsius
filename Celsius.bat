@echo off
setlocal
cd /d "E:\PythonProjectCELSIUS"
set "PYTHON_EXE=E:\PythonProjectCELSIUS\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Ambiente .venv nao encontrado. Abra o Celsius pelo PyCharm para configurar.
    pause
    exit /b 1
)
start "" "%PYTHON_EXE%" main.py