<#
.SYNOPSIS
    Launch `adk web` locally with Datadog LLM Observability enabled.

.DESCRIPTION
    Telemetry is enabled by `ddtrace-run` reading DD_* environment variables at
    process spawn — BEFORE the app calls load_dotenv(). So a plain `adk web` (or
    DD_* vars living only in .env) will NOT emit traces.

    This script promotes the variables from .env into the real process environment
    first, then launches `ddtrace-run adk web`, so ddtrace sees them and instruments
    the google_adk / google_genai integrations.

.PARAMETER EnvFile
    Path to the env file to load (default: .env in the repo root).

.EXAMPLE
    ./scripts/run_adk_web.ps1
    ./scripts/run_adk_web.ps1 --port 8080          # extra args pass through to adk web
#>
[CmdletBinding()]
param(
    [string]$EnvFile,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AdkArgs
)

$ErrorActionPreference = "Stop"

# Repo root is the parent of this script's directory.
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot ".env" }

# Load KEY=VALUE lines from the env file into the current process environment.
if (Test-Path $EnvFile) {
    Write-Host "Loading env from $EnvFile" -ForegroundColor Cyan
    foreach ($line in Get-Content $EnvFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $idx = $trimmed.IndexOf("=")
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $val = $trimmed.Substring($idx + 1).Trim().Trim('"').Trim("'")
        Set-Item -Path "Env:$key" -Value $val
    }
} else {
    Write-Host "No env file at $EnvFile — relying on already-exported vars." -ForegroundColor Yellow
}

if (-not $env:DD_API_KEY) {
    Write-Host "WARNING: DD_API_KEY is not set — traces will NOT reach Datadog." -ForegroundColor Yellow
    Write-Host "         Set it to the TEAM Datadog org key (a personal key hides traces in a sandbox account)." -ForegroundColor Yellow
}

# Sensible LLM Obs defaults if the env file didn't set them.
if (-not $env:DD_LLMOBS_ENABLED)           { $env:DD_LLMOBS_ENABLED = "true" }
if (-not $env:DD_LLMOBS_ML_APP)            { $env:DD_LLMOBS_ML_APP = "agent-guardian" }
if (-not $env:DD_LLMOBS_AGENTLESS_ENABLED) { $env:DD_LLMOBS_AGENTLESS_ENABLED = "true" }
if (-not $env:DD_APM_TRACING_ENABLED)      { $env:DD_APM_TRACING_ENABLED = "false" }  # MUST be false: agentless LLM Obs only ships when APM tracing is off
if (-not $env:DD_SITE)                     { $env:DD_SITE = "us5.datadoghq.com" }
if (-not $env:DD_SERVICE)                  { $env:DD_SERVICE = "agent-guardian" }
if (-not $env:DD_ENV)                      { $env:DD_ENV = "dev" }

Set-Location $RepoRoot
# Datadog is enabled in-process by `import ddtrace.auto` in agent.py — no ddtrace-run
# wrapper (it mangles args around adk.EXE on Windows). Env is already set above.
Write-Host "Launching: uv run adk web . $AdkArgs" -ForegroundColor Green
uv run adk web . @AdkArgs
