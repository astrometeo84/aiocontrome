<#
.SYNOPSIS
    Runs the opt-in live tests of aiocontrome against your Controme Mini-Server.

.DESCRIPTION
    Asks for the address, username and password, sets the CONTROME_* environment variables for
    this run only, starts "uv run --extra dev pytest -m live" and restores the previous state
    afterwards (CONTROME_* variables set before the run are cleared for the run and restored at
    the end).
    Credentials are read with Read-Host (not stored in the command line or the history); the
    password is entered as SecureString. Leave the username empty to skip the credential check.

    Read-only except one credential probe: set_room_offset on room 99999 (does not exist)
    with offset 0. See docs/LIVE_TESTS.md. Works with Windows PowerShell 5.1 and PowerShell 7.

.EXAMPLE
    .\scripts\run-live-tests.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error 'uv was not found in PATH. Install uv first (https://docs.astral.sh/uv/).'
    exit 2
}

$repo = Split-Path -Parent $PSScriptRoot
# All variables the live tests read. Values left over in this session (e.g. from a manual run)
# must not leak into this run: they are saved, cleared and restored in the finally block.
$names = @('CONTROME_LIVE', 'CONTROME_HOST', 'CONTROME_HOUSE', 'CONTROME_USER', 'CONTROME_PASSWORD')

$defaultHost = $env:CONTROME_IP
$prompt = 'Address of the Mini-Server'
if ($defaultHost) { $prompt += " [$defaultHost]" }
$address = (Read-Host $prompt).Trim()
if (-not $address) { $address = $defaultHost }
if (-not $address) {
    Write-Error 'No address given (and $env:CONTROME_IP is not set).'
    exit 2
}

$user = (Read-Host 'Controme username (empty = skip credential check)').Trim()
$plain = $null
if ($user) {
    $secure = Read-Host 'Password (empty = skip credential check)' -AsSecureString
    if ($secure.Length -gt 0) {
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        }
        finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
    $secure.Dispose()
}

$saved = @{}
foreach ($name in $names) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

$exitCode = 1
Push-Location $repo
try {
    foreach ($name in $names) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $env:CONTROME_LIVE = '1'
    $env:CONTROME_HOST = $address
    if ($plain) {
        $env:CONTROME_USER = $user
        $env:CONTROME_PASSWORD = $plain
    }
    else {
        Write-Host 'No credentials given: the credential check will be skipped.'
    }
    & uv run --extra dev pytest -m live --no-cov -p no:cacheprovider -q --tb=short
    $exitCode = $LASTEXITCODE
}
finally {
    # Restore the previous state: variables that were not set before are removed.
    foreach ($name in $names) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
    $plain = $null
    Pop-Location
}
exit $exitCode
