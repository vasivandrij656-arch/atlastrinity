"""Backward-compat shim: brain.message_bus → brain.core.server.message_bus"""

from .core.server.message_bus import *  # noqa: F401,F403
