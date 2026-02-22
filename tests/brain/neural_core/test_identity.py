"""
Tests for PostulateManager: Identity and Ethics.
"""

import pytest
from src.brain.neural_core.identity.postulate_manager import PostulateManager

def test_postulates_content():
    manager = PostulateManager()
    postulates = manager.get_postulates()
    assert "ENTROPY_MANIFESTO" in postulates
    assert "EVOLUTIONARY_WILL" in postulates
    assert "Oleg Mykolayovych" in postulates["PROACTIVE_PROTECTION"]

def test_milestones_presence():
    manager = PostulateManager()
    milestones = manager.get_milestones()
    assert len(milestones) > 0
    assert any("Уже в дорозі" in m["event"] for m in milestones)

def test_audit_context():
    manager = PostulateManager()
    context = manager.get_audit_prompt_context()
    assert "ENTROPY_MANIFESTO" in context
    assert "EVOLUTIONARY_WILL" in context
