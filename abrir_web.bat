@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Ambiente .venv nao encontrado. Consulte docs\GUIA_INICIANTE.md.
    pause
    exit /b 1
)
set "MODE=lan"
if /i "%~1"=="--lan" set "MODE=lan"
if /i "%~1"=="--loopback" set "MODE=loopback"
if "%MODE%"=="loopback" (
    echo Abra http://127.0.0.1:8790/app no navegador deste computador.
    echo Use o QR de celular apenas com o modo rede local (--lan).
    echo Mantenha esta janela aberta. Para encerrar, pressione Ctrl+C.
    "%PYTHON_EXE%" -m core.web_api --host 127.0.0.1 --port 8790 --http
) else (
    echo Modo rede local (HTTPS): o QR de pareamento fica acessivel pelo celular.
    echo Abra http://127.0.0.1:8790/app no navegador deste computador e use o botao de pareamento.
    echo Mantenha esta janela aberta. Para encerrar, pressione Ctrl+C.
    "%PYTHON_EXE%" -m core.web_api --host 0.0.0.0 --port 8790 --allow-lan
)
if errorlevel 1 (
    echo Se a porta estiver ocupada, abra o endereco acima ou use --port 8791.
    pause
    exit /b 1
)