"""Backward-compat shim: brain.tool_dispatcher → brain.core.orchestration.tool_dispatcher"""

from .core.orchestration.tool_dispatcher import *  # noqa: F401,F403
