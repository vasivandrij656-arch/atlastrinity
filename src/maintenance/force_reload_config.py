"""
Force reload AtlasTrinity configuration
"""

import importlib
import os
import sys


def force_reload_config():
    """Force reload configuration"""

    # Add project root to path
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    # Clear config cache (Both Style A and shim)
    sys.modules.pop("src.brain.config_loader", None)
    sys.modules.pop("brain.config_loader", None)

    # Reload modules
    from src.brain.config_loader import config

    importlib.reload(sys.modules["src.brain.config_loader"])

    # Check config
    tool_routing = config.get("tool_routing", {})

    if "macos_use" in tool_routing:
        tool_routing["macos_use"]
        return True
    return False


if __name__ == "__main__":
    force_reload_config()
