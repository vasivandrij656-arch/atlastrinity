"""AtlasTrinity Error Router

Intelligent error classification and recovery routing system.
Acts as the 'Triaging Doctor' for exceptions during task execution.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from src.brain.monitoring.logger import logger  # pyre-ignore


class ErrorCategory(Enum):
    """Categories of errors requiring distinct recovery strategies"""

    TRANSIENT = "transient"  # Network blips, timeouts (Retry)
    INFRASTRUCTURE = "infrastructure"  # API rate limits, service unavailability (Wait and Retry)
    LOGIC = "logic"  # Code bugs, syntax errors (Vibe Fix)
    STATE = "state"  # Corrupted session/environment (Restart)
    PERMISSION = "permission"  # Access denied (Ask User/Atlas)
    USER_INPUT = "user_input"  # Missing info (Ask User)
    VERIFICATION = "verification"  # Grisha's verification logic failed (Immediate escalation)
    LOOP = "loop"  # Detected repetitive cycles
    CI_FAILURE = "ci_failure"  # GitHub Actions or local CI failure
    UNKNOWN = "unknown"  # Unclassified (Default fallback)


@dataclass
class RecoveryStrategy:
    """Action plan for recovering from an error"""

    action: str  # RETRY, VIBE_HEAL, RESTART, ASK_USER
    backoff: float = 0.0
    max_retries: int = 3
    context_needed: bool = False  # Does Vibe need logs/context?
    reason: str = ""


class SmartErrorRouter:
    """Routes exceptions to the optimal recovery strategy"""

    # Transient: simple retries usually fix these
    TRANSIENT_PATTERNS = [
        r"connection\s+(refused|reset|timeout)",
        r"timeout",
        r"broken\s+pipe",
        r"network\s+error",
        r"socket\s+error",
        r"temporary\s+failure",
    ]

    # Infrastructure: API limits, service issues (requires longer wait)
    INFRASTRUCTURE_PATTERNS = [
        r"rate\s+limit\s+exceeded",
        r"mistral\s+api\s+rate\s+limit",
        r"error_type.*RATE_LIMIT",
        r"api\s+quota\s+exceeded",
        r"too\s+many\s+requests",
        r"429\s+too\s+many\s+requests",
        r"503\s+service\s+unavailable",
        r"502\s+bad\s+gateway",
        r"api\s+is\s+unreachable",
    ]

    # Logic: requires code modification (Vibe)
    LOGIC_PATTERNS = [
        r"syntax\s*error",
        r"name\s*error",
        r"type\s*error",
        r"attribute\s*error",
        r"key\s*error",
        r"index\s*error",
        r"value\s*error",
        r"assertion\s*error",
        r"import\s*error",
        r"module\s*not\s*found",
        r"indentation\s*error",
        r"unbound\s*local\s*error",
    ]

    # State: requires system restart/reload
    STATE_PATTERNS = [
        r"corrupted\s+state",
        r"session\s+expired",
        r"invalid\s+token",
        r"database\s+locked",
        r"deadlock",
        r"stale\s+file\s+handle",
        r"transport\s+endpoint\s+is\s+not\s+connected",
    ]

    # Permission: requires intervention
    PERMISSION_PATTERNS = [
        r"permission\s+denied",
        r"access\s+denied",
        r"401\s+unauthorized",
        r"403\s+forbidden",
    ]

    # User Input: missing information or permission needed
    USER_INPUT_PATTERNS = [
        r"need_user_input",
        r"help_pending",
        r"user_input_received",
        r"missing\s+information",
        r"missing\s+data",
        r"please\s+provide",
    ]

    # Verification: Grisha's verification system detected issues
    VERIFICATION_PATTERNS = [
        r"grisha\s+rejected",
        r"auto-verdict\s+after",
        r"verification.*failed",
        r"max\s+attempts\s+reached.*verification",
        r"0/\d+\s+successful",
        r"recursion\s+detected",
        r"recursion\s+loop",
    ]

    # CI Failures: GitHub Actions or local CI pipeline issues
    CI_PATTERNS = [
        r"workflow\s+failed",
        r"action\s+failed",
        r"ci\s+pipeline\s+error",
        r"github\s+actions\s+failure",
        r"check_run\s+failure",
        r"script\s+not\s+found\s+in\s+ci",
    ]
    LOOP_THRESHOLDS = {
        ErrorCategory.VERIFICATION: 6,
        ErrorCategory.INFRASTRUCTURE: 5,
        ErrorCategory.TRANSIENT: 5,
        ErrorCategory.LOGIC: 3,
        ErrorCategory.STATE: 3,
        ErrorCategory.CI_FAILURE: 3,
    }
    DEFAULT_LOOP_THRESHOLD = 4

    def __init__(self):
        self._cache = {}
        self._category_history: list[ErrorCategory] = []
        self._max_history = 10

    def classify(self, error: str) -> ErrorCategory:
        """Classifies an error string into a category"""
        error_str = str(error).lower()
        if error_str in self._cache:
            return cast("ErrorCategory", self._cache[error_str])

        if error_str in ["help_pending", "need_user_input", "user_input_received"]:
            category = ErrorCategory.USER_INPUT
        elif any(re.search(p, error_str) for p in self.INFRASTRUCTURE_PATTERNS):
            category = ErrorCategory.INFRASTRUCTURE
        elif any(re.search(p, error_str) for p in self.VERIFICATION_PATTERNS):
            category = ErrorCategory.VERIFICATION
        elif any(re.search(p, error_str) for p in self.TRANSIENT_PATTERNS):
            category = ErrorCategory.TRANSIENT
        elif any(re.search(p, error_str) for p in self.LOGIC_PATTERNS):
            category = ErrorCategory.LOGIC
        elif any(re.search(p, error_str) for p in self.STATE_PATTERNS):
            category = ErrorCategory.STATE
        elif any(re.search(p, error_str) for p in self.CI_PATTERNS):
            category = ErrorCategory.CI_FAILURE
        elif any(re.search(p, error_str) for p in self.PERMISSION_PATTERNS):
            category = ErrorCategory.PERMISSION
        elif any(re.search(p, error_str) for p in self.USER_INPUT_PATTERNS):
            category = ErrorCategory.USER_INPUT
        else:
            category = ErrorCategory.UNKNOWN

        logger.debug(f"[ROUTER] Classified '{error_str[:50]}' as {category.value}")  # pyre-ignore
        self._cache[error_str] = category
        return category

    def decide(
        self, error: Any, attempt: int = 1, context: dict[str, Any] | None = None
    ) -> RecoveryStrategy:
        """Decides the recovery strategy based on error and attempt count.

        Args:
            error: The exception or error string
            attempt: Current attempt number (1-based)
            context: Optional context dictionary for pattern matching
        """
        error_str = str(error)

        # 1. Try Config-Driven Pattern Matching first
        try:
            from src.brain.behavior.behavior_engine import behavior_engine  # pyre-ignore

            # Build match context
            match_ctx = context or {}
            match_ctx["error"] = error_str
            match_ctx["attempt"] = attempt
            match_ctx["error_contains"] = error_str  # Special key for flexible matching

            pattern = behavior_engine.match_pattern(match_ctx, "adaptive_behavior")

            if pattern:
                action_cfg = pattern.action

                # Map config action to RecoveryStrategy
                # Default to VIBE_HEAL if not specified but looks proactive
                strategy_action = action_cfg.get("strategy_action")

                if not strategy_action:
                    # Heuristic mapping based on config fields
                    if action_cfg.get("server") == "vibe":
                        strategy_action = "VIBE_HEAL"
                    elif action_cfg.get("fallback_strategy") == "browser_automation":
                        # Special case for web fallback - mapping to RETRY for now as Orchestrator
                        # doesn't handle tool switching natively yet.
                        # Future: Implement CHANGE_TOOL strategy.
                        strategy_action = "RETRY"
                    elif action_cfg.get("retry_with_sudo"):
                        strategy_action = "ASK_USER"  # Sudo requires user permissions usually

                if strategy_action:
                    return RecoveryStrategy(
                        action=strategy_action,
                        backoff=float(action_cfg.get("backoff", 0.0)),
                        max_retries=int(action_cfg.get("max_retries", 2)),
                        context_needed=action_cfg.get("context_needed", True),
                        reason=f"Matched adaptive pattern: {pattern.name}",
                    )
        except ImportError:
            pass  # Fallback to hardcoded logic if engine not available
        except Exception as e:
            logger.warning(f"[ROUTER] Pattern matching failed: {e}")

        # 2. Hardcoded Logic (Fallback)
        category = self.classify(error_str)

        # Track history for loop detection
        self._category_history.append(category)
        if len(self._category_history) > self._max_history:
            self._category_history.pop(0)

        # Detect Loop: Same category repeated > threshold times recently
        threshold = self.LOOP_THRESHOLDS.get(category, self.DEFAULT_LOOP_THRESHOLD)
        if len(self._category_history) >= threshold and all(
            c == category for c in self._category_history[-threshold:]
        ):
            if category not in [ErrorCategory.USER_INPUT, ErrorCategory.PERMISSION]:
                logger.warning(
                    f"[ROUTER] 🔁 Loop detected for category {category.value} (Threshold: {threshold}). Forcing RESTART strategy."
                )
                return RecoveryStrategy(
                    action="RESTART",
                    reason=f"Repetitive {category.value} errors detected (Loop Pattern). Triggering system-level recovery.",
                )

        logger.info(f"[ROUTER] Error classified as: {category.value} (Attempt {attempt})")

        if category == ErrorCategory.INFRASTRUCTURE:
            # Infrastructure issues: wait longer, don't involve Vibe/Grisha
            # These are external service issues, not code problems
            if attempt <= 3:
                return RecoveryStrategy(
                    action="WAIT_AND_RETRY",
                    backoff=60.0 * attempt,  # 60s, 120s, 180s
                    max_retries=3,
                    reason=f"API rate limit or service unavailability detected. Waiting {60 * attempt}s before retry.",
                )
            # After 3 attempts, escalate to Atlas for a deeper infrastructure diagnostic
            return RecoveryStrategy(
                action="ATLAS_PLAN",
                context_needed=True,
                reason="Persistent API rate limiting or service issue. Requesting Atlas to optimize request pattern or find alternative provider.",
            )

        if category == ErrorCategory.TRANSIENT:
            # Patient Retry
            backoff = 2.0 * attempt
            return RecoveryStrategy(
                action="RETRY",
                backoff=backoff,
                max_retries=5,
                reason="Transient network/system issue. Retrying with backoff.",
            )

        if category == ErrorCategory.LOGIC:
            # Fast Fail -> Self-Healing Protocol
            # We skip simple retries for logic errors because re-running buggy code won't fix it
            return RecoveryStrategy(
                # FIX: Orchestrator expects VIBE_HEAL, not SELF_HEALING
                action="VIBE_HEAL",
                backoff=0.0,
                max_retries=2,  # Give Vibe 2 shots using Reflection
                context_needed=True,
                reason="Logic error detected. Initiating Self-Healing Protocol (Analyze -> Sandbox -> Fix).",
            )

        if category == ErrorCategory.STATE:
            # Immediate Restart with State Preservation
            # FIX: Orchestrator expects RESTART usually, or we define SELF_HEALING_RESTART handling?
            # Orchestrator handles RESTART. SELF_HEALING_RESTART is undefined in orchestrator.
            return RecoveryStrategy(
                action="RESTART",
                reason="System state corruption detected. Initiating Phoenix Protocol (Snapshot -> Restart -> Resume).",
            )

        if category == ErrorCategory.PERMISSION:
            return RecoveryStrategy(
                action="ATLAS_PLAN",
                context_needed=True,
                reason="Permission denied. Escalate to Atlas for reconnaissance or credential verification.",
            )

        if category == ErrorCategory.USER_INPUT:
            # If we are stuck on help_pending/need_user_input, trigger strategic discovery
            # FIX: If we have tried multiple times and still need user input, stop spinning and ASK.
            if attempt > 3:
                return RecoveryStrategy(
                    action="ASK_USER",
                    reason="Repeated requests for user input/assistance. Stopping recursion to request manual intervention.",
                )

            return RecoveryStrategy(
                action="ATLAS_PLAN",
                context_needed=True,
                reason="Missing information or assistance required. Atlas will now trigger a discovery substep to find the required data autonomously.",
            )

        if category == ErrorCategory.VERIFICATION:
            # ENHANCED: Distinguish between legitimate step failure vs verification system bug
            error_str = str(error).lower()

            # CRITICAL: Check for Grisha recursion detection
            # If Grisha already detected recursion, DON'T trigger ATLAS_PLAN (would create infinite loop)
            recursion_indicators = [
                "recursion detected",
                "recursion loop detected",
                "same rejection repeated",
                "manual intervention required",
                "identical reasoning",
            ]

            is_recursion = any(indicator in error_str for indicator in recursion_indicators)

            if is_recursion:
                # Grisha detected recursion - escalate to user, NOT Atlas
                logger.warning(
                    "[ROUTER] Grisha recursion detected. Escalating to user instead of ATLAS_PLAN."
                )
                return RecoveryStrategy(
                    action="ASK_USER",
                    reason="Grisha detected a recursion loop (same rejection repeated multiple times). Manual intervention required to break the cycle.",
                )

            # Legitimate step failures (NOT verification system bugs):
            legitimate_failure_indicators = [
                "empty results detected",
                "verification criteria not met",
                "no design files found",
                "artifact not found",
                "expected result not achieved",
                "tool execution found but result empty",
                "insufficient evidence",
                "missing evidence",
                "no confirmation",
                "command output does not show",
            ]

            # True verification system bugs (require Atlas diagnostic):
            system_bug_indicators = [
                "grisha crashed",
                "verification logic error",
                "sequential thinking failed",
                "tool routing loop",
                "infinite verification recursion",
                "verification timeout after",
                "grisha exception",
                "verification system failure",
            ]

            # Check if this is a legitimate failure (step didn't produce expected result)
            is_legitimate_failure = any(
                indicator in error_str for indicator in legitimate_failure_indicators
            )
            is_system_bug = any(indicator in error_str for indicator in system_bug_indicators)

            if is_legitimate_failure and not is_system_bug:
                # This is a REAL step failure, not a verification bug
                # Let Tetyana retry with adjustments (NOT ATLAS_PLAN)
                logger.info("[ROUTER] Detected legitimate step failure (not verification bug)")
                return RecoveryStrategy(
                    action="RETRY",
                    backoff=2.0,
                    max_retries=2,
                    reason="Step verification failed due to missing expected results. Retrying with adjusted approach.",
                )
            if is_system_bug:
                # True verification system failure - escalate to Atlas
                logger.warning("[ROUTER] Verification system bug detected - escalating to Atlas")
                return RecoveryStrategy(
                    action="ATLAS_PLAN",
                    context_needed=True,
                    reason="Verification system failure detected. This indicates issues with Grisha's error detection logic, not the task itself. Escalating for diagnostic review.",
                )
            # Ambiguous case - use RETRY first, then escalate if persistent
            if attempt <= 1:
                logger.info(
                    "[ROUTER] Ambiguous verification failure - trying RETRY before escalation"
                )
                return RecoveryStrategy(
                    action="RETRY",
                    backoff=3.0,
                    max_retries=2,
                    reason="Verification failed. Retrying with modified approach before escalating.",
                )
            # After retry, escalate to Atlas
            logger.info(
                "[ROUTER] Persistent verification failure after retry - escalating to Atlas"
            )
            return RecoveryStrategy(
                action="ATLAS_PLAN",
                context_needed=True,
                reason="Persistent verification failure. Escalating to Atlas for strategic re-planning.",
            )

        if category == ErrorCategory.CI_FAILURE:
            # CI Failure: Automatically trigger SystemFixer or VIBE_HEAL
            return RecoveryStrategy(
                action="VIBE_HEAL",
                context_needed=True,
                reason="CI/CD failure detected. Automatically initiating repair cycle via Self-Healing Protocol.",
            )

        # Unknown / Default Fallback
        if attempt <= 2:
            return RecoveryStrategy(
                action="RETRY", backoff=1.0, reason="Unknown error. Trying again."
            )
        # Persistent unknown error: extreme autonomy mode triggers strategic planning
        return RecoveryStrategy(
            action="ATLAS_PLAN",
            context_needed=True,
            reason="Persistent unknown error. Escalating for strategic re-evaluation and discovery.",
        )


# Global Instance
error_router = SmartErrorRouter()
