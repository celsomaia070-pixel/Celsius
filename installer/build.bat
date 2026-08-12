@echo off
REM Celsius - Build reprodutivel do executavel/instalador Windows
REM Uso:
REM   build.bat thin exe
REM   build.bat thin installer
REM   build.bat offline installer

setlocal

set "PROJECT_ROOT=%~dp0.."
set "DIST_DIR=%PROJECT_ROOT%\dist"
set "BUILD_DIR=%PROJECT_ROOT%\build"
set "SPEC_FILE=%PROJECT_ROOT%\celsius.spec"
set "ISS_FILE=%PROJECT_ROOT%\installer\celsius.iss"
set "BUILD_FLAVOR=%~1"
set "BUILD_TARGET=%~2"

if "%BUILD_FLAVOR%"=="" set "BUILD_FLAVOR=thin"
if "%BUILD_TARGET%"=="" set "BUILD_TARGET=installer"

if /I not "%BUILD_FLAVOR%"=="thin" if /I not "%BUILD_FLAVOR%"=="offline" (
    echo [ERRO] Sabor invalido: %BUILD_FLAVOR%
    echo Use: thin ou offline
    exit /b 2
)
if /I not "%BUILD_TARGET%"=="exe" if /I not "%BUILD_TARGET%"=="installer" (
    echo [ERRO] Alvo invalido: %BUILD_TARGET%
    echo Use: exe ou installer
    exit /b 2
)

set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%PROJECT_ROOT%\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERRO] Ambiente virtual nao encontrado em .venv ou venv.
    exit /b 1
)

if /I "%BUILD_FLAVOR%"=="offline" (
    set "CELSIUS_BUNDLE_MODELS=1"
    if not exist "%PROJECT_ROOT%\resources\qwen2.5-vl-7b-q4_k_m.gguf" (
        echo [ERRO] Modelo padrao ausente para build offline.
        exit /b 1
    )
    if not exist "%PROJECT_ROOT%\resources\mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf" (
        echo [ERRO] mmproj ausente para build offline multimodal.
        exit /b 1
    )
) else (
    set "CELSIUS_BUNDLE_MODELS=0"
)

echo ============================================================
echo   Celsius - Build %BUILD_FLAVOR% / %BUILD_TARGET%
echo ============================================================

echo [1/7] Preparando ferramentas...
"%PYTHON_EXE%" -m pip install --upgrade pip --quiet
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" -m pip install -r "%PROJECT_ROOT%\pylock.toml"
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" -m pip install pyinstaller ruff pytest --quiet
if errorlevel 1 exit /b 1

echo [2/7] Validando codigo e testes...
pushd "%PROJECT_ROOT%"
"%PYTHON_EXE%" -m ruff check .
if errorlevel 1 goto :failure_popd
"%PYTHON_EXE%" -m pytest -q
if errorlevel 1 goto :failure_popd

echo [3/7] Executando preflight de release...
"%PYTHON_EXE%" tools\release_preflight.py --flavor %BUILD_FLAVOR%
if errorlevel 1 goto :failure_popd

echo [4/7] Limpando build anterior...
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"

echo [5/7] Compilando com PyInstaller...
"%PYTHON_EXE%" -m PyInstaller "%SPEC_FILE%" --clean --noconfirm
if errorlevel 1 goto :failure_popd

echo [6/7] Testando executavel empacotado...
if exist "%LOCALAPPDATA%\Celsius\logs\self-test.json" del /q "%LOCALAPPDATA%\Celsius\logs\self-test.json"
start "" /wait "%DIST_DIR%\Celsius\Celsius.exe" --self-test
if errorlevel 1 (
    echo [ERRO] O self-test do executavel falhou.
    if exist "%LOCALAPPDATA%\Celsius\logs\self-test.json" type "%LOCALAPPDATA%\Celsius\logs\self-test.json"
    goto :failure_popd
)
if not exist "%LOCALAPPDATA%\Celsius\logs\self-test.json" (
    echo [ERRO] Executavel nao produziu o relatorio de self-test.
    goto :failure_popd
)
type "%LOCALAPPDATA%\Celsius\logs\self-test.json"

if /I "%BUILD_TARGET%"=="exe" goto :success_popd

echo [7/7] Gerando instalador com Inno Setup...
set "ISCC_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
if "%ISCC_PATH%"=="" (
    echo [ERRO] Inno Setup 6 nao encontrado.
    echo O executavel foi gerado em: %DIST_DIR%\Celsius\Celsius.exe
    echo Instale o Inno Setup e rode novamente para gerar o instalador.
    goto :failure_popd
)
"%ISCC_PATH%" "%ISS_FILE%"
if errorlevel 1 goto :failure_popd

:success_popd
popd
echo.
echo BUILD CONCLUIDO.
echo Executavel: %DIST_DIR%\Celsius\Celsius.exe
if /I "%BUILD_TARGET%"=="installer" echo Instalador: %DIST_DIR%\Celsius-Setup-v1.0.0.exe
exit /b 0

:failure_popd
popd
echo.
echo [ERRO] Build interrompido. Consulte a mensagem acima.
exit /b 1
