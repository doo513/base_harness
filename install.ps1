[CmdletBinding()]
param(
  [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Programs\base-harness")
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSCommandPath
$RuntimeRoot = Join-Path $RepoRoot "runtime"
$EntryPoint = Join-Path $RuntimeRoot "src\cli.ts"
$BinRoot = Join-Path $InstallRoot "bin"
$Launcher = Join-Path $BinRoot "base-harness.cmd"

if (-not (Test-Path -LiteralPath $EntryPoint)) {
  throw "Base Harness runtime entry point was not found: $EntryPoint"
}
if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
  throw "Bun 1.3.14 or newer is required during the experimental source-runtime phase."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3.11 or newer is required for the independent verifier."
}

& python -m pip install -e $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "Verifier installation failed." }
Push-Location $RuntimeRoot
try {
  & bun install
  if ($LASTEXITCODE -ne 0) { throw "Runtime dependency installation failed." }
} finally {
  Pop-Location
}

New-Item -ItemType Directory -Path $BinRoot -Force | Out-Null
$launcherText = @"
@echo off
setlocal
bun run "$EntryPoint" %*
exit /b %ERRORLEVEL%
"@
Set-Content -LiteralPath $Launcher -Value $launcherText -Encoding ascii

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not (($userPath -split ";") -contains $BinRoot)) {
  [Environment]::SetEnvironmentVariable("Path", "$BinRoot;$userPath", "User")
}
Write-Host "Base Harness installed: $Launcher"
