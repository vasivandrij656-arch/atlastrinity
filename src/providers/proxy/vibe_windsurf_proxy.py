#!/usr/bin/env python3
"""
VIBE Windsurf Proxy Server
==========================

Simple, stable OpenAI-compatible proxy specifically for VIBE CLI.
Converts OpenAI API calls to direct Windsurf Python API calls.

Features:
- Minimal dependencies (only requests + providers.windsurf)
- Stable error handling
- Fast response times
- VIBE-specific optimizations

Usage:
    python src/providers/proxy/vibe_windsurf_proxy.py                    # Default port 8085
    python src/providers/proxy/vibe_windsurf_proxy.py --port 8086       # Custom port

Environment:
    WINDSURF_API_KEY      - Required. Windsurf API key (sk-ws-...)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import http.server
import json
import os
import signal
import socketserver
import sys
import time

# Load environment variables from global .env
try:
    from dotenv import load_dotenv

    # Try local .env first, then global config .env
    env_paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.expanduser("~/.config/atlastrinity/.env"),
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            load_dotenv(env_path, override=True)
            break
except ImportError:
    pass  # dotenv not available, use system env vars

# Add project root and src to path for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
for path in [PROJECT_ROOT, SRC_ROOT]:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from providers.windsurf import WindsurfLLM
except ImportError as e:
    print(f"FAILED to import providers.windsurf: {e}", file=sys.stderr)
    sys.exit(1)

# ─── Configuration ─────────────────────────────────────────────────────

DEFAULT_PORT = 8085

# Load models from single source of truth: config/all_models.json
try:
    from providers.utils.model_registry import get_windsurf_models

    SUPPORTED_MODELS = get_windsurf_models()
except Exception:
    # Fallback if model_registry or all_models.json is unavailable
    SUPPORTED_MODELS = {
        "swe-1.5": "swe-1.5",
        "deepseek-v3": "deepseek-v3",
        "deepseek-r1": "deepseek-r1",
        "swe-1": "swe-1",
        "grok-code-fast-1": "grok-code-fast-1",
        "kimi-k2.5": "kimi-k2.5",
        "windsurf-fast": "windsurf-fast",
    }

# ─── Colors ────────────────────────────────────────────────────────────


class C:
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def log(msg: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"{C.DIM}[{timestamp}]{C.RESET} {msg}")


def info(msg: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"{C.DIM}[{timestamp}]{C.RESET} {C.CYAN}INFO{C.RESET}  {msg}")


def warn(msg: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"{C.DIM}[{timestamp}]{C.RESET} {C.YELLOW}WARN{C.RESET}  {msg}", file=sys.stderr)


def error(msg: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"{C.DIM}[{timestamp}]{C.RESET} {C.RED}ERROR{C.RESET} {msg}", file=sys.stderr)


# ─── Proxy Handler ─────────────────────────────────────────────────────


class VibeWindsurfProxyHandler(http.server.BaseHTTPRequestHandler):
    """Simple OpenAI-compatible proxy handler for VIBE Windsurf requests."""

    start_time: float = 0.0

    def log_message(self, format: str, *args) -> None:
        """Suppress default HTTP logging."""

    def do_GET(self) -> None:
        """Handle GET requests (models list, health check)."""
        if self.path in {"/v1/models"}:
            self.send_models_response()
        elif self.path in {"/health", "/"}:
            self.send_health_response()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        """Handle POST requests (chat completions)."""
        if self.path in {"/v1/chat/completions", "/chat/completions"}:
            self.handle_chat_completion()
        else:
            self.send_error(404, "Not Found")

    def send_models_response(self) -> None:
        """Send available models list."""
        models = []
        for model_name in SUPPORTED_MODELS:
            models.append(
                {
                    "id": model_name,
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "windsurf-free",
                }
            )

        response = {"object": "list", "data": models}

        self.send_json_response(response)

    def send_health_response(self) -> None:
        """Send health check response."""
        response = {
            "status": "healthy",
            "service": "vibe-windsurf-proxy",
            "models": list(SUPPORTED_MODELS.keys()),
            "uptime": time.time() - self.start_time,
        }
        self.send_json_response(response)

    def handle_chat_completion(self) -> None:
        """Handle chat completion request using direct Windsurf API."""
        try:
            # Parse request
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_error(400, "Empty request body")
                return

            body = self.rfile.read(content_length)
            request_data = json.loads(body.decode("utf-8"))

            # Extract parameters
            model = request_data.get("model", "swe-1.5")
            messages = request_data.get("messages", [])

            # Validate model
            if model not in SUPPORTED_MODELS:
                self.send_error_response(f"Unsupported model: {model}", 400)
                return

            # Convert messages to Windsurf format
            windsurf_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                windsurf_messages.append({"role": role, "content": content})

            # Call Windsurf directly
            # Pass proxy_url="" to prevent the WindsurfLLM instance from trying to use THIS proxy (recursion)
            # This allows it to use the Fallback Chain (Cascade -> Local -> Direct) safely.
            llm = WindsurfLLM(model_name=model, proxy_url="")

            # Make the API call with timeout
            start_time = time.time()
            response = None
            
            try:
                # Use timeout to prevent hanging
                import signal

                def timeout_handler(signum, frame):
                    raise TimeoutError("Windsurf API call timed out")

                # Set 30 second timeout
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)

                try:
                    response = llm.invoke(windsurf_messages)
                except TimeoutError as e:
                    error(f"Windsurf API timeout: {e}")
                    self.send_error_response("Windsurf API timeout after 30 seconds", 504)
                finally:
                    signal.alarm(0)  # Cancel timeout
                return
            except Exception as e:
                error(f"Windsurf API error: {e}")
                self.send_error_response(f"Windsurf API error: {e!s}", 502)
            elapsed = time.time() - start_time

            # Extract content
            if response and hasattr(response, "content"):
                content = str(response.content)
            else:
                content = str(response) if response else "Error: No response generated"

            # Create OpenAI-compatible response
            openai_response = {
                "id": f"vibe-ws-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,  # Windsurf doesn't provide token counts
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                "vibe_proxy": {"elapsed_seconds": round(elapsed, 2), "provider": "windsurf-direct"},
            }

            log(f"✅ {model} response in {elapsed:.2f}s")
            self.send_json_response(openai_response)

        except json.JSONDecodeError as e:
            error(f"JSON decode error: {e}")
            self.send_error_response("Invalid JSON in request body", 400)
        except Exception as e:
            # Check for broken pipe in generic exception as well
            if "[Errno 32] Broken pipe" in str(e) or (isinstance(e, OSError) and e.errno == 32):
                pass
            else:
                error(f"Request error: {e}")
                self.send_error_response(f"Windsurf API error: {e!s}", 500)

    def send_json_response(self, data: dict) -> None:
        """Send JSON response."""
        response_body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

        try:
            self.wfile.write(response_body)
        except BrokenPipeError:
            # Client closed connection - ignore silently
            pass

    def send_error_response(self, message: str, status_code: int = 500) -> None:
        """Send error response in OpenAI format."""
        error_data = {
            "error": {"message": message, "type": "invalid_request_error", "code": "api_error"}
        }

        response_body = json.dumps(error_data).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()

        try:
            self.wfile.write(response_body)
        except BrokenPipeError:
            # Client closed connection - ignore silently
            pass


# ─── Server Management ─────────────────────────────────────────────────


def run(port: int = DEFAULT_PORT) -> None:
    """Start the VIBE Windsurf proxy server."""

    # Check environment
    api_key = os.getenv("WINDSURF_API_KEY")
    if not api_key:
        error("WINDSURF_API_KEY environment variable not set!")
        error("Run: python -m src.providers.get_windsurf_token --key-only")
        sys.exit(1)

    # Mask key for display
    masked_key = api_key[:15] + "..." + api_key[-8:] if len(api_key) > 20 else api_key
    info(f"API Key: {masked_key}")
    info(f"Supported models: {', '.join(SUPPORTED_MODELS.keys())}")

    # Start server
    log(f"Starting VIBE Windsurf Proxy on port {port}")

    VibeWindsurfProxyHandler.start_time = time.time()
    server_address = ("127.0.0.1", port)

    # Use ThreadingTCPServer with bounded thread pool to prevent thread exhaustion
    # (RuntimeError: can't start new thread)
    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True
        _thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)

        def process_request(self, request, client_address):
            self._thread_pool.submit(self.process_request_thread, request, client_address)

    httpd = ThreadedTCPServer(server_address, VibeWindsurfProxyHandler)

    info(f"Serving at http://127.0.0.1:{port}")
    info(f"OpenAI-compatible endpoint: http://127.0.0.1:{port}/v1/chat/completions")
    info(f"Models list: http://127.0.0.1:{port}/v1/models")
    info(f"Health check: http://127.0.0.1:{port}/health")

    # Setup signal handlers
    shutting_down = False

    def shutdown_handler(signum, frame):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        log("Shutting down proxy...")
        httpd.server_close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        shutdown_handler(None, None)


# ─── Entry Point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="VIBE Windsurf OpenAI-compatible proxy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Default port 8085
  %(prog)s --port 8086               # Custom port
  %(prog)s --port 8085               # Standard VIBE port
        """,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    args = parser.parse_args()

    run(port=args.port)
