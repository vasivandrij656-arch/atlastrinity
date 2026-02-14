"""Self-Healing Subsystem for Atlas Trinity.

Provides the unified self-healing hypermodule with 4 operating modes:
- HEAL:     Reactive error fixing
- DIAGNOSE: System health diagnostics
- PREVENT:  Preventive maintenance
- IMPROVE:  Proactive code improvements

Quick start:
    from src.brain.healing import healing_hypermodule, HealingMode
    result = await healing_hypermodule.run(HealingMode.DIAGNOSE)
"""

from src.brain.healing.hypermodule import SelfHealingHypermodule, healing_hypermodule
from src.brain.healing.log_analyzer import LogAnalyzer, log_analyzer
from src.brain.healing.modes import (
    CommitTag,
    DiagnosticReport,
    HealingMode,
    HealingPriority,
    HealingResult,
    Hotspot,
    ImprovementNote,
)

__all__ = [
    "SelfHealingHypermodule",
    "healing_hypermodule",
    "LogAnalyzer",
    "log_analyzer",
    "HealingMode",
    "HealingPriority",
    "HealingResult",
    "DiagnosticReport",
    "ImprovementNote",
    "Hotspot",
    "CommitTag",
]
