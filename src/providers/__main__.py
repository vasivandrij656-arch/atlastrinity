#!/usr/bin/env python3
"""
Provider CLI
============

Command-line interface for managing LLM providers.

Usage:
    python -m providers switch windsurf
    python -m providers switch copilot
    python -m providers status
    python -m providers test
    python -m providers quick-test
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        return

    command = sys.argv[1].lower()
    handlers = {
        "switch": _handle_switch,
        "status": _handle_status,
        "test": _handle_test,
        "quick-test": _handle_quick_test,
        "token": _handle_token,
    }

    handler = handlers.get(command)
    if handler:
        handler()


def _handle_switch():
    if len(sys.argv) < 3:
        return
    provider = sys.argv[2].lower()
    if provider in ["windsurf", "copilot"]:
        try:
            from providers.utils.switch_provider import main as switch_provider_main

            sys.argv = ["switch_provider.py", provider]
            switch_provider_main()
        except ImportError:
            pass


def _handle_status():
    try:
        from providers.utils.switch_provider import show_status

        show_status()
    except ImportError:
        pass


def _handle_test():
    try:
        from providers.tests.test_windsurf_config import test_config_integration

        test_config_integration()
    except ImportError:
        pass


def _handle_quick_test():
    try:
        from providers.tests.quick_windsurf_test import quick_test

        quick_test()
    except ImportError:
        pass


def _handle_token():
    if len(sys.argv) < 3:
        return
    token_provider = sys.argv[2].lower()
    args = sys.argv[3:]

    if token_provider == "windsurf":
        try:
            from providers.utils.get_windsurf_token import main as windsurf_token_main

            sys.argv = ["get_windsurf_token.py", *args]
            windsurf_token_main()
        except ImportError:
            pass
    elif token_provider == "copilot":
        try:
            from providers.utils.get_copilot_token import main as copilot_token_main

            sys.argv = ["get_copilot_token.py", *args]
            copilot_token_main()
        except ImportError:
            pass


if __name__ == "__main__":
    main()
