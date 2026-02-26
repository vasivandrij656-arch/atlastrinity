import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import psutil  # pyre-ignore
from opentelemetry import trace  # pyre-ignore
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # pyre-ignore
from opentelemetry.sdk.resources import Resource  # pyre-ignore
from opentelemetry.sdk.trace import TracerProvider  # pyre-ignore
from opentelemetry.sdk.trace.export import BatchSpanProcessor  # pyre-ignore
from prometheus_client import Counter, Gauge, Histogram, start_http_server  # pyre-ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger(__name__)


class MonitoringSystem:
    """
    Comprehensive monitoring system.
    Provides:
    - Real-time metrics (Prometheus - embedded)
    - Tracing (OpenTelemetry)
    - Persistent Logs & Metrics (SQLite)
    """

    # Metrics collectors (declared for Pyre2)
    cpu_usage: Any
    memory_usage: Any
    disk_usage: Any
    network_bytes_sent: Any
    network_bytes_received: Any
    request_count: Any
    request_latency: Any
    active_requests: Any
    etl_records_processed: Any
    etl_errors: Any
    tracer: Any

    def __init__(
        self,
        prometheus_port: int = 8001,
        opensearch_enabled: bool = False,  # Now defaults to False, acts as "External DB" flag
        grafana_enabled: bool = True,
        config: dict[str, Any] | None = None,
    ):
        """
        Initialize the monitoring system.

        Args:
            prometheus_port: Port for Prometheus metrics server
            opensearch_enabled: (Legacy name) Enable external DB storage
            grafana_enabled: Enable structured logging
            config: Optional monitoring configuration dictionary
        """
        # Load configuration
        self.config = config or self._load_config()

        # Apply configuration
        self.prometheus_port = self.config.get("prometheus", {}).get("port", prometheus_port)
        self.storage_enabled = True  # Always enable local storage
        self.grafana_enabled = self.config.get("grafana", {}).get("enabled", grafana_enabled)
        self.opensearch_enabled = self.config.get("opensearch", {}).get(
            "enabled", opensearch_enabled
        )

        # Initialize SQLite for Logs/Metrics
        self.db_path = Path.home() / ".config" / "atlastrinity" / "data" / "monitoring.db"
        self._init_db()

        # Initialize metrics collectors
        self._initialize_metrics()

        # Initialize tracing
        self._initialize_tracing()

        # Start Prometheus server
        self._start_prometheus_server()

        logger.info(f"Monitoring system initialized - SQLite DB at {self.db_path}")

    def _init_db(self):
        """Initialize SQLite monitoring database."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                # Logs table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        level TEXT,
                        service TEXT,
                        message TEXT,
                        data JSON
                    )
                """)
                # Metrics table (Snapshots)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS metric_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        metrics JSON
                    )
                """)

                # Request Logs
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS request_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        request_type TEXT,
                        status TEXT,
                        duration REAL
                    )
                """)

                # Healing Events (Parallel Self-Healing & Constraints)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS healing_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        task_id TEXT,
                        event_type TEXT, -- 'auto_healing', 'constraint_violation'
                        step_id TEXT,
                        priority INTEGER,
                        status TEXT,
                        details JSON
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to init monitoring DB: {e}")

    def _save_to_db(self, table: str, data: dict):
        """Helper to save dict data to SQLite."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?"] * len(data))
                sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
                conn.execute(sql, list(data.values()))
                conn.commit()
        except Exception as e:
            # Don't crash app on monitoring failure
            logger.error(f"Failed to write to monitoring DB ({table}): {e}")

    def _load_config(self) -> dict[str, Any]:
        """
        Load monitoring configuration.

        Returns:
            Dictionary containing monitoring configuration
        """
        try:
            from src.brain.monitoring.monitoring_config import monitoring_config  # pyre-ignore

            return {
                "prometheus": monitoring_config.get_prometheus_config(),
                "grafana": monitoring_config.get_grafana_config(),
                "opensearch": monitoring_config.get_opensearch_config(),
                "tracing": monitoring_config.get_tracing_config(),
                "etl": monitoring_config.get_etl_config(),
            }
        except ImportError:
            logger.warning("Monitoring config not available, using defaults")
            return {}

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics collectors with safety checks for duplicate registration."""
        from prometheus_client import REGISTRY  # pyre-ignore

        def create_gauge(name, label):
            if name in REGISTRY._names_to_collectors:
                return cast("Any", REGISTRY._names_to_collectors[name])
            return Gauge(name, label)

        def create_counter(name, label, labels=None):
            if name in REGISTRY._names_to_collectors:
                return cast("Any", REGISTRY._names_to_collectors[name])
            return Counter(name, label, labels or [])

        def create_histogram(name, label, labels=None):
            if name in REGISTRY._names_to_collectors:
                return cast("Any", REGISTRY._names_to_collectors[name])
            return Histogram(name, label, labels or [])

        # System metrics
        self.cpu_usage = create_gauge(
            "atlastrinity_cpu_usage_percent", "Current CPU usage percentage"
        )
        self.memory_usage = create_gauge(
            "atlastrinity_memory_usage_bytes", "Current memory usage in bytes"
        )
        self.disk_usage = create_gauge(
            "atlastrinity_disk_usage_bytes", "Current disk usage in bytes"
        )

        # Network metrics
        self.network_bytes_sent = create_counter(
            "atlastrinity_network_bytes_sent", "Total bytes sent"
        )
        self.network_bytes_received = create_counter(
            "atlastrinity_network_bytes_received", "Total bytes received"
        )

        # Application metrics
        self.request_count = create_counter(
            "atlastrinity_requests_total",
            "Total number of requests processed",
            ["request_type", "status"],
        )
        self.request_latency = create_histogram(
            "atlastrinity_request_latency_seconds",
            "Request processing latency in seconds",
            ["request_type"],
        )
        self.active_requests = create_gauge(
            "atlastrinity_active_requests", "Number of active requests"
        )

        # ETL pipeline metrics
        self.etl_records_processed = create_counter(
            "atlastrinity_etl_records_processed",
            "Number of records processed by ETL",
            ["pipeline_stage"],
        )
        self.etl_errors = create_counter(
            "atlastrinity_etl_errors",
            "Number of ETL processing errors",
            ["pipeline_stage", "error_type"],
        )

    def _initialize_tracing(self) -> None:
        """Initialize OpenTelemetry tracing."""
        try:
            # Set up resource with service name
            resource = Resource.create({"service.name": "atlastrinity", "service.version": "1.0.0"})

            # Create tracer provider
            tracer_provider = TracerProvider(resource=resource)

            # Set up span processor with OTLP exporter
            otlp_exporter = OTLPSpanExporter()
            span_processor = BatchSpanProcessor(otlp_exporter)
            tracer_provider.add_span_processor(span_processor)

            # Set as global tracer provider
            trace.set_tracer_provider(tracer_provider)

            self.tracer = trace.get_tracer(__name__)
            logger.info("OpenTelemetry tracing initialized")

        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry tracing: {e}")
            self.tracer = cast("Any", None)

    def _start_prometheus_server(self) -> None:
        """Start Prometheus metrics server with port fallback."""
        start_port = self.prometheus_port
        for port_offset in range(10):  # Try 10 consecutive ports
            current_port = start_port + port_offset
            try:
                start_http_server(current_port)
                self.prometheus_port = current_port
                logger.info(f"Prometheus metrics server started on port {current_port}")
                return
            except OSError as e:
                if e.errno == 48:  # Address already in use
                    logger.debug(f"Prometheus port {current_port} is busy. Trying next...")
                    continue
                logger.error(f"Failed to start Prometheus server on port {current_port}: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error starting Prometheus server: {e}")
                break
        logger.warning(
            "Could not start Prometheus server after 10 attempts. Metrics delivery via port will be unavailable."
        )

    def collect_system_metrics(self) -> dict[str, Any]:
        """
        Collect system-level metrics.

        Returns:
            Dictionary containing system metrics
        """
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=None)
            self.cpu_usage.set(cpu_percent)

            # Memory metrics
            mem = psutil.virtual_memory()
            self.memory_usage.set(mem.used)

            # Disk metrics
            disk = psutil.disk_usage("/")
            self.disk_usage.set(disk.used)

            # Network metrics
            net_io = psutil.net_io_counters()
            self.network_bytes_sent.inc(net_io.bytes_sent)
            self.network_bytes_received.inc(net_io.bytes_recv)

            metrics = {
                "cpu_usage_percent": cpu_percent,
                "memory_used_bytes": mem.used,
                "memory_total_bytes": mem.total,
                "disk_used_bytes": disk.used,
                "disk_total_bytes": disk.total,
                "network_bytes_sent": net_io.bytes_sent,
                "network_bytes_received": net_io.bytes_recv,
                "timestamp": datetime.now().isoformat(),
            }

            # Save snapshot to SQLite
            self._save_to_db(
                "metric_snapshots",
                {"timestamp": metrics["timestamp"], "metrics": json.dumps(metrics)},
            )

            return metrics

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return {}

    def record_request(self, request_type: str, status: str, duration: float) -> None:
        """
        Record an application request.

        Args:
            request_type: Type of request (e.g., 'chat', 'stt', 'etl')
            status: Status of request (e.g., 'success', 'error')
            duration: Duration in seconds
        """
        try:
            self.request_count.labels(request_type=request_type, status=status).inc()
            self.request_latency.labels(request_type=request_type).observe(duration)

            self._save_to_db(
                "request_logs",
                {
                    "timestamp": datetime.now().isoformat(),
                    "request_type": request_type,
                    "status": status,
                    "duration": duration,
                },
            )

            logger.info(
                f"Recorded {request_type} request: status={status}, duration={duration:.2f}s"
            )
        except Exception as e:
            logger.error(f"Error recording request metrics: {e}")

    def record_etl_metrics(
        self, stage: str, records_processed: int, errors: int = 0, error_type: str = "none"
    ) -> None:
        """
        Record ETL pipeline metrics.

        Args:
            stage: ETL stage (e.g., 'scraping', 'transformation', 'distribution')
            records_processed: Number of records processed
            errors: Number of errors encountered
            error_type: Type of error if any
        """
        try:
            self.etl_records_processed.labels(pipeline_stage=stage).inc(records_processed)
            if errors > 0:
                self.etl_errors.labels(pipeline_stage=stage, error_type=error_type).inc(errors)

            logger.info(
                f"ETL metrics recorded: stage={stage}, records={records_processed}, errors={errors}"
            )
        except Exception as e:
            logger.error(f"Error recording ETL metrics: {e}")

    def record_healing_event(
        self,
        task_id: str,
        event_type: str,
        step_id: str,
        priority: int,
        status: str,
        details: dict[str, Any],
    ) -> None:
        """
        Record a self-healing or constraint violation event.

        Args:
            task_id: Unique task ID
            event_type: 'auto_healing' or 'constraint_violation'
            step_id: ID of the step where it happened
            priority: 1 (Standard) or 2 (High/Constraint)
            status: Current status (started, fixed, failed)
            details: Additional context (error, fix description, etc.)
        """
        try:
            self._save_to_db(
                "healing_events",
                {
                    "timestamp": datetime.now().isoformat(),
                    "task_id": task_id,
                    "event_type": event_type,
                    "step_id": step_id,
                    "priority": priority,
                    "status": status,
                    "details": json.dumps(details, ensure_ascii=False),
                },
            )

            # Also log as a metric
            self.etl_errors.labels(pipeline_stage="self_healing", error_type=event_type).inc()

            logger.info(f"Healing event recorded: {event_type} for {step_id} (Status: {status})")

        except Exception as e:
            logger.error(f"Error recording healing event: {e}")

    def record_opensearch_metrics(self, query_type: str, documents: int = 0) -> None:
        """
        Record Search-related metrics (Legacy Name).

        Args:
            query_type: Type of search operation
            documents: Number of documents involved
        """
        # Kept for compatibility, logs to stdout mainly
        logger.info(f"Search metrics recorded: query_type={query_type}, documents={documents}")

    def start_request(self) -> None:
        """Increment active request counter."""
        self.active_requests.inc()

    def end_request(self) -> None:
        """Decrement active request counter."""
        self.active_requests.dec()

    def get_metrics_snapshot(self) -> dict[str, Any]:
        """
        Get a snapshot of current metrics.

        Returns:
            Dictionary containing current metrics values
        """
        try:
            return {
                "system": self.collect_system_metrics(),
                "application": {
                    "active_requests": int(self.active_requests._value.get()),
                    "timestamp": datetime.now().isoformat(),
                },
            }
        except Exception as e:
            logger.error(f"Error getting metrics snapshot: {e}")
            return {}

    def log_for_grafana(self, message: str, level: str = "info", **kwargs) -> None:
        """
        Log message in structured format.

        Args:
            message: Log message
            level: Log level (info, warning, error, debug)
            kwargs: Additional context data
        """
        try:
            timestamp = datetime.now().isoformat()

            # Save to SQLite
            self._save_to_db(
                "logs",
                {
                    "timestamp": timestamp,
                    "level": level,
                    "service": "atlastrinity",
                    "message": message,
                    "data": json.dumps(kwargs, ensure_ascii=False),
                },
            )

            # Stdout logging
            log_entry = {
                "timestamp": timestamp,
                "level": level,
                "message": message,
                "service": "atlastrinity",
                **kwargs,
            }
            log_json = json.dumps(log_entry, ensure_ascii=False)

            if level == "error":
                logger.error(log_json)
            elif level == "warning":
                logger.warning(log_json)
            elif level == "debug":
                logger.debug(log_json)
            else:
                logger.info(log_json)

        except Exception as e:
            logger.error(f"Error logging: {e}")

    def create_span(self, name: str, **kwargs) -> Any:
        """
        Create a tracing span for distributed tracing.

        Args:
            name: Span name
            kwargs: Additional span attributes

        Returns:
            Tracing span object or None if tracing is disabled
        """
        if not self.tracer:
            return None

        try:
            return self.tracer.start_span(name, **kwargs)
        except Exception as e:
            logger.error(f"Error creating tracing span: {e}")
            return None

    def is_healthy(self) -> bool:
        """
        Check if monitoring system is healthy.

        Returns:
            True if monitoring system is operational, False otherwise
        """
        try:
            # Check if we can write to DB
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False


# Global monitoring instance - use lazy initialization to avoid duplicate metric registration
monitoring_system = None


def get_monitoring_system():
    """Get the global monitoring system instance (singleton pattern)."""
    global monitoring_system
    if monitoring_system is None:
        monitoring_system = MonitoringSystem()
    return monitoring_system
