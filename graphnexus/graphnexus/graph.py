"""In-memory graph model and edge-list (SNAP text format) reading / writing."""
from __future__ import annotations

import gzip
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

Edge = Tuple[int, int]


class EdgeListError(ValueError):
    """Raised for malformed edge-list files."""


class Graph:
    """Immutable graph with dense node indexes ``0..n-1`` and sorted adjacency lists.

    ``ext_ids[i]`` is the original (external) id of dense node ``i``; ids are sorted ascending.
    For undirected graphs every edge is stored in both directions and ``in`` == ``out``.
    """

    def __init__(
        self,
        ext_ids: List[int],
        out_adj: List[List[int]],
        in_adj: Optional[List[List[int]]],
        directed: bool,
        num_edges: int,
        self_loops_dropped: int = 0,
        duplicates_dropped: int = 0,
    ) -> None:
        self.ext_ids = ext_ids
        self._out = out_adj
        self._in = in_adj if directed else out_adj
        self.directed = directed
        self.num_edges = num_edges
        self.self_loops_dropped = self_loops_dropped
        self.duplicates_dropped = duplicates_dropped

    # -- GraphView protocol -------------------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.ext_ids)

    def out_neighbors(self, idx: int) -> Sequence[int]:
        return self._out[idx]

    def in_neighbors(self, idx: int) -> Sequence[int]:
        return self._in[idx]

    def external_id(self, idx: int) -> int:
        return self.ext_ids[idx]

    # -- construction -------------------------------------------------------------------
    @classmethod
    def from_edges(
        cls, edges: Iterable[Edge], directed: bool = False, nodes: Iterable[int] = ()
    ) -> "Graph":
        """Build a graph from ``(u, v)`` pairs of external ids.

        Self-loops and duplicate edges are dropped (and counted). ``nodes`` may add
        isolated nodes that appear in no edge.
        """
        id_set = set(nodes)
        raw: List[Edge] = []
        loops = 0
        for u, v in edges:
            id_set.add(u)
            id_set.add(v)
            if u == v:
                loops += 1
            else:
                raw.append((u, v))

        ext_ids = sorted(id_set)
        index = {ext: i for i, ext in enumerate(ext_ids)}
        n = len(ext_ids)
        out_sets = [set() for _ in range(n)]
        in_sets = [set() for _ in range(n)] if directed else None

        unique = 0
        for u, v in raw:
            a, b = index[u], index[v]
            if b in out_sets[a]:
                continue  # duplicate (for undirected graphs this also catches (v, u))
            out_sets[a].add(b)
            unique += 1
            if directed:
                in_sets[b].add(a)  # type: ignore[index]
            else:
                out_sets[b].add(a)

        out_adj = [sorted(s) for s in out_sets]
        in_adj = [sorted(s) for s in in_sets] if in_sets is not None else None
        return cls(ext_ids, out_adj, in_adj, directed, unique, loops, len(raw) - unique)


# ------------------------------------------------------------------------- edge-list I/O
def _open_text(path: Path, mode: str = "rt"):
    if str(path).endswith(".gz"):
        return gzip.open(path, mode, encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def read_edge_list(path) -> Iterator[Edge]:
    """Yield ``(u, v)`` integer pairs from a SNAP-style edge list (``.txt`` or ``.gz``).

    Lines starting with ``#`` or ``%`` and blank lines are ignored; fields may be separated by
    spaces, tabs or commas. Extra columns (e.g. weights) are ignored.
    """
    path = Path(path)
    with _open_text(path) as fh:
        for lineno, line in enumerate(fh, start=1):
            text = line.strip()
            if not text or text[0] in "#%":
                continue
            parts = text.replace(",", " ").split()
            if len(parts) < 2:
                raise EdgeListError(f"{path}:{lineno}: expected 'source target', got {text!r}")
            try:
                yield int(parts[0]), int(parts[1])
            except ValueError as exc:
                raise EdgeListError(f"{path}:{lineno}: node ids must be integers, got {text!r}") from exc


def load_graph(path, directed: bool = False) -> Graph:
    try:
        graph = Graph.from_edges(read_edge_list(path), directed=directed)
    except (OSError, UnicodeDecodeError, EOFError) as exc:
        raise EdgeListError(f"Cannot read {path}: {exc}") from exc
    if graph.n == 0:
        raise EdgeListError(f"{path}: no edges found")
    return graph


def write_edge_list(path, edges: Iterable[Edge], header: str = "") -> None:
    path = Path(path)
    with _open_text(path, "wt") as fh:
        for line in header.splitlines():
            fh.write(f"# {line}\n")
        for u, v in edges:
            fh.write(f"{u}\t{v}\n")
