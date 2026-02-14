#!/bin/bash
# scripts/auto_commit_backups.sh
# Automatically commits and pushes database backups after fresh install

set -e

# Determine project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔄 Auto-commit and push database backups..."

# Check if there are any changes to commit
if ! git status --porcelain | grep -E "backups/databases/"; then
    echo "ℹ️  No database backup changes found. Skipping commit."
    exit 0
fi

# Load GitHub token from .env if available
ENV_FILE="$HOME/.config/atlastrinity/.env"
if [ -f "$ENV_FILE" ]; then
    GITHUB_TOKEN_VAL=$(grep "^GITHUB_TOKEN=" "$ENV_FILE" | head -n 1 | cut -d '=' -f2- | sed "s/^['\"]//;s/['\"]$//")
    if [ -n "$GITHUB_TOKEN_VAL" ]; then
        export GH_TOKEN="$GITHUB_TOKEN_VAL"
        echo "🔑 Using GITHUB_TOKEN from .env for authentication."
    fi
fi

# Check if GitHub CLI is available and authenticated
if command -v gh &> /dev/null; then
    if gh api user --jq '.login' &> /dev/null; then
        echo "🔗 GitHub CLI authenticated."
        USE_GH_CLI=true
    else
        echo "⚠️  GitHub CLI not authenticated. Using git push with token."
        USE_GH_CLI=false
    fi
else
    echo "⚠️  GitHub CLI not found. Using git push with token."
    USE_GH_CLI=false
fi

# Configure git with token if available
if [ -n "$GITHUB_TOKEN_VAL" ] && [ "$USE_GH_CLI" = false ]; then
    # Set up remote URL with token for push
    git remote set-url origin "https://$GITHUB_TOKEN_VAL@github.com/solagurma/atlastrinity.git"
    echo "🔐 Configured git remote with token."
fi

# Stage only backup files
echo "📦 Staging database backup files..."
git add backups/databases/

# Check if there's anything to commit
if git diff --cached --quiet; then
    echo "ℹ️  No staged changes. Nothing to commit."
    exit 0
fi

# Create commit with timestamp
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
COMMIT_MSG="Auto-commit database backups after fresh install - $TIMESTAMP"

echo "📝 Creating commit: $COMMIT_MSG"
git commit --no-verify -m "$COMMIT_MSG"

# Push changes
echo "🚀 Pushing to GitHub..."
if [ "$USE_GH_CLI" = true ]; then
    git push
else
    git push origin main
fi

echo "✅ Database backups successfully committed and pushed to GitHub!"
echo "📊 Commit: $(git log -1 --oneline)"
