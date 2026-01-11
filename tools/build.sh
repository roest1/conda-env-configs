#!/usr/bin/env bash
set -e

ENV_NAME="$1"

if [[ -z "$ENV_NAME" ]]; then
  echo "Usage: build.sh <env-name>"
  exit 1
fi

ENV_FILE="$ENV_NAME/environment.yml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ Environment file not found: $ENV_FILE"
  exit 1
fi

echo "🚀 Building environment: $ENV_NAME"
conda env update -n "$ENV_NAME" -f "$ENV_FILE" --prune
echo "✅ Done."
