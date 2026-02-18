#!/bin/bash
# scripts/sync_secrets.sh
# Synchronizes secrets from local .env to GitHub repository secrets using 'gh' CLI.

set -e

ENV_FILE="$HOME/.config/atlastrinity/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ℹ️  .env ще не створено в $ENV_FILE (це нормально для fresh install)."
    echo "   Додайте API ключі в $ENV_FILE та запустіть цей скрипт знову."
    exit 0
fi

if ! command -v gh &> /dev/null; then
    echo "🔗 GitHub CLI (gh) not found. Attempting to install with brew..."
    if command -v brew &> /dev/null; then
        brew install gh
    else
        echo "❌ Homebrew not found. Please install Homebrew first or install gh manually: brew install gh"
        exit 1
    fi
fi

# Load GITHUB_TOKEN from .env and export as GH_TOKEN for the CLI
GH_TOKEN_VAL=$(grep "^GITHUB_TOKEN=" "$ENV_FILE" | head -n 1 | cut -d '=' -f2- | sed "s/^['\"]//;s/['\"]$//")
if [ -n "$GH_TOKEN_VAL" ]; then
    export GH_TOKEN="$GH_TOKEN_VAL"
    echo "🔑 Using GITHUB_TOKEN from .env for authentication."
fi

# Check if authenticated (via GH_TOKEN or existing session)
# Use 'gh api user' which is more robust than 'gh auth status' as it validates the current token directly
if ! gh api user --jq '.login' &> /dev/null; then
    echo "❌ Authentication failed. Ensure GITHUB_TOKEN in .env is valid or run: gh auth login"
    exit 1
fi

# Exclude GITHUB_TOKEN (used for auth) and other common non-secret env vars if any
EXCLUDE_LIST=("GITHUB_TOKEN" "GITHUB_TOKEN_ACTION" "PATH" "PWD" "HOME")

echo "🎬 Starting secrets synchronization for $(basename $(pwd))..."

SYNC_COUNT=0

# Extract all keys that look like secrets/configs (CAPITAL_LETTERS=...)
# Excludes comments and empty lines
KEYS=$(grep -E "^[A-Z0-9_]+=" "$ENV_FILE" | cut -d '=' -f1)

for SECRET in $KEYS; do
    # Check if in exclude list
    SKIP=false
    for EXCLUDE in "${EXCLUDE_LIST[@]}"; do
        if [[ "$SECRET" == "$EXCLUDE" ]]; then
            SKIP=true
            break
        fi
    done
    
    if [ "$SKIP" = true ]; then
        echo "ℹ️  Skipping $SECRET (excluded)"
        continue
    fi

    # Extract value, handling quotes
    VALUE=$(grep "^$SECRET=" "$ENV_FILE" | head -n 1 | cut -d '=' -f2- | sed "s/^['\"]//;s/['\"]$//")
    
    if [ -n "$VALUE" ]; then
        echo "📤 Syncing $SECRET..."
        echo "$VALUE" | gh secret set "$SECRET"
        SYNC_COUNT=$((SYNC_COUNT + 1))
    fi
done

echo ""
echo "✅ Successfully synced $SYNC_COUNT secrets to GitHub repository."
echo "💡 You can now run your CI/CD pipelines with full access to these keys."
