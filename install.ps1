param(
    [string]$Python = '',
    [ValidateSet('all','codex','claude-code','claude-desktop','cursor','trae','workbuddy','doubao','generic')]
    [string]$Client = 'all',
    [switch]$ConfigOnly,
    [switch]$Offline,
    [string]$Wheelhouse = '',
    [string]$IndexUrl = ''
)
$ErrorActionPreference = 'Stop'
$shopdateArgs = @((Join-Path $PSScriptRoot 'installer.py'), '--client', $Client)
if ($ConfigOnly) { $shopdateArgs += '--config-only' }
if ($Offline) { $shopdateArgs += '--offline' }
if ($Wheelhouse) { $shopdateArgs += @('--wheelhouse', $Wheelhouse) }
if ($IndexUrl) { $shopdateArgs += @('--index-url', $IndexUrl) }
if ($Python) {
    & $Python @shopdateArgs
} elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv/Scripts/python.exe')) {
    & (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') @shopdateArgs
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3-64 @shopdateArgs
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python @shopdateArgs
} else {
    throw 'Install 64-bit Python 3.11+ first, or provide -Python with an absolute Python path.'
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
