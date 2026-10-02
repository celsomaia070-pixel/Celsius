<#
.SYNOPSIS
  Sobe o servidor de decisoes local (kev.serve) usado pela camada JEV/System One do Celsius.

.DESCRIPTION
  1. Cria/usa uma venv dedicada (kev-venv) com as deps pinadas em requirements-kev.txt;
  2. Clona o repo do kev no commit pinado (build\kev-src) e instala de forma editavel;
  3. Sobe o servidor de decisoes (padrao: porta 8009, modelo jaredpalmer/kev-0.5b).

  O Celsius fala com este processo via HTTP em 127.0.0.1:<Port>/v1/systemone
  quando CELSIUS_DECISION_ENABLED=true. Parar com Ctrl+C.

.PARAMETER Port
  Porta do servidor (default 8009).

.PARAMETER Model
  Run do kev a servir (default jaredpalmer/kev-0.5b).

.PARAMETER NoStart
  Apenas prepara a venv + kev instalado, sem subir o servidor.

.EXAMPLE
  .\scripts\kev-server.ps1
.EXAMPLE
  .\scripts\kev-server.ps1 -Port 8010 -NoStart
#>
[CmdletBinding()]
param(
    [int]$Port = 8009,
    [string]$Model = "jaredpalmer/kev-0.5b",
    [string]$VenvName = "kev-venv",
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $root $VenvName
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$reqFile = Join-Path $root "requirements-kev.txt"
$kevSrc = Join-Path $root "build\kev-src"
$kevGit = Join-Path $kevSrc ".git"
$kevRev = "557598fced1dada75dfbf36ed144dce309ac6ceb"

function Get-PythonVersion([string]$py) {
    $out = & $py -c "import sys; print(sys.version_info.major, sys.version_info.minor)"
    if ($LASTEXITCODE -ne 0) { throw "Python invalido: $py" }
    $parts = $out -split " "
    return [int]$parts[0], [int]$parts[1]
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Criando venv dedicada em $venvDir"
    & python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar a venv" }
}

$verMajor, $verMinor = Get-PythonVersion $venvPython
Write-Host "Python da venv: $verMajor.$verMinor"

Write-Host "Instalando deps do servidor de decisoes (requirements-kev.txt)..."
& $venvPython -m pip install -U pip
if ($LASTEXITCODE -ne 0) { throw "Falha ao atualizar pip" }
& $venvPython -m pip install -r $reqFile --extra-index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar requirements-kev.txt" }

if (-not (Test-Path -LiteralPath $kevGit)) {
    if (-not (Test-Path -LiteralPath $kevSrc)) {
        New-Item -ItemType Directory -Path $kevSrc | Out-Null
    }
    Write-Host "Clonando kev (pinado em $kevRev)..."
    & git clone --quiet https://github.com/jaredpalmer/kev "$kevSrc"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao clonar o kev" }
    Push-Location $kevSrc
    try {
        & git checkout --quiet $kevRev
        if ($LASTEXITCODE -ne 0) { throw "Falha no git checkout do commit pinado" }
    } finally {
        Pop-Location
    }
}

# A primeira execucao deve falhar aqui para cair no bloco de instalacao. Com
# ErrorActionPreference=Stop, o stderr do Python vira NativeCommandError e
# encerrava o script antes de avaliarmos LASTEXITCODE.
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $venvPython -c "import kev" 2>$null
$kevImportExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($kevImportExitCode -ne 0) {
    Write-Host "Instalando kev (editavel)..."
    & $venvPython -m pip install -e $kevSrc
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Install normal falhou em Python $verMajor.$verMinor; tentando --no-deps --ignore-requires-python (kev pina <3.14)"
        & $venvPython -m pip install --no-deps --ignore-requires-python -e $kevSrc
        if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar o kev" }
    }
}

if ($NoStart) {
    Write-Host ""
    Write-Host "Bootstrap concluido. Para subir manualmente:"
    Write-Host "  & `"$venvPython`" -m kev.serve --run $Model --port $Port"
    exit 0
}

Write-Host ""
Write-Host "Subindo kev.serve porta=$Port modelo=$Model ..."
& $venvPython -m kev.serve --run $Model --port $Port
