#!/bin/bash
# --- Agent Guardian System Setup ---
# This script is executed by Vertex AI Reasoning Engine during the container build.

set -e # Exit immediately if a command fails

echo "Installing system dependencies..."
apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg unzip wget util-linux \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

echo "Installing uv and other core Python libraries..."
# Install uv via pip to guarantee it's in the Python environment's PATH
pip install --no-cache-dir uv google-cloud-aiplatform google-adk

echo "Pre-installing MCP servers..."
# Ensure the python bin directory is in the path
export PATH="$(dirname $(which python)):$PATH"

# Pre-download MCP servers so they are cached in the container image
uv tool install mcp-atlassian
uv tool install mcpdoc
npm install -g @modelcontextprotocol/server-github

echo "Installing ast-grep (sg)..."
mkdir -p /tmp/ast-grep
curl -LsSf https://github.com/ast-grep/ast-grep/releases/latest/download/app-x86_64-unknown-linux-gnu.zip -o /tmp/ast-grep.zip
unzip /tmp/ast-grep.zip -d /tmp/ast-grep
mv /tmp/ast-grep/sg /usr/local/bin/sg
chmod +x /usr/local/bin/sg
rm -rf /tmp/ast-grep /tmp/ast-grep.zip

echo "System setup completed successfully."
