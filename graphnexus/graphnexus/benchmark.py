"""Latency benchmarks for lookups, traversals and whole-graph algorithms."""
from __future__ import annotations

import random
import statistics
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List

from .algorithms import (
    bfs, dfs, pagerank, shortest_path, strongly_connected_components,
    weakly_connected_components,
)
from .storage import GraphStore


@dataclass(frozen=True)
class Timing:
    name: str
    count: int
    mean_ns: float
    median_ns: float
    p95_ns: float


@dataclass(frozen=True)
class BenchmarkReport:
    path: str
    num_nodes: int
    num_edges: int
    directed: bool
    timings: List[Timing]

    def to_dict(self) -> Dict:
        return {**{k: v for k, v in asdict(self).items() if k != "timings"},
                "timings": [asdict(t) for t in self.timings]}


def format_ns(ns: float) -> str:
    if ns < 1_000:
        return f"{ns:.0f} ns"
    if ns < 1_000_000:
        return f"{ns / 1_000:.2f} us"
    if ns < 1_000_000_000:
        return f"{ns / 1_000_000:.3f} ms"
    return f"{ns / 1_000_000_000:.3f} s"


def _measure(name: str, fn: Callable, args: List[tuple]) -> Timing:
    samples: List[int] = []
    clock = time.perf_counter_ns
    for a in args:
        t0 = clock()
        fn(*a)
        samples.append(clock() - t0)
    samples.sort()
    p95 = samples[min(len(samples) - 1, int(len(samples) * 0.95))]
    return Timing(name, len(samples), statistics.fmean(samples), statistics.median(samples), float(p95))


def run_benchmark(store: GraphStore, queries: int = 10_000, traversals: int = 50, seed: int = 42) -> BenchmarkReport:
    """Benchmark ``store``. ``queries`` = point lookups per metric, ``traversals`` = full traversals."""
    if store.n == 0:
        raise ValueError("Cannot benchmark an empty graph")
    rng = random.Random(seed)
    n = store.n
    ext = [store.external_id(i) for i in range(n)]
    max_ext = max(ext)
    with_edges = [i for i in range(n) if store.out_degree(i) > 0] or [0]

    present = [(ext[rng.randrange(n)],) for _ in range(queries)]
    missing = [(max_ext + 1 + rng.randrange(10 * n),) for _ in range(queries)]
    edge_hits = []
    for _ in range(queries):
        u = rng.choice(with_edges)
        nbrs = store.out_neighbors(u)
        edge_hits.append((ext[u], ext[rng.choice(nbrs)]) if nbrs else (ext[u], ext[u]))
    edge_random = [(ext[rng.randrange(n)], ext[rng.randrange(n)]) for _ in range(queries)]
    sources = [(rng.randrange(n),) for _ in range(traversals)]
    pairs = [(rng.randrange(n), rng.randrange(n)) for _ in range(traversals)]

    timings = [
        _measure("node lookup (hit)", store.node_index, present),
        _measure("node lookup (miss)", store.node_index, missing),
        _measure("edge lookup (existing edge)", store.has_edge, edge_hits),
        _measure("edge lookup (random pair)", store.has_edge, edge_random),
        _measure("neighbour query (id -> neighbour ids)", store.neighbors_of, present),
        _measure("BFS (full traversal)", bfs, [(store, s[0]) for s in sources]),
        _measure("DFS (full traversal)", dfs, [(store, s[0]) for s in sources]),
        _measure("shortest path (BFS)", shortest_path, [(store, a, b) for a, b in pairs]),
        _measure("PageRank (to convergence)", pagerank, [(store,)] * 3),
        _measure("WCC (whole graph)", weakly_connected_components, [(store,)] * 3),
        _measure("SCC (whole graph)", strongly_connected_components, [(store,)] * 3),
    ]
    return BenchmarkReport(str(store.path), n, store.num_edges, store.directed, timings)


def format_report(report: BenchmarkReport) -> str:
    rows = [("operation", "runs", "mean", "median", "p95")]
    for t in report.timings:
        rows.append((t.name, str(t.count), format_ns(t.mean_ns), format_ns(t.median_ns), format_ns(t.p95_ns)))
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    lines = []
    for i, r in enumerate(rows):
        lines.append("  ".join(c.ljust(widths[0]) if j == 0 else c.rjust(widths[j]) for j, c in enumerate(r)))
        if i == 0:
            lines.append("  ".join("-" * w for w in widths))
    kind = "directed" if report.directed else "undirected"
    head = f"{report.path}: {report.num_nodes:,} nodes, {report.num_edges:,} edges ({kind})"
    return head + "\n\n" + "\n".join(lines)
