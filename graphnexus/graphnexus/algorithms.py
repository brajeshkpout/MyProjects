"""Core graph algorithms: BFS, DFS, shortest path, PageRank, WCC and SCC.

Every function works on any *GraphView*: an object with ``n``, ``out_neighbors(i)`` and
``in_neighbors(i)`` over dense node indexes (both ``Graph`` and the on-disk ``GraphStore``).
All traversals are iterative, so deep graphs never hit Python's recursion limit.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

NeighborFn = Callable[[int], Sequence[int]]


def _neighbor_fn(view, direction: str) -> NeighborFn:
    if direction == "out":
        return view.out_neighbors
    if direction == "in":
        return view.in_neighbors
    if direction == "both":
        def both(i: int) -> Sequence[int]:
            return sorted(set(view.out_neighbors(i)) | set(view.in_neighbors(i)))
        return both
    raise ValueError("direction must be 'out', 'in' or 'both'")


def _check_node(view, node: int) -> None:
    if not 0 <= node < view.n:
        raise IndexError(f"node index {node} out of range")


# ------------------------------------------------------------------------------ traversal
@dataclass(frozen=True)
class BFSResult:
    order: List[int]          # nodes in visiting order
    distance: Dict[int, int]  # node -> hops from the source


def bfs(view, source: int, max_depth: Optional[int] = None, direction: str = "out") -> BFSResult:
    """Breadth-first search from ``source``; optionally stop expanding at ``max_depth``."""
    _check_node(view, source)
    neighbors = _neighbor_fn(view, direction)
    dist = {source: 0}
    order = [source]
    queue = deque([source])
    while queue:
        u = queue.popleft()
        d = dist[u]
        if max_depth is not None and d >= max_depth:
            continue
        for v in neighbors(u):
            if v not in dist:
                dist[v] = d + 1
                order.append(v)
                queue.append(v)
    return BFSResult(order, dist)


def dfs(view, source: int, direction: str = "out") -> List[int]:
    """Depth-first *pre-order* from ``source`` (same order as the recursive definition)."""
    _check_node(view, source)
    neighbors = _neighbor_fn(view, direction)
    visited = {source}
    order = [source]
    stack = [iter(neighbors(source))]
    while stack:
        for v in stack[-1]:
            if v not in visited:
                visited.add(v)
                order.append(v)
                stack.append(iter(neighbors(v)))
                break
        else:
            stack.pop()
    return order


def shortest_path(view, source: int, target: int, direction: str = "out") -> Optional[List[int]]:
    """Fewest-hops path ``source -> target`` (BFS with parent pointers) or ``None``."""
    _check_node(view, source)
    _check_node(view, target)
    if source == target:
        return [source]
    neighbors = _neighbor_fn(view, direction)
    parent = {source: source}
    queue = deque([source])
    while queue:
        u = queue.popleft()
        for v in neighbors(u):
            if v in parent:
                continue
            parent[v] = u
            if v == target:
                path = [v]
                while path[-1] != source:
                    path.append(parent[path[-1]])
                return path[::-1]
            queue.append(v)
    return None


# ----------------------------------------------------------------------------- PageRank
@dataclass(frozen=True)
class PageRankResult:
    scores: List[float]
    iterations: int
    converged: bool


def pagerank(
    view, damping: float = 0.85, tol: float = 1e-9, max_iter: int = 200
) -> PageRankResult:
    """PageRank by power iteration.

    Dangling nodes (no out-edges) spread their rank uniformly, teleportation is uniform, and
    the scores always sum to 1. Stops when the L1 change drops below ``tol``.
    """
    if not 0.0 < damping < 1.0:
        raise ValueError("damping must be strictly between 0 and 1")
    if max_iter < 1:
        raise ValueError("max_iter must be >= 1")
    n = view.n
    if n == 0:
        return PageRankResult([], 0, True)

    adj = [view.out_neighbors(i) for i in range(n)]
    out_deg = [len(a) for a in adj]
    dangling = [i for i in range(n) if out_deg[i] == 0]
    rank = [1.0 / n] * n

    for iteration in range(1, max_iter + 1):
        dangling_mass = sum(rank[i] for i in dangling)
        base = (1.0 - damping) / n + damping * dangling_mass / n
        new = [base] * n
        for u in range(n):
            deg = out_deg[u]
            if deg:
                share = damping * rank[u] / deg
                for v in adj[u]:
                    new[v] += share
        delta = sum(abs(new[i] - rank[i]) for i in range(n))
        rank = new
        if delta < tol:
            return PageRankResult(rank, iteration, True)
    return PageRankResult(rank, max_iter, False)


def top_k(scores: Sequence[float], k: int) -> List[int]:
    """Indexes of the ``k`` highest scores (ties broken by lower index)."""
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:k]


# ------------------------------------------------------------------ connected components
@dataclass(frozen=True)
class Components:
    labels: List[int]  # node -> component id
    sizes: List[int]   # component id -> number of nodes

    @property
    def count(self) -> int:
        return len(self.sizes)

    @property
    def largest_size(self) -> int:
        return max(self.sizes) if self.sizes else 0

    def largest_component(self) -> int:
        """Id of the largest component (lowest id on ties)."""
        return max(range(len(self.sizes)), key=lambda c: (self.sizes[c], -c))


def _sizes(labels: List[int], count: int) -> List[int]:
    sizes = [0] * count
    for c in labels:
        sizes[c] += 1
    return sizes


def weakly_connected_components(view) -> Components:
    """WCC: components of the graph when edge directions are ignored (union-find)."""
    n = view.n
    parent = list(range(n))

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for u in range(n):
        for v in view.out_neighbors(u):
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[max(ru, rv)] = min(ru, rv)

    ids: Dict[int, int] = {}
    labels = [0] * n
    for u in range(n):
        labels[u] = ids.setdefault(find(u), len(ids))
    return Components(labels, _sizes(labels, len(ids)))


def strongly_connected_components(view) -> Components:
    """SCC via an iterative version of Tarjan's algorithm (O(V + E))."""
    n = view.n
    adj = [view.out_neighbors(i) for i in range(n)]
    index = [-1] * n
    low = [0] * n
    on_stack = [False] * n
    label = [-1] * n
    stack: List[int] = []
    counter = 0
    comp_count = 0

    for root in range(n):
        if index[root] != -1:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack[root] = True
        work = [(root, 0)]
        while work:
            v, i = work[-1]
            nbrs = adj[v]
            if i < len(nbrs):
                work[-1] = (v, i + 1)
                w = nbrs[i]
                if index[w] == -1:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack[w] = True
                    work.append((w, 0))
                elif on_stack[w] and index[w] < low[v]:
                    low[v] = index[w]
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    if low[v] < low[parent]:
                        low[parent] = low[v]
                if low[v] == index[v]:
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        label[w] = comp_count
                        if w == v:
                            break
                    comp_count += 1
    return Components(label, _sizes(label, comp_count))
