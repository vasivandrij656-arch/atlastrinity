import pytest

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None
import os
import sys
from pathlib import Path

# Ensure src is in the path for CI and local tests
root_path = Path(__file__).parent.parent.absolute()
if str(root_path / "src") not in sys.path:
    sys.path.insert(0, str(root_path / "src"))
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

# Disable heavy brain components during collection if on Linux CI
if os.getenv("CI") and os.name != "nt":
    # Prevent top-level brain initialization during collection
    os.environ["ATLAS_BRAIN_SKIP_INIT"] = "true"

# Default list of MCP servers used in tests
DEFAULT_SERVERS = [
    "filesystem",
    "terminal",
    "computer-use",
    "applescript",
    "puppeteer",
    "duckduckgo-search",
    "fetch",
    "github",
    "git",
    "memory",
    "postgres",
    "whisper-stt",
    "time",
    "sequential-thinking",
    "docker",
    "devtools",
]


@pytest.fixture(scope="session")
def mcp_credentials_available():
    """Check if MCP credentials are available in environment."""
    github_token = os.getenv("MCP_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    postgres_url = os.getenv("MCP_POSTGRES_URL") or os.getenv("POSTGRES_URL")

    return {
        "github": bool(github_token),
        "postgres": bool(postgres_url),
    }


@pytest.fixture(params=DEFAULT_SERVERS)
def server_name(request):
    """Parametrized server name for MCP tests."""
    return request.param


@pytest.fixture(params=DEFAULT_SERVERS)
def name(request):
    """Alias fixture used by some tests expecting 'name'."""
    return request.param


@pytest.fixture
def test_cases(server_name):
    """Return a small set of test cases for a given server name (sane defaults)."""
    test_plan = {
        "filesystem": [
            {
                "tool": "list_directory",
                "args": {"path": "/"},
                "description": "List root",
            },
        ],
        "terminal": [
            {
                "tool": "execute_command",
                "args": {"command": "echo Test"},
                "description": "Echo command",
            },
        ],
        "memory": [
            {
                "tool": "create_entities",
                "args": {
                    "entities": [
                        {
                            "name": "test_memory",
                            "entityType": "concept",
                            "observations": ["Testing"],
                        },
                    ],
                },
                "description": "Create entities",
            },
        ],
        "devtools": [
            {
                "tool": "devtools_validate_config",
                "args": {},
                "description": "Validate MCP config",
            },
            {
                "tool": "devtools_lint_python",
                "args": {"file_path": "tests/conftest.py"},
                "description": "Lint self with ruff",
            },
        ],
    }
    return test_plan.get(server_name, [])


@pytest.fixture(params=["cpu"] + (["mps"] if (torch and torch.backends.mps.is_available()) else []))
def device_name(request):
    """Parametrize device_name for Whisper tests (cpu and mps if available)."""
    return request.param
