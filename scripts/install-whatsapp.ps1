$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$integrationDirectory = Join-Path $projectDirectory 'integrations\whatsapp'
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) { throw 'Instale o Node.js 22 ou superior antes de continuar.' }
Push-Location -LiteralPath $integrationDirectory
try {
    & $npmCommand.Source ci --omit=dev --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'A instalação da conexão WhatsApp falhou.' }
    Write-Host 'Conexão instalada. Abra o Celsius e clique em Conectar WhatsApp.'
} finally { Pop-Location }
