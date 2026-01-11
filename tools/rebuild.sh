#!/usr/bin/env bash
set -e

ENV_NAME="$1"

if [[ -z "$ENV_NAME" ]]; then
  echo "Usage: rebuild.sh <env-name>"
  exit 1
fi

read -p "⚠️  Delete and rebuild environment '$ENV_NAME'? [y/N] " confirm
if [[ "$confirm" != "y" ]]; then
  echo "Aborted."
  exit 0
fi

echo "🧨 Removing environment: $ENV_NAME"
conda remove -n "$ENV_NAME" --all -y

ENV_FILE="$ENV_NAME/environment.yml"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ Environment file not found: $ENV_FILE"
  exit 1
fi

echo "🚀 Recreating environment: $ENV_NAME"
conda env create -f "$ENV_FILE"
echo "✅ Done."
