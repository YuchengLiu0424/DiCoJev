[CmdletBinding()]
param(
    [string]$Python = 'D:\LLM\LLaDA-V\.venv\Scripts\python.exe',
    [string]$ModelPath = 'D:\LLM\LLaDA-V',
    [string]$CodePath = 'D:\LLM\LLaDA-V-code',
    [string]$HostAddress = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$Port = 8002,
    [string]$TracePath = ''
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$serverScript = Join-Path $PSScriptRoot 'llada_openai_server.py'

foreach ($requiredPath in @($Python, $ModelPath, $CodePath, $serverScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path does not exist: $requiredPath"
    }
}

$env:PYTHONPATH = Join-Path $CodePath 'train'
if ($TracePath) {
    $env:LLADA_TRACE_PATH = $TracePath
}
$nativeArgs = @(
    $serverScript
    '--model-path'
    $ModelPath
    '--code-path'
    $CodePath
    '--host'
    $HostAddress
    '--port'
    $Port.ToString()
)

Write-Host "Starting LLaDA-V for DiCoJev from $repositoryRoot"
& $Python @nativeArgs
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    throw "LLaDA-V server failed with exit code $exitCode"
}
