#!/bin/bash

# Redis Stop Script for AtlasTrinity
# Stops Redis if it's running

echo "🛑 Stopping Redis..."

# Try to stop Redis using brew services (most common on macOS)
if command -v brew > /dev/null 2>&1; then
    if brew services list | grep -q "redis.*started"; then
        echo "🔄 Stopping Redis via brew services..."
        if brew services stop redis; then
            echo "✅ Redis stopped successfully"
            exit 0
        else
            echo "❌ Failed to stop Redis via brew services"
            exit 1
        fi
    else
        echo "ℹ️  Redis is not running via brew services"
    fi
fi

# Fallback: try to find and kill redis-server process
REDIS_PID=$(pgrep -f redis-server | head -1)
if [ ! -z "$REDIS_PID" ]; then
    echo "🔄 Killing redis-server process (PID: $REDIS_PID)..."
    if kill $REDIS_PID; then
        echo "✅ Redis process killed"
        exit 0
    else
        echo "❌ Failed to kill Redis process"
        exit 1
    fi
else
    echo "ℹ️  Redis process not found"
fi

echo "✅ Redis is stopped"
