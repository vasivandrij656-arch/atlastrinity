"""Backward-compat shim: brain.config_loader → brain.config.config_loader"""

from .config.config_loader import *  # noqa: F401,F403
