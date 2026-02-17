# Use Swift 5.9 as base image
FROM swift:5.9-focal as builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy package files
COPY Package.swift Package.resolved ./

# Build the application
RUN swift build --configuration release --product mcp-server-windsurf

# Production stage
FROM ubuntu:22.04

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash windsurf
USER windsurf

# Set working directory
WORKDIR /home/windsurf

# Copy built application from builder
COPY --from=builder /app/.build/release/mcp-server-windsurf /usr/local/bin/mcp-server-windsurf

# Create necessary directories
RUN mkdir -p /home/windsurf/.config/atlastrinity/{logs,windsurf_workspaces,plugins}

# Set permissions
RUN chmod +x /usr/local/bin/mcp-server-windsurf

# Environment variables
ENV WINDSURF_LOG_LEVEL=info
ENV WINDSURF_CACHE_SIZE=100
ENV WINDSURF_ENABLE_PLUGINS=true
ENV WINDSURF_CONFIG_PATH=/home/windsurf/.config/atlastrinity/windsurf_config.json

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose port
EXPOSE 8080

# Start the application
CMD ["mcp-server-windsurf"]
