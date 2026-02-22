"""Proactive Improvement Engine for Self-Healing System.

Reads improvement notes from the LogAnalyzer, identifies code hotspots,
and applies fixes via Vibe. All changes are auto-committed with [Self-Healing] tags.
"""

import logging

from src.brain.healing.modes import (
    CommitTag,
    HealingMode,
    HealingPriority,
    HealingResult,
    Hotspot,
    ImprovementNote,
)

logger = logging.getLogger("brain.healing.improvement_engine")


class ImprovementEngine:
    """Finds and applies code improvements proactively.

    Workflow:
    1. Read pending improvement notes from LogAnalyzer
    2. Group and prioritize into hotspots
    3. For each hotspot: generate fix via Vibe → lint → test → commit
    4. Mark notes as addressed
    """

    def __init__(self):
        self._max_per_cycle = 3
        self._require_lint = True
        self._require_tests = True

    def find_hotspots(self, notes: list[ImprovementNote]) -> list[Hotspot]:
        """Analyze improvement notes to find code hotspots.

        Groups notes by source file and creates Hotspot objects.

        Returns:
            List of Hotspot objects, sorted by priority.
        """
        # Group by source file
        by_file: dict[str, list[ImprovementNote]] = {}
        general: list[ImprovementNote] = []

        for note in notes:
            if note.addressed:
                continue
            if note.source_file:
                by_file.setdefault(note.source_file, []).append(note)
            else:
                general.append(note)

        hotspots: list[Hotspot] = []

        # File-based hotspots
        for file_path, file_notes in by_file.items():
            # Determine most severe priority
            worst_priority = min(n.severity.value for n in file_notes)
            total_occurrences = sum(n.occurrences for n in file_notes)

            # Determine category from most common note category
            categories = [n.category for n in file_notes]
            most_common_cat = max(set(categories), key=categories.count)
            category_map = {
                "error_pattern": "error_handling",
                "slow_operation": "performance",
                "repeated_warning": "code_quality",
                "resource_bottleneck": "performance",
                "ci_failure": "code_quality",
                "workflow_error": "config",
            }

            description = (
                f"{len(file_notes)} issues ({total_occurrences} total occurrences): "
                + "; ".join(n.description[:60] for n in file_notes[:3])
            )

            hotspots.append(
                Hotspot(
                    file_path=file_path,
                    description=description,
                    priority=HealingPriority(worst_priority),
                    category=category_map.get(most_common_cat, "code_quality"),
                    related_notes=[n.id for n in file_notes],
                )
            )

        # General (no file) hotspots
        for note in general[:5]:  # Limit general notes
            hotspots.append(
                Hotspot(
                    file_path="system",
                    description=note.description,
                    priority=note.severity,
                    category="code_quality",
                    related_notes=[note.id],
                )
            )

        # Sort by priority (lower value = higher priority)
        return sorted(hotspots, key=lambda h: h.priority.value)

    async def apply_improvement(self, hotspot: Hotspot) -> HealingResult:
        """Apply a single improvement via Vibe.

        Steps:
        1. Build context prompt from hotspot
        2. Call Vibe to generate fix
        3. Run linting verification
        4. Run test verification (if enabled)

        Returns:
            HealingResult with success status.
        """
        logger.info(
            f"[ImprovementEngine] Applying improvement to {hotspot.file_path}: {hotspot.description[:80]}"
        )

        try:
            from src.brain.mcp.mcp_manager import mcp_manager

            max_retries = 3
            prompt = self._build_improvement_prompt(hotspot)

            for attempt in range(max_retries):
                logger.info(f"[ImprovementEngine] Attempt {attempt + 1}/{max_retries} for {hotspot.file_path}")
                
                # Call Vibe for the fix
                vibe_result = await mcp_manager.call_tool(
                    "vibe",
                    "vibe_prompt",
                    {
                        "prompt": prompt,
                        "auto_approve": True,
                    },
                )

                if not vibe_result:
                    return HealingResult(
                        mode=HealingMode.IMPROVE,
                        success=False,
                        message=f"Vibe returned empty result for {hotspot.file_path}",
                    )

                # Run lint verification
                if self._require_lint:
                    lint_result = await mcp_manager.call_tool(
                        "devtools", "devtools_run_global_lint", {}
                    )
                    lint_ok = isinstance(lint_result, dict) and lint_result.get("overall_status") in (
                        "clean",
                        "pass",
                        True,
                    )
                    if not lint_ok:
                        logger.warning(
                            f"[ImprovementEngine] Lint failed on attempt {attempt + 1}: {lint_result}"
                        )
                        if attempt < max_retries - 1:
                            # Feed the lint error back to Vibe
                            lint_errors_str = str(lint_result.get("errors", lint_result))[:1000]
                            prompt += f"\n\n--- PREVIOUS ATTEMPT FAILED ---\nLinting failed with the following errors:\n{lint_errors_str}\n\nPlease fix these errors and try again. Make sure your changes are syntactically valid."
                            continue
                        else:
                            return HealingResult(
                                mode=HealingMode.IMPROVE,
                                success=False,
                                message=f"Lint failed after {max_retries} attempts applying improvement to {hotspot.file_path}",
                                details={"lint_result": str(lint_result)[:200]},
                            )
                
                # If we get here, it succeeded
                logger.info(f"[ImprovementEngine] Successfully improved {hotspot.file_path}")
                return HealingResult(
                    mode=HealingMode.IMPROVE,
                    success=True,
                    message=f"Improvement applied to {hotspot.file_path}: {hotspot.category} (after {attempt + 1} attempts)",
                    details={"hotspot": hotspot.to_dict()},
                )

        except Exception as e:
            logger.error(f"[ImprovementEngine] Failed to apply improvement: {e}")
            return HealingResult(
                mode=HealingMode.IMPROVE,
                success=False,
                message=f"Improvement failed: {e}",
            )

        return HealingResult(
            mode=HealingMode.IMPROVE,
            success=False,
            message="Improvement failed: reached end of function"
        )

    async def run_improvement_cycle(
        self,
        notes: list[ImprovementNote],
        max_improvements: int | None = None,
    ) -> list[HealingResult]:
        """Run a full improvement cycle.

        1. Find hotspots from notes
        2. Apply fixes (up to max_improvements)
        3. Commit successful changes
        4. Return results

        Args:
            notes: List of ImprovementNote objects to process.
            max_improvements: Override max improvements per cycle.

        Returns:
            List of HealingResult for each attempted improvement.
        """
        max_count = max_improvements or self._max_per_cycle
        hotspots = self.find_hotspots(notes)

        if not hotspots:
            logger.info("[ImprovementEngine] No hotspots found, nothing to improve")
            return []

        logger.info(
            f"[ImprovementEngine] Found {len(hotspots)} hotspots, applying up to {max_count}"
        )

        results: list[HealingResult] = []
        successful_files: list[str] = []

        for hotspot in hotspots[:max_count]:
            result = await self.apply_improvement(hotspot)
            results.append(result)

            if result.success and hotspot.file_path != "system":
                successful_files.append(hotspot.file_path)

        # Auto-commit if there were successful improvements
        if successful_files:
            from src.brain.healing.ci_bridge import ci_bridge

            descriptions = [r.message for r in results if r.success]
            commit_msg = f"Proactive improvements: {'; '.join(descriptions[:3])}"
            commit_hash = ci_bridge.commit_and_push(
                commit_msg,
                files=successful_files,
                tag=CommitTag.IMPROVEMENT,
            )
            if commit_hash:
                for r in results:
                    if r.success:
                        r.committed = True
                        r.commit_hash = commit_hash

        return results

    # --- Private helpers ---

    def _build_improvement_prompt(self, hotspot: Hotspot) -> str:
        """Build a Vibe prompt for applying an improvement."""
        parts = [
            f"PROACTIVE IMPROVEMENT REQUEST (Category: {hotspot.category})",
            f"Target: {hotspot.file_path}",
            f"Issue: {hotspot.description}",
            "",
            "Instructions:",
        ]

        if hotspot.category == "error_handling":
            parts.append("- Add or improve error handling for the identified patterns")
            parts.append("- Ensure exceptions are caught and logged properly")
            parts.append("- Add fallback behavior where appropriate")
        elif hotspot.category == "performance":
            parts.append("- Optimize the identified slow operations")
            parts.append("- Consider caching, connection pooling, or async optimization")
            parts.append("- Avoid breaking existing functionality")
        elif hotspot.category == "code_quality":
            parts.append("- Improve code quality: add type hints, docstrings, logging")
            parts.append("- Fix any linting issues")
            parts.append("- Follow existing code style patterns in the project")
        elif hotspot.category == "security":
            parts.append("- Fix security vulnerabilities")
            parts.append("- Sanitize inputs, validate data, use secure defaults")

        if hotspot.suggested_fix:
            parts.append(f"\nSuggested approach: {hotspot.suggested_fix}")

        parts.append("\nIMPORTANT: Make minimal, safe changes. Do NOT break existing tests.")
        return "\n".join(parts)


# Singleton
improvement_engine = ImprovementEngine()
