from src.brain.prompts import AgentPrompts


def test_agent_prompts_exports():
    assert hasattr(AgentPrompts, "ATLAS")
    assert hasattr(AgentPrompts, "TETYANA")
    assert hasattr(AgentPrompts, "GRISHA")


def test_grisha_prompt_contains_dynamic_catalog():
    """Verify Grisha's prompt includes dynamic server catalog from mcp_registry."""
    sys_prompt = AgentPrompts.get_agent_system_prompt("GRISHA")

    # Check that catalog is properly interpolated from mcp_registry
    assert "TIER 1 - CORE" in sys_prompt or "macos-use" in sys_prompt

    # Check MCP verification tools are mentioned
    assert "macos-use_refresh_traversal" in sys_prompt or "execute_command" in sys_prompt


def test_atlas_prompt_contains_dynamic_catalog():
    """Verify Atlas's prompt includes dynamic server catalog from mcp_registry."""
    sys_prompt = AgentPrompts.get_agent_system_prompt("ATLAS")

    # Check that catalog is properly interpolated
    assert "TIER 1 - CORE" in sys_prompt or "macos-use" in sys_prompt


def test_tetyana_prompt_contains_dynamic_catalog():
    """Verify Tetyana's prompt includes dynamic server catalog from mcp_registry."""
    sys_prompt = AgentPrompts.get_agent_system_prompt("TETYANA")

    # Check that catalog is properly interpolated
    assert "TIER 1 - CORE" in sys_prompt or "macos-use" in sys_prompt


def test_prompts_no_uninterpolated_placeholders():
    """Verify no literal placeholders remain in formatted prompts."""
    for name in ["ATLAS", "TETYANA", "GRISHA"]:
        prompt = AgentPrompts.get_agent_system_prompt(name)
        assert "{catalog}" not in prompt, f"{name} has uninterpolated catalog"
        assert "{vibe_tools_documentation}" not in prompt, f"{name} has uninterpolated vibe docs"
        assert "{voice_protocol}" not in prompt, f"{name} has uninterpolated voice protocol"
        # CRITICAL: Verify that nested placeholders from voice protocol ARE PRESENT as literals for downstream runtime formatting
        assert "{failure_essence}" in prompt, f"{name} is missing {{failure_essence}} placeholder for runtime replacement"
        assert "{reason_short}" in prompt, f"{name} is missing {{reason_short}} placeholder for runtime replacement"
