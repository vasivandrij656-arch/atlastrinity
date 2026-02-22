"""
Tests for CognitiveGraph: Relational and Causal Memory.
"""

import asyncio
import os

import pytest

from src.brain.neural_core.memory.graph import CognitiveGraph


@pytest.fixture
async def temp_graph():
    db_path = "tests/temp_test_graph.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    graph = CognitiveGraph(db_path=db_path)
    await graph.initialize()
    yield graph
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_add_and_get_node(temp_graph):
    await temp_graph.add_node("test_node", "test_type", "Test Node", {"attr": "val"})
    node = await temp_graph.get_node("test_node")
    assert node is not None
    assert node["label"] == "Test Node"
    assert node["type"] == "test_type"


@pytest.mark.asyncio
async def test_causality_chain(temp_graph):
    await temp_graph.add_node("A", "event", "Event A", {})
    await temp_graph.add_node("B", "event", "Event B", {})
    await temp_graph.add_edge("A", "B", "caused", {})

    chain = await temp_graph.get_causality_chain("B")
    assert len(chain) > 0
    assert chain[0]["source_id"] == "A"
    assert chain[0]["relation"] == "caused"
