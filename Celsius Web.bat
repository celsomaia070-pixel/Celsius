@echo off
setlocal
cd /d "E:\PythonProjectCELSIUS"
set "PYTHON_EXE=E:\PythonProjectCELSIUS\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Ambiente .venv nao encontrado. Abra o Celsius pelo PyCharm para configurar.
    pause
    exit /b 1
)

powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8790/app' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }"
if errorlevel 1 goto :start_server

echo O Celsius Web ja esta ativo em http://127.0.0.1:8790/app
start "" "http://127.0.0.1:8790/app"
exit /b 0

:start_server
set "MODE=lan"
if /i "%~1"=="--lan" set "MODE=lan"
if /i "%~1"=="--loopback" set "MODE=loopback"
if "%MODE%"=="loopback" (
    echo Iniciando Celsius Web em http://127.0.0.1:8790/app
    echo Mantenha esta janela aberta. Para encerrar, pressione Ctrl+C.
    start "Celsius Web" "%PYTHON_EXE%" -m core.web_api --host 127.0.0.1 --port 8790 --http
) else (
    echo Iniciando Celsius Web em http://127.0.0.1:8790/app
    echo Mantenha esta janela aberta. Para encerrar, pressione Ctrl+C.
    start "Celsius Web" "%PYTHON_EXE%" -m core.web_api --host 0.0.0.0 --port 8790 --allow-lan
)
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8790/app"
exit /b 0