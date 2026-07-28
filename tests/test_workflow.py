"""Tests for core.workflow (Graph-based workflow engine with State flow).

Note: core/workflow.py does not currently exist in the project.
This test file defines a minimal, self-contained Graph/State implementation
that the workflow module is expected to provide, and tests it thoroughly.
When the workflow module is created, update the import to:
    from core.workflow import Graph, State
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

# ── Inline implementation (replace with real import when available) ────


class State(dict):
    """Mutable state bag passed through graph nodes."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def get_or(self, key: str, default: Any = None) -> Any:
        return self.get(key, default)


class GraphCycleError(Exception):
    """Raised when a cycle is detected in the graph."""


@dataclass
class Node:
    name: str
    fn: Callable[[State], State]
    description: str = ""


@dataclass
class Edge:
    source: str
    target: str
    condition: Callable[[State], bool] | None = None


class Graph:
    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._entry: str | None = None

    def add_node(self, name: str, fn: Callable[[State], State], description: str = "") -> None:
        self._nodes[name] = Node(name=name, fn=fn, description=description)

    def add_edge(
        self, source: str, target: str, condition: Callable[[State], bool] | None = None
    ) -> None:
        if source not in self._nodes:
            raise ValueError(f"Source node '{source}' not found")
        if target not in self._nodes:
            raise ValueError(f"Target node '{target}' not found")
        self._edges.append(Edge(source=source, target=target, condition=condition))

    def set_entry(self, name: str) -> None:
        if name not in self._nodes:
            raise ValueError(f"Node '{name}' not found")
        self._entry = name

    def _detect_cycle(self) -> None:
        """DFS-based cycle detection. Only flags unconditional cycles."""
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node_name: str) -> None:
            visited.add(node_name)
            rec_stack.add(node_name)
            for edge in self._edges:
                if edge.source == node_name and edge.condition is None:
                    if edge.target not in visited:
                        dfs(edge.target)
                    elif edge.target in rec_stack:
                        raise GraphCycleError(f"Cycle detected involving node '{edge.target}'")
            rec_stack.discard(node_name)

        for name in self._nodes:
            if name not in visited:
                dfs(name)

    def run(self, initial_state: State | None = None) -> State:
        if not self._nodes:
            return initial_state or State()
        if self._entry is None:
            raise ValueError("No entry point set. Call set_entry() first.")

        self._detect_cycle()

        state = initial_state or State()
        current = self._entry
        visited: set[str] = set()

        while current is not None:
            if current in visited:
                raise GraphCycleError(f"Runtime cycle at node '{current}'")
            visited.add(current)

            node = self._nodes[current]
            state = node.fn(state)

            # Find next node
            next_node = None
            for edge in self._edges:
                if edge.source == current:
                    if edge.condition is None or edge.condition(state):
                        next_node = edge.target
                        break
            current = next_node

        return state


# ── Tests ─────────────────────────────────────────────────────────────


class TestState:
    def test_create_state(self):
        s = State(x=1, y=2)
        assert s["x"] == 1
        assert s["y"] == 2

    def test_get_or(self):
        s = State(a=1)
        assert s.get_or("a") == 1
        assert s.get_or("b", "default") == "default"

    def test_empty_state(self):
        s = State()
        assert len(s) == 0

    def test_mutable(self):
        s = State(x=1)
        s["y"] = 2
        assert s["y"] == 2

    def test_state_as_dict(self):
        s = State(a="hello")
        assert isinstance(s, dict)


class TestGraphAddNode:
    def test_add_node(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        assert "a" in g._nodes

    def test_add_multiple_nodes(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        assert len(g._nodes) == 2

    def test_add_node_with_description(self):
        g = Graph()
        g.add_node("a", lambda s: s, description="first node")
        assert g._nodes["a"].description == "first node"

    def test_add_node_replaces(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        g.add_node("a", lambda s: s)
        assert len(g._nodes) == 1


class TestGraphAddEdge:
    def test_add_edge(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_edge("a", "b")
        assert len(g._edges) == 1

    def test_add_edge_missing_source(self):
        g = Graph()
        g.add_node("b", lambda s: s)
        with pytest.raises(ValueError, match="Source"):
            g.add_edge("a", "b")

    def test_add_edge_missing_target(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        with pytest.raises(ValueError, match="Target"):
            g.add_edge("a", "b")

    def test_add_conditional_edge(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        cond = lambda s: s.get("go", False)
        g.add_edge("a", "b", condition=cond)
        assert g._edges[0].condition is not None


class TestGraphSetEntry:
    def test_set_entry(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        g.set_entry("a")
        assert g._entry == "a"

    def test_set_entry_missing(self):
        g = Graph()
        with pytest.raises(ValueError, match="not found"):
            g.set_entry("x")


class TestGraphRunLinear:
    def test_single_node(self):
        g = Graph()
        g.add_node("start", lambda s: {**s, "done": True})
        g.set_entry("start")
        result = g.run()
        assert result["done"] is True

    def test_linear_chain(self):
        g = Graph()
        g.add_node("a", lambda s: {**s, "a": True})
        g.add_node("b", lambda s: {**s, "b": True})
        g.add_node("c", lambda s: {**s, "c": True})
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.set_entry("a")
        result = g.run()
        assert result["a"] is True
        assert result["b"] is True
        assert result["c"] is True

    def test_state_flows_through(self):
        g = Graph()
        g.add_node("double", lambda s: {**s, "value": s.get("value", 1) * 2})
        g.add_node("add_ten", lambda s: {**s, "value": s.get("value", 0) + 10})
        g.add_edge("double", "add_ten")
        g.set_entry("double")
        result = g.run(State(value=5))
        assert result["value"] == 20

    def test_empty_graph(self):
        g = Graph()
        result = g.run()
        assert isinstance(result, State)

    def test_no_entry_raises(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        with pytest.raises(ValueError, match="No entry point"):
            g.run()

    def test_run_with_initial_state(self):
        g = Graph()
        g.add_node("inc", lambda s: {**s, "x": s.get("x", 0) + 1})
        g.set_entry("inc")
        result = g.run(State(x=10))
        assert result["x"] == 11


class TestGraphConditionalEdges:
    def test_condition_true(self):
        g = Graph()
        g.add_node("a", lambda s: {**s, "branch": "left"})
        g.add_node("left", lambda s: {**s, "visited": "left"})
        g.add_node("right", lambda s: {**s, "visited": "right"})
        g.add_edge("a", "left", condition=lambda s: s.get("branch") == "left")
        g.add_edge("a", "right", condition=lambda s: s.get("branch") == "right")
        g.set_entry("a")
        result = g.run()
        assert result["visited"] == "left"

    def test_condition_false_fallback(self):
        g = Graph()
        g.add_node("a", lambda s: {**s, "branch": "right"})
        g.add_node("left", lambda s: {**s, "visited": "left"})
        g.add_node("right", lambda s: {**s, "visited": "right"})
        g.add_edge("a", "left", condition=lambda s: s.get("branch") == "left")
        g.add_edge("a", "right", condition=lambda s: s.get("branch") == "right")
        g.set_entry("a")
        result = g.run()
        assert result["visited"] == "right"

    def test_unconditional_edge_always_takes(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: {**s, "result": "b"})
        g.add_edge("a", "b")
        g.set_entry("a")
        result = g.run()
        assert result["result"] == "b"

    def test_multiple_conditions_first_match_wins(self):
        g = Graph()
        g.add_node("a", lambda s: {**s, "mode": "fast"})
        g.add_node("fast", lambda s: {**s, "path": "fast"})
        g.add_node("slow", lambda s: {**s, "path": "slow"})
        g.add_edge("a", "fast", condition=lambda s: s.get("mode") == "fast")
        g.add_edge("a", "slow", condition=lambda s: s.get("mode") == "slow")
        g.set_entry("a")
        result = g.run()
        assert result["path"] == "fast"


class TestGraphLoopDetection:
    def test_direct_cycle(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        g.add_edge("a", "a")
        g.set_entry("a")
        with pytest.raises(GraphCycleError):
            g.run()

    def test_indirect_cycle(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        g.set_entry("a")
        with pytest.raises(GraphCycleError):
            g.run()

    def test_three_node_cycle(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_node("c", lambda s: s)
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        g.set_entry("a")
        with pytest.raises(GraphCycleError):
            g.run()

    def test_no_false_positive_linear(self):
        g = Graph()
        g.add_node("a", lambda s: s)
        g.add_node("b", lambda s: s)
        g.add_node("c", lambda s: s)
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.set_entry("a")
        # Should not raise
        g.run()

    def test_conditional_cycle_not_triggered(self):
        g = Graph()
        g.add_node("a", lambda s: {**s, "stop": True})
        g.add_node("b", lambda s: s)
        g.add_edge("a", "a", condition=lambda s: not s.get("stop", False))
        g.add_edge("a", "b", condition=lambda s: s.get("stop", False))
        g.set_entry("a")
        result = g.run()
        assert result["stop"] is True


class TestGraphStateFlow:
    def test_accumulate_across_nodes(self):
        g = Graph()
        g.add_node("init", lambda s: {**s, "log": ["init"]})
        g.add_node("step1", lambda s: {**s, "log": s["log"] + ["step1"]})
        g.add_node("step2", lambda s: {**s, "log": s["log"] + ["step2"]})
        g.add_edge("init", "step1")
        g.add_edge("step1", "step2")
        g.set_entry("init")
        result = g.run()
        assert result["log"] == ["init", "step1", "step2"]

    def test_node_transformations_chain(self):
        g = Graph()
        g.add_node("start", lambda s: {**s, "value": 10})
        g.add_node("double", lambda s: {**s, "value": s["value"] * 2})
        g.add_node("negate", lambda s: {**s, "value": -s["value"]})
        g.add_edge("start", "double")
        g.add_edge("double", "negate")
        g.set_entry("start")
        result = g.run()
        assert result["value"] == -20

    def test_independent_keys(self):
        g = Graph()
        g.add_node("a", lambda s: {**s, "x": 1})
        g.add_node("b", lambda s: {**s, "y": 2})
        g.add_edge("a", "b")
        g.set_entry("a")
        result = g.run()
        assert result["x"] == 1
        assert result["y"] == 2

    def test_branching_state(self):
        g = Graph()
        g.add_node("decide", lambda s: {**s, "type": "premium"})
        g.add_node("premium_flow", lambda s: {**s, "discount": 0.2})
        g.add_node("basic_flow", lambda s: {**s, "discount": 0.0})
        g.add_edge("decide", "premium_flow", condition=lambda s: s.get("type") == "premium")
        g.add_edge("decide", "basic_flow", condition=lambda s: s.get("type") != "premium")
        g.set_entry("decide")
        result = g.run()
        assert result["discount"] == 0.2

    def test_initial_state_preserved(self):
        g = Graph()
        g.add_node("echo", lambda s: {**s, "seen": True})
        g.set_entry("echo")
        result = g.run(State(original=True))
        assert result["original"] is True
        assert result["seen"] is True
