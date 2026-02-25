"""Unit tests for Grisha's Discovery Resilience (Positive Negative Discovery)."""

import os
import sys
import unittest
from unittest.mock import MagicMock

# Add src path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.brain.agents.grisha import Grisha


class TestGrishaDiscoveryResilience(unittest.TestCase):
    def setUp(self):
        # Create Grisha instance with mocked dependencies
        self.grisha = Grisha.__new__(Grisha)
        self.grisha._verdict_markers_cache = None
        self.grisha._rejection_history = {}

    def test_fallback_verdict_not_found_is_success(self):
        """Test that 'not found' in a successful tool execution is treated as success."""
        results = [
            {
                "tool": "duckduckgo-search",
                "result": "No results found for the given query.",
                "error": False,
            }
        ]
        verdict = self.grisha._fallback_verdict(results)
        self.assertTrue(verdict["verified"])
        self.assertIn("пройшли валідацію", verdict["reasoning"])

    def test_fallback_verdict_empty_result_is_success_for_discovery(self):
        """Test that empty results for discovery tools are treated as success."""
        results = [{"tool": "golden-fund", "result": "", "error": False}]
        verdict = self.grisha._fallback_verdict(results)
        self.assertTrue(verdict["verified"])

    def test_fallback_verdict_actual_error_is_failure(self):
        """Test that actual errors are still treated as failures."""
        results = [
            {"tool": "duckduckgo-search", "result": "error: connection timeout", "error": True}
        ]
        verdict = self.grisha._fallback_verdict(results)
        self.assertFalse(verdict["verified"])

    def test_extract_issues_filters_not_found_when_verified(self):
        """Test that 'not found' issues are filtered out when the step is verified."""
        analysis_text = """
        VERDICT: CONFIRMED
        REASONING: The search was completed but no entities were found. This confirms the absence of data.
        ISSUES:
        - Result not found in registry
        - Empty output from tool
        """
        # We simulate that the LLM/fallback marked it as verified
        issues = self.grisha._extract_issues(analysis_text, verified=True)
        self.assertEqual(len(issues), 0)

    def test_extract_issues_keeps_other_issues_when_verified(self):
        """Test that non-discovery issues are still kept when verified."""
        analysis_text = """
        VERDICT: CONFIRMED
        REASONING: The search was completed.
        ISSUES:
        - Result not found in registry
        - Slow response time
        """
        issues = self.grisha._extract_issues(analysis_text, verified=True)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0], "- Slow response time")


if __name__ == "__main__":
    unittest.main()
