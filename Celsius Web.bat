@echo off
setlocal
cd /d "E:\PythonProjectCELSIUS"
set "PYTHON_EXE=E:\PythonProjectCELSIUS\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Ambiente .venv nao encontrado. Abra o Celsius pelo PyCharm para configurar.
    pause
    exit /b 1
)

set "SCHEME=http"
set "MODE=lan"
if /i "%~1"=="--lan" set "MODE=lan"
if /i "%~1"=="--loopback" set "MODE=loopback"
if "%MODE%"=="lan" set "SCHEME=https"

rem Probe the TCP port instead of issuing an HTTPS request. A request-based probe
rem depends on a certificate-validation scriptblock, which fails on PowerShell 5.1
rem runspaces and makes an already running server look like a dead one.
powershell -NoProfile -Command "try { $c = New-Object System.Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 8790); $c.Close(); exit 0 } catch { exit 1 }"
if errorlevel 1 goto :start_server

echo O Celsius Web ja esta ativo em %SCHEME%://127.0.0.1:8790/app
start "" "%SCHEME%://127.0.0.1:8790/app"
exit /b 0

:start_server
if "%MODE%"=="loopback" (
    echo Iniciando Celsius Web em http://127.0.0.1:8790/app
    echo Mantenha esta janela aberta. Para encerrar, pressione Ctrl+C.
    start "Celsius Web" "%PYTHON_EXE%" -m core.web_api --host 127.0.0.1 --port 8790 --http
) else (
    echo Iniciando Celsius Web em https://127.0.0.1:8790/app
    echo Mantenha esta janela aberta. Para encerrar, pressione Ctrl+C.
    start "Celsius Web" "%PYTHON_EXE%" -m core.web_api --host 0.0.0.0 --port 8790 --allow-lan
)
timeout /t 3 /nobreak >nul
if "%MODE%"=="loopback" (
    start "" "http://127.0.0.1:8790/app"
) else (
    start "" "https://127.0.0.1:8790/app"
)
exit /b 0
