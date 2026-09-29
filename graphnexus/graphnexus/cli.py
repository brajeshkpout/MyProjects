"""Command-line interface:  ``graphnexus <command> ...``  or  ``python -m graphnexus <command> ...``"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .algorithms import (
    bfs, dfs, pagerank, shortest_path, strongly_connected_components, top_k,
    weakly_connected_components,
)
from .benchmark import format_report, run_benchmark
from .datasets import SNAP_DATASETS, DatasetError, download_dataset, generate_social_graph
from .graph import EdgeListError, load_graph, write_edge_list
from .storage import GraphStore, StorageError, write_store


class CliError(Exception):
    """A user-facing error: printed as ``Error: ...`` with exit status 1."""


def _open(path: str) -> GraphStore:
    try:
        return GraphStore(path)
    except StorageError as exc:
        raise CliError(str(exc)) from exc


def _require_node(store: GraphStore, ext_id: int) -> int:
    idx = store.node_index(ext_id)
    if idx is None:
        raise CliError(f"Node {ext_id} does not exist in {store.path}")
    return idx


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    text = [[str(c) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in text)) if text else len(h) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:>{w}}}" for w in widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in widths))]
    lines += [fmt.format(*r) for r in text]
    return "\n".join(lines)


def _kind(store: GraphStore) -> str:
    return "directed" if store.directed else "undirected"


# ------------------------------------------------------------------------------ commands
def cmd_import(args) -> int:
    start = time.perf_counter()
    try:
        graph = load_graph(args.edge_list, directed=args.directed)
    except (EdgeListError, OSError) as exc:
        raise CliError(str(exc)) from exc
    summary = write_store(args.output, graph)
    elapsed = time.perf_counter() - start
    print(f"Imported {args.edge_list} -> {summary.path}")
    print(f"  type      : {'directed' if graph.directed else 'undirected'}")
    print(f"  nodes     : {graph.n:,}")
    print(f"  edges     : {graph.num_edges:,}")
    if graph.self_loops_dropped or graph.duplicates_dropped:
        print(f"  skipped   : {graph.self_loops_dropped:,} self-loops, {graph.duplicates_dropped:,} duplicate edges")
    print(f"  file size : {summary.size_bytes:,} bytes")
    print(f"  time      : {elapsed:.2f} s")
    return 0


def cmd_info(args) -> int:
    with _open(args.db) as store:
        print(f"File        : {store.path}")
        print(f"Format      : GNX1 ({store.file_size:,} bytes)")
        print(f"Type        : {_kind(store)}")
        print(f"Nodes       : {store.n:,}")
        print(f"Edges       : {store.num_edges:,}")
        if args.verify:
            ok = store.verify()
            print(f"Checksum    : {'OK' if ok else 'MISMATCH (file is corrupt)'}")
            return 0 if ok else 1
    return 0


def cmd_node(args) -> int:
    with _open(args.db) as store:
        idx = _require_node(store, args.node)
        outs = store.neighbors_of(args.node, "out")
        print(f"Node {args.node}")
        if store.directed:
            ins = store.neighbors_of(args.node, "in")
            print(f"  out-degree: {len(outs)}\n  in-degree : {len(ins)}")
            print(f"  out-neighbours: {_preview(outs, args.limit)}")
            print(f"  in-neighbours : {_preview(ins, args.limit)}")
        else:
            print(f"  degree    : {len(outs)}")
            print(f"  neighbours: {_preview(outs, args.limit)}")
    return 0


def _preview(items: Sequence[int], limit: int) -> str:
    if not items:
        return "(none)"
    shown = ", ".join(map(str, items[:limit]))
    return shown + (f", ... (+{len(items) - limit:,} more)" if len(items) > limit else "")


def cmd_edge(args) -> int:
    with _open(args.db) as store:
        _require_node(store, args.source)
        _require_node(store, args.target)
        found = store.has_edge(args.source, args.target)
    arrow = "->" if store.directed else "--"
    print(f"Edge {args.source} {arrow} {args.target}: {'EXISTS' if found else 'does not exist'}")
    return 0 if found else 2


def cmd_bfs(args) -> int:
    with _open(args.db) as store:
        src = _require_node(store, args.source)
        result = bfs(store, src, max_depth=args.max_depth, direction=args.direction)
        depth = max(result.distance.values())
        print(f"BFS from {args.source}: reached {len(result.order):,} of {store.n:,} nodes, max depth {depth}")
        rows = [(store.external_id(i), result.distance[i]) for i in result.order[: args.limit]]
        print(_table(["node", "distance"], rows))
        if len(result.order) > args.limit:
            print(f"... (+{len(result.order) - args.limit:,} more)")
    return 0


def cmd_dfs(args) -> int:
    with _open(args.db) as store:
        src = _require_node(store, args.source)
        order = dfs(store, src, direction=args.direction)
        print(f"DFS from {args.source}: reached {len(order):,} of {store.n:,} nodes")
        print("Pre-order: " + _preview([store.external_id(i) for i in order], args.limit))
    return 0


def cmd_path(args) -> int:
    with _open(args.db) as store:
        a, b = _require_node(store, args.source), _require_node(store, args.target)
        path = shortest_path(store, a, b, direction=args.direction)
        if path is None:
            print(f"No path from {args.source} to {args.target}")
            return 2
        print(f"Shortest path ({len(path) - 1} hops): " + " -> ".join(str(store.external_id(i)) for i in path))
    return 0


def _pagerank_rows(store: GraphStore, scores: List[float], k: int):
    rows = []
    for rank, i in enumerate(top_k(scores, k), start=1):
        deg = store.in_degree(i) if store.directed else store.out_degree(i)
        rows.append((rank, store.external_id(i), f"{scores[i]:.6f}", deg))
    return rows


def cmd_pagerank(args) -> int:
    with _open(args.db) as store:
        result = pagerank(store, damping=args.damping, tol=args.tol, max_iter=args.max_iter)
        status = "converged" if result.converged else "did NOT converge"
        print(f"PageRank ({status} after {result.iterations} iterations, damping={args.damping})")
        print(_table(["rank", "node", "pagerank", "in-degree" if store.directed else "degree"],
                     _pagerank_rows(store, result.scores, args.top)))
    return 0


def _component_lines(name: str, comps, n: int, top: int) -> List[str]:
    sizes = sorted(comps.sizes, reverse=True)
    pct = 100.0 * comps.largest_size / n if n else 0.0
    lines = [f"{name}: {comps.count:,} component(s)",
             f"  largest size: {comps.largest_size:,} nodes ({pct:.1f}% of the graph)"]
    if top > 1 and len(sizes) > 1:
        lines.append("  top sizes   : " + ", ".join(f"{s:,}" for s in sizes[:top]))
    return lines


def cmd_components(args) -> int:
    with _open(args.db) as store:
        if args.kind in ("wcc", "both"):
            print("\n".join(_component_lines("Weakly connected components (WCC)",
                                             weakly_connected_components(store), store.n, args.top)))
        if args.kind in ("scc", "both"):
            print("\n".join(_component_lines("Strongly connected components (SCC)",
                                             strongly_connected_components(store), store.n, args.top)))
    return 0


def cmd_analyze(args) -> int:
    with _open(args.db) as store:
        pr = pagerank(store)
        wcc = weakly_connected_components(store)
        scc = strongly_connected_components(store)
        rows = _pagerank_rows(store, pr.scores, args.top)
        if args.json:
            print(json.dumps({
                "file": str(store.path), "nodes": store.n, "edges": store.num_edges,
                "directed": store.directed,
                "top_pagerank": [{"rank": r, "node": nd, "pagerank": float(s), "degree": d} for r, nd, s, d in rows],
                "wcc": {"count": wcc.count, "largest_size": wcc.largest_size},
                "scc": {"count": scc.count, "largest_size": scc.largest_size},
            }, indent=2))
            return 0
        print(f"GraphNexus analysis of {store.path}")
        print(f"  {store.n:,} nodes, {store.num_edges:,} edges ({_kind(store)})\n")
        print(f"Top {len(rows)} nodes by PageRank")
        print(_table(["rank", "node", "pagerank", "in-degree" if store.directed else "degree"], rows))
        print()
        print("\n".join(_component_lines("Weakly connected components (WCC)", wcc, store.n, 1)))
        print("\n".join(_component_lines("Strongly connected components (SCC)", scc, store.n, 1)))
    return 0


def cmd_benchmark(args) -> int:
    with _open(args.db) as store:
        try:
            report = run_benchmark(store, queries=args.queries, traversals=args.traversals, seed=args.seed)
        except ValueError as exc:
            raise CliError(str(exc)) from exc
    print(json.dumps(report.to_dict(), indent=2) if args.json else format_report(report))
    return 0


def cmd_generate(args) -> int:
    try:
        edges = generate_social_graph(args.nodes, args.attach, args.triad_prob, args.seed)
    except DatasetError as exc:
        raise CliError(str(exc)) from exc
    header = (f"Synthetic social network (Holme-Kim model), nodes={args.nodes}, "
              f"attach={args.attach}, triad_prob={args.triad_prob}, seed={args.seed}\nUndirected edge list")
    write_edge_list(args.output, edges, header)
    print(f"Wrote {len(edges):,} edges over {args.nodes:,} nodes to {args.output}")
    return 0


def cmd_download(args) -> int:
    info = SNAP_DATASETS[args.name]
    print(f"Downloading {args.name}: {info.description}")
    try:
        path = download_dataset(args.name, args.dest)
    except DatasetError as exc:
        raise CliError(str(exc)) from exc
    flag = " --directed" if info.directed else ""
    print(f"Saved to {path}\nNext: graphnexus import {path} {args.name}.gnx{flag}")
    return 0


# --------------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="graphnexus", description="GraphNexus: a lightweight graph database.")
    p.add_argument("--version", action="version", version=f"graphnexus {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    def add(name: str, func, help_: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.set_defaults(func=func)
        return sp

    s = add("import", cmd_import, "Build a .gnx database from an edge-list file (.txt / .gz)")
    s.add_argument("edge_list")
    s.add_argument("output", help="database file to create, e.g. graph.gnx")
    s.add_argument("--directed", action="store_true", help="treat edges as directed (default: undirected)")

    s = add("info", cmd_info, "Show database statistics")
    s.add_argument("db")
    s.add_argument("--verify", action="store_true", help="also verify the file checksum")

    s = add("node", cmd_node, "Look up a node and its neighbours (hash-index lookup)")
    s.add_argument("db"); s.add_argument("node", type=int)
    s.add_argument("--limit", type=int, default=20, help="max neighbours to print (default 20)")

    s = add("edge", cmd_edge, "Check whether an edge exists (hash-index lookup)")
    s.add_argument("db"); s.add_argument("source", type=int); s.add_argument("target", type=int)

    for name, func, text in (("bfs", cmd_bfs, "Breadth-first traversal from a node"),
                             ("dfs", cmd_dfs, "Depth-first traversal from a node")):
        s = add(name, func, text)
        s.add_argument("db"); s.add_argument("source", type=int)
        s.add_argument("--direction", choices=["out", "in", "both"], default="out")
        s.add_argument("--limit", type=int, default=20, help="max nodes to print (default 20)")
        if name == "bfs":
            s.add_argument("--max-depth", type=int, default=None)

    s = add("path", cmd_path, "Shortest path (fewest hops) between two nodes")
    s.add_argument("db"); s.add_argument("source", type=int); s.add_argument("target", type=int)
    s.add_argument("--direction", choices=["out", "in", "both"], default="out")

    s = add("pagerank", cmd_pagerank, "Top nodes by PageRank")
    s.add_argument("db")
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--damping", type=float, default=0.85)
    s.add_argument("--tol", type=float, default=1e-9)
    s.add_argument("--max-iter", type=int, default=200)

    s = add("components", cmd_components, "Connected components (WCC / SCC) and the largest size")
    s.add_argument("db")
    s.add_argument("--kind", choices=["wcc", "scc", "both"], default="both")
    s.add_argument("--top", type=int, default=5, help="how many component sizes to list")

    s = add("analyze", cmd_analyze, "Summary: top PageRank nodes and largest connected component sizes")
    s.add_argument("db")
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--json", action="store_true")

    s = add("benchmark", cmd_benchmark, "Benchmark lookup / traversal / algorithm latency")
    s.add_argument("db")
    s.add_argument("--queries", type=int, default=10_000, help="point lookups per metric")
    s.add_argument("--traversals", type=int, default=50, help="full traversals per metric")
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--json", action="store_true")

    s = add("generate", cmd_generate, "Generate a synthetic social network edge list (offline demo data)")
    s.add_argument("output")
    s.add_argument("--nodes", type=int, default=4039)
    s.add_argument("--attach", type=int, default=22, help="edges added per new node (default 22 ~ ego-Facebook density)")
    s.add_argument("--triad-prob", type=float, default=0.6)
    s.add_argument("--seed", type=int, default=42)

    s = add("download", cmd_download, "Download a Stanford SNAP dataset")
    s.add_argument("name", choices=sorted(SNAP_DATASETS))
    s.add_argument("--dest", default="data", help="destination folder (default: data)")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
