# 🚀 Windsurf MCP Provider - Deployment and Operations Guide

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Docker Deployment](#docker-deployment)
3. [Kubernetes Deployment](#kubernetes-deployment)
4. [Configuration Management](#configuration-management)
5. [Monitoring and Analytics](#monitoring-and-analytics)
6. [Troubleshooting](#troubleshooting)
7. [Performance Optimization](#performance-optimization)
8. [Security Considerations](#security-considerations)

## 🚀 Quick Start

### Prerequisites
- Docker 20.10+ or Kubernetes 1.20+
- Swift 5.9+ (for building from source)
- Valid WINDSURF_API_KEY

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/your-org/atlastrinity.git
cd atlastrinity

# Set up environment
export WINDSURF_API_KEY=sk-ws-your-api-key-here

# Build the application
cd vendor/mcp-server-windsurf
swift build --configuration release

# Run locally
swift run --configuration release
```

### Quick Test

```bash
# Test the MCP server
python3 scripts/windsurf/comprehensive_demo.py

# Run comprehensive tests
python3 tests/test_windsurf_mcp_comprehensive.py
```

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Navigate to the MCP server directory
cd vendor/mcp-server-windsurf

# Create environment file
cat > .env << EOF
WINDSURF_API_KEY=sk-ws-your-api-key-here
WORKSPACE_PATH=./workspace
EOF

# Start the complete stack
docker-compose up -d

# Check logs
docker-compose logs -f windsurf-mcp

# Stop the stack
docker-compose down
```

### Individual Docker Commands

```bash
# Build the image
docker build -t windsurf-mcp:latest .

# Run the container
docker run -d \
  --name windsurf-mcp \
  -p 8080:8080 \
  -e WINDSURF_API_KEY=sk-ws-your-api-key-here \
  -v $(pwd)/workspace:/app/workspace \
  windsurf-mcp:latest

# Check container status
docker ps
docker logs windsurf-mcp

# Stop the container
docker stop windsurf-mcp
docker rm windsurf-mcp
```

### Docker Compose Services

| Service | Port | Description |
|---------|------|-------------|
| windsurf-mcp | 8080 | Main MCP server |
| redis | 6379 | Caching and session storage |
| prometheus | 9090 | Metrics collection |
| grafana | 3000 | Analytics dashboard |
| nginx | 80/443 | Reverse proxy |

## ☸️ Kubernetes Deployment

### Prerequisites
- Kubernetes cluster 1.20+
- kubectl configured
- Helm 3.0+ (optional)

### Namespace Setup

```bash
# Create namespace
kubectl create namespace windsurf

# Set default namespace
kubectl config set-context --current=windsurf
```

### Deploy with YAML Manifests

```bash
# Apply all manifests
kubectl apply -f kubernetes/

# Check deployment status
kubectl get pods -n windsurf

# Check services
kubectl get services -n windsurf

# Check ingress
kubectl get ingress -n windsurf
```

### Deploy with Helm (Alternative)

```bash
# Add Helm repository (if not already added)
helm repo add windsurf https://charts.windsurf-mcp.com
helm repo update

# Install the chart
helm install windsurf-mcp windsurf/windsurf-mcp \
  --namespace windsurf \
  --set apiKey=sk-ws-your-api-key-here \
  --set replicaCount=3 \
  --set resources.requests.memory=512Mi \
  --set resources.limits.memory=2Gi

# Upgrade the chart
helm upgrade windsurf-mcp windsurf/windsurf-mcp \
  --namespace windsurf \
  --set apiKey=sk-ws-your-new-key-here

# Uninstall
helm uninstall windsurf-mcp --namespace windsurf
```

### Scaling and Updates

```bash
# Scale deployment
kubectl scale deployment windsurf-mcp --replicas=5 -n windsurf

# Update configuration
kubectl patch configmap windsurf-config -n windsurf --patch-file=update-config.yaml

# Restart deployment
kubectl rollout restart deployment/windsurf-mcp -n windsurf

# Check rollout status
kubectl rollout status deployment/windsurf-mcp -n windsurf
```

## ⚙️ Configuration Management

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WINDSURF_API_KEY` | Windsurf API key | Required |
| `WINDSURF_LOG_LEVEL` | Logging level | `info` |
| `WINDSURF_CACHE_SIZE` | Cache size | `100` |
| `WINDSURF_ENABLE_PLUGINS` | Enable plugins | `true` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379` |

### Configuration File

```json
{
  "general": {
    "defaultModel": "swe-1.5",
    "timeoutDuration": 120,
    "retryAttempts": 3,
    "autoDetectWorkspace": true
  },
  "cascade": {
    "enableActionPhase": true,
    "enableCortexReasoning": true,
    "enableFileOperations": true,
    "enableToolExecution": true,
    "enableAutonomousExecution": true,
    "actionTimeout": 180
  },
  "performance": {
    "enableCaching": true,
    "cacheSize": 100,
    "cacheExpiration": 300,
    "enableConnectionPooling": true,
    "maxConnections": 3,
    "enableRequestBatching": true,
    "batchSize": 5,
    "enableOptimization": true
  },
  "logging": {
    "enableLogging": true,
    "logLevel": "info",
    "logToFile": true,
    "logToConsole": true,
    "maxLogFileSize": 10485760,
    "logRetentionDays": 7,
    "enableDebugMode": false,
    "logCategories": ["cascade", "actionphase", "performance", "workspace"]
  }
}
```

### Configuration Templates

```bash
# Apply development template
curl -X POST http://localhost:8080/config/template \
  -H "Content-Type: application/json" \
  -d '{"template": "development"}'

# Apply production template
curl -X POST http://localhost:8080/config/template \
  -H "Content-Type: application/json" \
  -d '{"template": "production"}'

# Apply minimal template
curl -X POST http://localhost:8080/config/template \
  -H "Content-Type: application/json" \
  -d '{"template": "minimal"}'
```

## 📊 Monitoring and Analytics

### Prometheus Metrics

Available metrics:
- `windsurf_cache_hit_rate` - Cache hit percentage
- `windsurf_response_time_seconds` - Response time distribution
- `windsurf_active_connections` - Active connection count
- `windsurf_plugin_count` - Number of loaded plugins
- `windsurf_error_count` - Error count by type
- `windsurf_memory_usage_bytes` - Memory usage
- `windsurf_cpu_usage_percent` - CPU usage

### Grafana Dashboards

Access Grafana at `http://localhost:3000` (default credentials: admin/admin123)

Pre-built dashboards:
- **Windsurf MCP Overview**: System health and performance
- **Cascade Analytics**: Cascade execution metrics
- **Plugin Performance**: Plugin usage and errors
- **System Resources**: Memory, CPU, and network metrics

### Health Checks

```bash
# Health check endpoint
curl http://localhost:8080/health

# Readiness check endpoint
curl http://localhost:8080/ready

# Metrics endpoint
curl http://localhost:8080/metrics

# Analytics dashboard
curl http://localhost:8080/analytics
```

### Log Management

```bash
# View logs (Docker)
docker logs windsurf-mcp

# View logs (Kubernetes)
kubectl logs -f deployment/windsurf-mcp -n windsurf

# Access log files
ls -la ~/.config/atlastrinity/logs/windsurf/
tail -f ~/.config/atlastrinity/logs/windsurf/cascade.jsonl
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Connection Failures

**Symptoms**: "Windsurf IDE not detected" errors

**Solutions**:
```bash
# Check if Windsurf is running
ps aux | grep -i windsurf

# Check port availability
netstat -an | grep :8080

# Verify API key
echo $WINDSURF_API_KEY | grep -q "^sk-ws-" && echo "API key format OK" || echo "Invalid API key format"
```

#### 2. High Memory Usage

**Symptoms**: Container crashes or OOMKilled

**Solutions**:
```bash
# Check memory usage
docker stats windsurf-mcp

# Reduce cache size
curl -X PATCH http://localhost:8080/config \
  -H "Content-Type: application/json" \
  -d '{"performance": {"cacheSize": 50}}'

# Enable memory optimization
curl -X PATCH http://localhost:8080/config \
  -H "Content-Type: application/json" \
  -d '{"performance": {"enableOptimization": true}}'
```

#### 3. Slow Response Times

**Symptoms**: Requests taking > 5 seconds

**Solutions**:
```bash
# Check performance metrics
curl http://localhost:8080/analytics

# Enable connection pooling
curl -X PATCH http://localhost:8080/config \
  -H "Content-Type: application/json" \
  -d '{"performance": {"enableConnectionPooling": true}}'

# Optimize requests
curl -X PATCH http://localhost:8080/config \
  -H "Content-Type: application/json" \
  -d '{"performance": {"enableOptimization": true}}'
```

#### 4. Plugin Errors

**Symptoms**: Plugin loading or execution failures

**Solutions**:
```bash
# Check plugin status
curl http://localhost:8080/plugins

# Reload plugins
curl -X POST http://localhost:8080/plugins/reload

# Check plugin logs
grep -i "plugin" ~/.config/atlastrinity/logs/windsurf/*.jsonl
```

### Debug Mode

```bash
# Enable debug logging
curl -X PATCH http://localhost:8080/config \
  -H "Content-Type: application/json" \
  -d '{"logging": {"enableDebugMode": true, "logLevel": "debug"}}'

# View debug logs
tail -f ~/.config/atlastrinity/logs/windsurf/cascade.jsonl | grep DEBUG
```

## ⚡ Performance Optimization

### Caching Optimization

```bash
# Optimize cache settings
curl -X PATCH http://localhost:8080/config \
  -H "Content-Type: application/json" \
  -d '{
    "performance": {
      "cacheSize": 200,
      "cacheExpiration": 600,
      "enableCaching": true
    }
  }'
```

### Connection Pooling

```bash
# Optimize connection pool
curl -X PATCH http://localhost:8080/config \
  -H "Content-Type: application/json" \
  -d '{
    "performance": {
      "maxConnections": 5,
      "enableConnectionPooling": true
    }
  }'
```

### Request Optimization

```bash
# Enable request optimization
curl -X PATCH http://localhost:8080/config \
  -H "Content-Type: application/json" \
  -d '{
    "performance": {
      "enableOptimization": true,
      "enableRequestBatching": true,
      "batchSize": 10
    }
  }'
```

### Resource Limits

```bash
# Kubernetes resource limits
kubectl patch deployment windsurf-mcp -n windsurf -p '{"spec":{"template":{"spec":{"containers":[{"name":"windsurf-mcp","resources":{"limits":{"memory":"4Gi","cpu":"3000m"}}}]}}}'
```

## 🔒 Security Considerations

### API Key Management

```bash
# Use Kubernetes secrets
kubectl create secret generic windsurf-secrets \
  --from-literal=api-key=sk-ws-your-api-key-here \
  -n windsurf

# Reference in deployment
kubectl set env deployment/windsurf-mcp WINDSURF_API_KEY \
  --from=secret/windsurf-secrets/key \
  -n windsurf
```

### Network Security

```bash
# Network policies
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: windsurf-network-policy
  namespace: windsurf
spec:
  podSelector:
    matchLabels:
      app: windsurf-mcp
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: monitoring
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: database
EOF
```

### File System Permissions

```bash
# Set appropriate permissions
chmod 755 ~/.config/atlastrinity
chmod 644 ~/.config/atlastrinity/windsurf_config.json
chmod 600 ~/.config/atlastrinity/logs/windsurf/*
```

### Container Security

```bash
# Run as non-root user
docker run --user 1000:1000 windsurf-mcp:latest

# Read-only file system where possible
docker run --read-only windsurf-mcp:latest

# Limit capabilities
docker run --cap-drop=ALL --cap-add=NET_BIND_SERVICE windsurf-mcp:latest
```

## 📈 Scaling and High Availability

### Horizontal Scaling

```bash
# Enable HPA
kubectl autoscale deployment windsurf-mcp \
  --min=2 --max=10 --cpu-percent=70 \
  --memory-percent=80 -n windsurf

# Manual scaling
kubectl scale deployment windsurf-mcp --replicas=5 -n windsurf
```

### Load Balancing

```yaml
# Ingress configuration
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: windsurf-ingress
  annotations:
    nginx.ingress.kubernetes.io/load-balance: round_robin
spec:
  rules:
  - host: windsurf-mcp.example.com
    http:
      paths:
      - backend:
          service:
            name: windsurf-mcp-service
            port:
              number: 8080
```

### Health Checks

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3
```

## 🔄 Updates and Maintenance

### Rolling Updates

```bash
# Update deployment
kubectl set image deployment/windsurf-mcp \
  windsurf-mcp=windsurf-mcp:v2.0.0 \
  -n windsurf

# Rollback if needed
kubectl rollout undo deployment/windsurf-mcp -n windsurf

# Check rollout status
kubectl rollout status deployment/windsurf-mcp -n windsurf
```

### Backup and Restore

```bash
# Backup configuration
kubectl get configmap windsurf-config -o yaml -n windsurf > backup-config.yaml

# Backup secrets
kubectl get secret windsurf-secrets -o yaml -n windsurf > backup-secrets.yaml

# Restore configuration
kubectl apply -f backup-config.yaml -n windsurf
kubectl apply -f backup-secrets.yaml -n windsurf
```

## 📞 Support and Documentation

### Getting Help

- **Documentation**: [Complete Implementation Summary](WINDSURF_MCP_COMPLETE_SUMMARY.md)
- **API Reference**: Available via `/docs` endpoint
- **Community**: GitHub Issues and Discussions
- **Support**: Contact support team for enterprise deployments

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `python3 tests/test_windsurf_mcp_comprehensive.py`
5. Submit a pull request

---

🎉 **The Windsurf MCP Provider is now production-ready with comprehensive deployment options, monitoring, and operational support!**
