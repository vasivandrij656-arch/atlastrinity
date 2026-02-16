"""Backward-compat shim: brain.logger → brain.monitoring.logger"""

from .monitoring.logger import *  # noqa: F401,F403
