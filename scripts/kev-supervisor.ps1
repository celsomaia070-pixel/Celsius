<#
.SYNOPSIS
  Supervisiona o servidor local KEV/JEV do Celsius.

.DESCRIPTION
  Mantem kev.serve disponivel em 127.0.0.1. Se o processo encerrar, reinicia
  apos um pequeno intervalo. Use Start/Stop/Status para controlar o supervisor.
  Ele nao instala tarefa agendada nem servico do Windows; roda somente quando
  iniciado explicitamente pelo usuario ou pelo atalho do Celsius.

.EXAMPLE
  .\scripts\kev-supervisor.ps1 -Action Start
  .\scripts\kev-supervisor.ps1 -Action Status
  .\scripts\kev-supervisor.ps1 -Action Stop
#>
[CmdletBinding()]
param(
    [ValidateSet("Start", "Run", "Stop", "Status")]
    [string]$Action = "Status",
    [int]$Port = 8009,
    [string]$Model = "jaredpalmer/kev-0.5b",
    [int]$RestartDelaySeconds = 5
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stateDir = Join-Path $root "logs"
$pidFile = Join-Path $stateDir "kev-supervisor.pid"
$serverPidFile = Join-Path $stateDir "kev-server.pid"
$supervisorLog = Join-Path $stateDir "kev-supervisor.log"
$supervisorErr = Join-Path $stateDir "kev-supervisor.stderr.log"
$serverOut = Join-Path $stateDir "kev-server.stdout.log"
$serverErr = Join-Path $stateDir "kev-server.stderr.log"
$serverScript = Join-Path $PSScriptRoot "kev-server.ps1"
$venvPython = Join-Path $root "kev-venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

function Get-SavedProcess([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $value = (Get-Content -LiteralPath $path -Raw).Trim()
    $pidValue = 0
    if (-not [int]::TryParse($value, [ref]$pidValue)) { return $null }
    return Get-Process -Id $pidValue -ErrorAction SilentlyContinue
}

function Test-KevHealthy {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:$Port/v1/models"
        return $response.StatusCode -eq 200
    } catch { return $false }
}

if ($Action -eq "Status") {
    $supervisor = Get-SavedProcess $pidFile
    $server = Get-SavedProcess $serverPidFile
    $healthy = Test-KevHealthy
    [pscustomobject]@{
        Supervisor = if ($supervisor) { "running ($($supervisor.Id))" } else { "stopped" }
        Server = if ($server) { "running ($($server.Id))" } else { "stopped" }
        Healthy = $healthy
        Port = $Port
    } | Format-List
    exit $(if ($healthy) { 0 } else { 1 })
}

if ($Action -eq "Stop") {
    foreach ($path in @($serverPidFile, $pidFile)) {
        $process = Get-SavedProcess $path
        if ($process) { Stop-Process -Id $process.Id -Force }
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Supervisor KEV interrompido."
    exit 0
}

if ($Action -eq "Start") {
    $supervisor = Get-SavedProcess $pidFile
    if ($supervisor) {
        Write-Host "Supervisor KEV ja esta em execucao (PID $($supervisor.Id))."
        exit 0
    }
    $args = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Action Run -Port $Port -Model `"$Model`" -RestartDelaySeconds $RestartDelaySeconds"
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList $args -WindowStyle Hidden -RedirectStandardOutput $supervisorLog -RedirectStandardError $supervisorErr -PassThru
    $process.Id | Set-Content -LiteralPath $pidFile -NoNewline
    Write-Host "Supervisor KEV iniciado (PID $($process.Id))."
    exit 0
}

# Run: bootstrap once, then restart only the serving process when needed.
& $serverScript -Port $Port -Model $Model -NoStart
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel preparar o ambiente KEV." }

$PID | Set-Content -LiteralPath $pidFile -NoNewline
try {
    while ($true) {
        if (Test-KevHealthy) {
            Start-Sleep -Seconds 3
            continue
        }
        Write-Output "$(Get-Date -Format o) Starting kev.serve on port $Port"
        $server = Start-Process -FilePath $venvPython -ArgumentList "-m", "kev.serve", "--run", $Model, "--port", $Port -WindowStyle Hidden -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr -PassThru
        $server.Id | Set-Content -LiteralPath $serverPidFile -NoNewline
        $server.WaitForExit()
        Remove-Item -LiteralPath $serverPidFile -Force -ErrorAction SilentlyContinue
        Write-Output "$(Get-Date -Format o) kev.serve stopped (exit $($server.ExitCode)); retrying in $RestartDelaySeconds seconds"
        Start-Sleep -Seconds $RestartDelaySeconds
    }
} finally {
    Remove-Item -LiteralPath $serverPidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}
