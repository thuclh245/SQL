"""Steiner Tree Join Graph for safe schema linking in Text-to-SQL.

Finds the most secure, minimal join path connecting a set of anchor tables.
Edge weights encode SAFETY (cardinality, verified FKs, orphan rate) rather than mere distance:
- Verified 1:N FK: weight = 1.0
- Lineage / catalog relation: weight = 2.0
- Name matching heuristic: weight = 3.0
- N:M cardinality penalty: +5.0 (forces Dijkstra to avoid fan-out joins)
- High orphan rate (> 20%): +2.0
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Literal

EdgeSource = Literal["fk", "lineage", "name"]
Cardinality = Literal["1:1", "1:N", "N:1", "N:M", "unknown"]


@dataclass(frozen=True)
class GraphJoinEdge:
    left_table: str
    right_table: str
    left_cols: tuple[str, ...]
    right_cols: tuple[str, ...]
    source: EdgeSource = "fk"
    cardinality: Cardinality = "unknown"
    orphan_rate: float | None = None
    confidence: float = 1.0

    def other(self, t: str) -> str:
        return self.right_table if t.lower() == self.left_table.lower() else self.left_table

    def on_clause(self, left_alias: str | None = None, right_alias: str | None = None) -> str:
        la = left_alias or self.left_table
        ra = right_alias or self.right_table
        return " AND ".join(f"{la}.{l} = {ra}.{r}" for l, r in zip(self.left_cols, self.right_cols))


DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {"fk": 1.0, "lineage": 2.0, "name": 3.0}
PENALTY_NM: float = 5.0


def calculate_edge_weight(
    edge: GraphJoinEdge,
    source_weights: dict[str, float] | None = None,
    penalty_nm: float = PENALTY_NM,
) -> float:
    weights = source_weights or DEFAULT_SOURCE_WEIGHTS
    base = weights.get(edge.source, 3.0)
    if edge.cardinality == "N:M":
        base += penalty_nm
    if edge.orphan_rate is not None and edge.orphan_rate > 0.2:
        base += 2.0
    return base / max(edge.confidence, 0.1)


@dataclass
class SteinerJoinPlan:
    edges: list[GraphJoinEdge]
    bridge_tables: list[str]
    warnings: list[str]
    connected: bool

    def render(self) -> str:
        if not self.edges:
            return ""
        lines = []
        for e in self.edges:
            card_note = f" [{e.cardinality}]" if e.cardinality != "unknown" else ""
            lines.append(f"  {e.left_table} JOIN {e.right_table} ON {e.on_clause()}{card_note}")
        if self.bridge_tables:
            lines.append(f"  -- Bảng cầu nối tự động suy luận: {', '.join(self.bridge_tables)}")
        return "\n".join(lines)


class SteinerJoinGraph:
    """Join Graph engine implementing KMB Steiner Tree algorithm for safe SQL schema linking."""

    def __init__(
        self,
        edges: list[GraphJoinEdge],
        source_weights: dict[str, float] | None = None,
        penalty_nm: float = PENALTY_NM,
    ) -> None:
        self.edges = edges
        self.adj: dict[str, list[tuple[str, float, GraphJoinEdge]]] = {}
        for e in edges:
            w = calculate_edge_weight(e, source_weights, penalty_nm)
            self.adj.setdefault(e.left_table.lower(), []).append((e.right_table.lower(), w, e))
            self.adj.setdefault(e.right_table.lower(), []).append((e.left_table.lower(), w, e))

    def _dijkstra(self, src: str) -> tuple[dict[str, float], dict[str, tuple[str, GraphJoinEdge]]]:
        dist = {src: 0.0}
        prev: dict[str, tuple[str, GraphJoinEdge]] = {}
        pq = [(0.0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, float("inf")):
                continue
            for v, w, e in self.adj.get(u, []):
                nd = d + w
                if nd < dist.get(v, float("inf")):
                    dist[v], prev[v] = nd, (u, e)
                    heapq.heappush(pq, (nd, v))
        return dist, prev

    def _path(
        self,
        prev: dict[str, tuple[str, GraphJoinEdge]],
        src: str,
        dst: str,
    ) -> list[GraphJoinEdge] | None:
        out: list[GraphJoinEdge] = []
        cur = dst
        while cur != src:
            if cur not in prev:
                return None
            p, e = prev[cur]
            out.append(e)
            cur = p
        return list(reversed(out))

    def plan(self, anchors: list[str]) -> SteinerJoinPlan:
        """Kou-Markowsky-Berman (KMB) heuristic for Steiner Minimal Tree."""
        uniq = list(dict.fromkeys(a.lower() for a in anchors))
        valid_anchors = [a for a in uniq if a in self.adj]
        missing_anchors = [a for a in uniq if a not in self.adj]

        if len(valid_anchors) <= 1:
            warns = []
            if missing_anchors:
                warns.append(
                    f"Bảng neo không có trong Join Graph: {missing_anchors}. LLM sẽ phải tự suy luận đường JOIN."
                )
            return SteinerJoinPlan(edges=[], bridge_tables=[], warnings=warns, connected=not missing_anchors)

        sp = {a: self._dijkstra(a) for a in valid_anchors}

        # Prim algorithm over distance metric closure
        inside = {valid_anchors[0]}
        outside = set(valid_anchors[1:])
        chosen_edges: list[GraphJoinEdge] = []
        unreachable: list[str] = []

        while outside:
            best = None
            for u in inside:
                dist, prev = sp[u]
                for v in outside:
                    if v in dist and (best is None or dist[v] < best[0]):
                        best = (dist[v], u, v)
            if best is None:
                unreachable = sorted(outside)
                break
            _, u, v = best
            path = self._path(sp[u][1], u, v)
            if path:
                for pe in path:
                    if pe not in chosen_edges:
                        chosen_edges.append(pe)
            inside.add(v)
            outside.remove(v)

        # Detect bridge tables (tables included in join path that were not original anchors)
        path_tables: set[str] = set()
        for e in chosen_edges:
            path_tables.add(e.left_table.lower())
            path_tables.add(e.right_table.lower())

        bridge_tables = sorted(path_tables - set(valid_anchors))
        warnings = []
        if unreachable:
            warnings.append(f"Không thể tìm đường nối tới các bảng: {unreachable}")
        if missing_anchors:
            warnings.append(f"Bảng neo chưa có thông tin quan hệ trong catalog: {missing_anchors}")

        is_connected = not unreachable and not missing_anchors
        return SteinerJoinPlan(
            edges=chosen_edges,
            bridge_tables=bridge_tables,
            warnings=warnings,
            connected=is_connected,
        )
