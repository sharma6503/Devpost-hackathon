#!/usr/bin/env bash
# Launch `adk web` locally with Datadog LLM Observability enabled.
#
# Telemetry is enabled by `ddtrace-run` reading DD_* env vars at process spawn —
# BEFORE the app calls load_dotenv(). A plain `adk web` (or DD_* vars living only
# in .env) will NOT emit traces. This script exports the vars from .env into the
# real environment first, then launches `ddtrace-run adk web`.
#
# Usage:
#   ./scripts/run_adk_web.sh
#   ./scripts/run_adk_web.sh --port 8080     # extra args pass through to adk web
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"

if [[ -f "$ENV_FILE" ]]; then
  echo "Loading env from $ENV_FILE"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"   # ltrim
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    key="$(echo -n "$key" | xargs)"            # trim key
    val="${val%\"}"; val="${val#\"}"           # strip surrounding quotes
    val="${val%\'}"; val="${val#\'}"
    export "$key=$val"
  done < "$ENV_FILE"
else
  echo "No env file at $ENV_FILE — relying on already-exported vars."
fi

if [[ -z "${DD_API_KEY:-}" ]]; then
  echo "WARNING: DD_API_KEY is not set — traces will NOT reach Datadog."
  echo "         Set it to the TEAM Datadog org key (a personal key hides traces in a sandbox account)."
fi

# Sensible LLM Obs defaults if the env file didn't set them.
export DD_LLMOBS_ENABLED="${DD_LLMOBS_ENABLED:-true}"
export DD_LLMOBS_ML_APP="${DD_LLMOBS_ML_APP:-agent-guardian}"
export DD_LLMOBS_AGENTLESS_ENABLED="${DD_LLMOBS_AGENTLESS_ENABLED:-true}"
export DD_APM_TRACING_ENABLED="${DD_APM_TRACING_ENABLED:-false}"
export DD_SITE="${DD_SITE:-us5.datadoghq.com}"
export DD_SERVICE="${DD_SERVICE:-agent-guardian}"
export DD_ENV="${DD_ENV:-dev}"

cd "$REPO_ROOT"
# Datadog is enabled in-process by `import ddtrace.auto` in agent.py — no ddtrace-run
# wrapper (it mangles args around adk.EXE on Windows). Env is already exported above.
echo "Launching: uv run adk web . $*"
exec uv run adk web . "$@"
