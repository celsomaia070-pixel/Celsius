@echo off
REM Celsius - Build Script
REM Gera o instalador Windows usando PyInstaller + Inno Setup

setlocal enabledelayedexpansion

echo ============================================================
echo   Celsius - Build do Instalador
echo ============================================================
echo.

set PROJECT_ROOT=%~dp0..
set DIST_DIR=%PROJECT_ROOT%\dist
set BUILD_DIR=%PROJECT_ROOT%\build
set SPEC_FILE=%PROJECT_ROOT%\celsius.spec
set ISS_FILE=%PROJECT_ROOT%\installer\celsius.iss

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale Python 3.10+ e adicione ao PATH.
    exit /b 1
)

REM Check PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando PyInstaller...
    pip install pyinstaller
)

REM Check Inno Setup
set ISCC_PATH=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe
) else (
    where ISCC.exe >nul 2>&1
    if not errorlevel 1 (
        set ISCC_PATH=ISCC.exe
    )
)

if "%ISCC_PATH%"=="" (
    echo [ERRO] Inno Setup 6 nao encontrado.
    echo Baixe em: https://jrsoftware.org/isdl.php
    echo Instale e execute novamente este script.
    exit /b 1
)

echo [1/4] Instalando dependencias...
pip install -r %PROJECT_ROOT%\requirements.txt --quiet
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    exit /b 1
)

echo.
echo [2/4] Limpando builds anteriores...
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"

echo.
echo [3/4] Compilando com PyInstaller...
pyinstaller "%SPEC_FILE%" --clean --noconfirm
if errorlevel 1 (
    echo [ERRO] PyInstaller falhou.
    exit /b 1
)

echo.
echo [4/4] Gerando instalador com Inno Setup...
"%ISCC_PATH%" "%ISS_FILE%"
if errorlevel 1 (
    echo [ERRO] Inno Setup falhou.
    exit /b 1
)

echo.
echo ============================================================
echo   BUILD CONCLUIDO COM SUCESSO!
echo ============================================================
echo.
echo Instalador: %DIST_DIR%\Celsius-Setup-v1.0.0.exe
echo.

REM Show file size
for %%A in ("%DIST_DIR%\Celsius-Setup-v1.0.0.exe") do (
    set SIZE=%%~zA
    set /a SIZE_MB=!SIZE! / 1048576
    echo Tamanho: !SIZE_MB! MB
)

echo.
echo Proximo passo: Teste o instalador executando-o.
echo.

endlocal
