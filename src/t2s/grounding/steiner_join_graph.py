"""Lightweight join-graph planner for rendering the query explanation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GraphJoinEdge:
    left_table: str
    right_table: str
    left_cols: tuple[str, ...]
    right_cols: tuple[str, ...]
    source: str = "fk"
    cardinality: str = "N:1"

    def on_clause(self) -> str:
        return " AND ".join(
            f"{self.left_table}.{left} = {self.right_table}.{right}"
            for left, right in zip(self.left_cols, self.right_cols, strict=True)
        )


@dataclass
class JoinPlan:
    edges: list[GraphJoinEdge] = field(default_factory=list)
    bridge_tables: list[str] = field(default_factory=list)
    connected: bool = True
    warnings: list[str] = field(default_factory=list)


class SteinerJoinGraph:
    def __init__(self, edges: list[GraphJoinEdge]) -> None:
        self.edges = edges

    def plan(self, tables: list[str]) -> JoinPlan:
        targets = list(dict.fromkeys(table for table in tables if table))
        if len(targets) < 2:
            return JoinPlan()

        adjacency: dict[str, list[tuple[str, GraphJoinEdge]]] = {}
        for edge in self.edges:
            adjacency.setdefault(edge.left_table, []).append((edge.right_table, edge))
            adjacency.setdefault(edge.right_table, []).append((edge.left_table, edge))

        selected: list[GraphJoinEdge] = []
        used_tables = {targets[0]}
        warnings: list[str] = []
        for target in targets[1:]:
            queue: deque[tuple[str, list[GraphJoinEdge]]] = deque([(targets[0], [])])
            visited = {targets[0]}
            path: list[GraphJoinEdge] | None = None
            while queue:
                node, edges_so_far = queue.popleft()
                if node == target:
                    path = edges_so_far
                    break
                for next_node, edge in adjacency.get(node, []):
                    if next_node not in visited:
                        visited.add(next_node)
                        queue.append((next_node, [*edges_so_far, edge]))
            if path is None:
                warnings.append(f"Không tìm thấy liên kết khóa ngoại từ {targets[0]} tới {target}.")
                continue
            for edge in path:
                if edge not in selected:
                    selected.append(edge)
                    used_tables.update((edge.left_table, edge.right_table))

        bridges = [table for table in used_tables if table not in targets]
        return JoinPlan(selected, bridges, not warnings, warnings)
