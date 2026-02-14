#!/bin/bash

# Redis Check Script for AtlasTrinity
# Checks if Redis is running and ready to accept connections

echo "🔍 Checking Redis status..."

# Function to wait for Redis to be ready
wait_for_redis_ready() {
    local max_attempts=30
    local attempt=1
    
    echo "⏳ Waiting for Redis to be fully ready..."
    
    while [ $attempt -le $max_attempts ]; do
        if redis-cli ping > /dev/null 2>&1; then
            # Additional check: try a simple operation
            if redis-cli set atlas_check "ready" > /dev/null 2>&1 && redis-cli get atlas_check > /dev/null 2>&1; then
                redis-cli del atlas_check > /dev/null 2>&1
                echo "✅ Redis is fully ready"
                return 0
            fi
        fi
        
        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done
    
    echo ""
    echo "❌ Redis did not become ready within $max_attempts seconds"
    return 1
}

# Check if Redis is running
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis is responding"
    
    # Wait for Redis to be fully ready
    if wait_for_redis_ready; then
        exit 0
    else
        echo "❌ Redis responded but not ready for connections"
        exit 1
    fi
fi

echo "⚠️  Redis is not running. Attempting to start..."

# Try to start Redis using brew services (most common on macOS)
if command -v brew > /dev/null 2>&1; then
    if brew services list | grep -q "redis.*started"; then
        echo "✅ Redis is already started via brew services"
        # Wait for it to be ready
        if wait_for_redis_ready; then
            exit 0
        else
            exit 1
        fi
    fi
    
    echo "🚀 Starting Redis via brew services..."
    if brew services start redis; then
        echo "⏳ Waiting for Redis to start and be ready..."
        
        # Wait for Redis to be ready
        if wait_for_redis_ready; then
            echo "✅ Redis started successfully"
            exit 0
        else
            echo "❌ Redis failed to become ready after brew services"
            exit 1
        fi
    fi
fi

# Fallback: try to start redis-server directly
if command -v redis-server > /dev/null 2>&1; then
    echo "🚀 Starting redis-server directly..."
    
    # Start redis-server in background
    redis-server --daemonize yes > /dev/null 2>&1
    
    echo "⏳ Waiting for Redis to start and be ready..."
    
    # Wait for Redis to be ready
    if wait_for_redis_ready; then
        echo "✅ Redis started successfully"
        exit 0
    else
        echo "❌ Redis failed to start or become ready"
        exit 1
    fi
fi

# If we get here, Redis is not available
echo "❌ Redis not found. Please install Redis:"
echo "   brew install redis"
echo "   # or download from https://redis.io/download"
exit 1
