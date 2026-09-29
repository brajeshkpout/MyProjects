# GraphNexus | Graph Database Management System

A lightweight graph database written in pure Python (**zero runtime dependencies**). It stores graphs in a compact
**binary file format**, finds nodes and edges through **custom hash-based indexes**, and ships core graph algorithms
(**BFS/DFS, PageRank, weakly/strongly connected components**) plus a **CLI** for running queries and network analysis
on real-world datasets such as the Stanford SNAP social networks.

## Features

- **Custom hash indexing**: open-addressing hash tables (linear probing, SplitMix64 hash, load factor <= 0.5) for
  node lookup (`external id -> node`) and edge lookup (`(u, v)` membership). They are stored *inside* the file, so
  opening a database never rebuilds an index.
- **Simple binary storage**: CSR adjacency arrays + index tables, memory-mapped on read, atomic writes, CRC-32
  integrity check. Full spec in [`docs/FORMAT.md`](docs/FORMAT.md).
- **Algorithms**: BFS, DFS (both iterative, no recursion limit), shortest path, PageRank (power iteration with
  dangling-node handling), WCC (union-find) and SCC (iterative Tarjan). They run directly on the on-disk data.
- **Directed and undirected graphs**, SNAP-style edge lists (`.txt` and `.txt.gz`).
- **Benchmark tool** measuring lookup, traversal and algorithm latency.
- **CLI** to import data, query nodes/edges, traverse, rank nodes by PageRank and report the largest connected component.
- Cross-checked against NetworkX in the test suite (PageRank, WCC, SCC, BFS distances on random directed/undirected graphs).

## Install

Requires **Python 3.9+**.

```bash
git clone https://github.com/<your-username>/graphnexus.git
cd graphnexus
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .                                       # installs the `graphnexus` command
# (or run without installing:  python -m graphnexus ...)
```

## Quick start

```bash
# 1. Get data: the 4,039-node Stanford SNAP ego-Facebook network...
graphnexus download facebook                           # saves data/facebook_combined.txt.gz
graphnexus import data/facebook_combined.txt.gz facebook.gnx

#    ...or, offline, a synthetic social network of the same size:
graphnexus generate data/generated.txt
graphnexus import data/generated.txt facebook.gnx

# 2. Explore
graphnexus info facebook.gnx --verify
graphnexus analyze facebook.gnx                        # top PageRank nodes + largest component size
graphnexus benchmark facebook.gnx
```

Tiny sample graphs are included: `data/sample_undirected.txt` and `data/sample_directed.txt` (add `--directed` when importing the latter).

## CLI reference

| Command | What it does |
|---|---|
| `import EDGELIST OUT.gnx [--directed]` | Build a database from an edge list (self-loops and duplicates are dropped and reported) |
| `info DB [--verify]` | Node/edge counts, type, file size, optional checksum verification |
| `node DB ID [--limit N]` | Hash-index lookup of a node, its degree and neighbours |
| `edge DB U V` | Hash-index lookup of an edge (exit code 0 if it exists, 2 if not) |
| `bfs DB SRC [--max-depth N] [--direction out\|in\|both]` | Breadth-first traversal with distances |
| `dfs DB SRC [--direction ...]` | Depth-first pre-order traversal |
| `path DB SRC DST` | Shortest path (fewest hops) |
| `pagerank DB [--top K] [--damping D] [--tol T] [--max-iter N]` | Top-K nodes by PageRank |
| `components DB [--kind wcc\|scc\|both]` | Component counts and largest component size |
| `analyze DB [--top K] [--json]` | One-shot report: top PageRank nodes and largest WCC/SCC |
| `benchmark DB [--queries N] [--traversals N] [--json]` | Latency benchmark |
| `generate OUT.txt [--nodes N --attach M --seed S]` | Synthetic social network (offline demo data) |
| `download {facebook,wiki-vote,gnutella08}` | Download a SNAP dataset |

Node ids on the command line are the ids used in your edge list.

Example (`analyze` on the sample graph):

```text
$ graphnexus import data/sample_undirected.txt sample.gnx
$ graphnexus analyze sample.gnx --top 3
```

## Python API

```python
from graphnexus import load_graph, write_store, GraphStore, bfs, pagerank, top_k, weakly_connected_components

write_store("social.gnx", load_graph("data/facebook_combined.txt.gz"))   # build once

with GraphStore("social.gnx") as db:
    idx = db.node_index(107)              # hash-index lookup: external id -> dense index
    db.has_edge(0, 1)                     # hash-index edge lookup
    db.neighbors_of(0)                    # neighbour ids of node 0

    scores = pagerank(db).scores          # algorithms run directly on the file
    best = top_k(scores, 5)
    print([(db.external_id(i), scores[i]) for i in best])

    print(weakly_connected_components(db).largest_size)
    print(len(bfs(db, idx).order))
```

## Architecture

```
edge list (.txt/.gz) -> Graph (dense ids, sorted adjacency) -> write_store -> .gnx file
                                                                              |
      CLI / Python API -> GraphStore (mmap) -> hash-index lookups + CSR adjacency reads -> algorithms
```

```
graphnexus/
├── hashindex.py    custom open-addressing hash tables (node + edge index)
├── graph.py        in-memory Graph model, edge-list reader/writer
├── storage.py      binary format writer + memory-mapped GraphStore reader
├── algorithms.py   BFS, DFS, shortest path, PageRank, WCC, SCC
├── benchmark.py    latency benchmarks
├── datasets.py     SNAP downloader + synthetic social-graph generator
└── cli.py          command-line interface
```

## Benchmarks

`graphnexus benchmark` times each operation individually (`time.perf_counter_ns`) with a fixed random seed.
Sample run on a **synthetic 4,039-node / 88,605-edge social graph** (same scale as SNAP ego-Facebook), pure Python 3.12
in a small Linux container. Your numbers will differ by machine and dataset, so run the command on your own data.

| Operation | Mean | Median | p95 |
|---|---|---|---|
| Node lookup (hash index) | 1.15 us | 0.93 us | 1.90 us |
| Edge lookup (hash index) | 3.89 us | 2.88 us | 6.35 us |
| Neighbour query (id -> neighbour ids) | 12.2 us | 8.8 us | 27.8 us |
| BFS, full traversal | 14.3 ms | 12.5 ms | 20.6 ms |
| DFS, full traversal | 13.9 ms | 13.5 ms | 18.9 ms |
| Shortest path | 0.39 ms | 0.29 ms | 1.26 ms |
| PageRank (to 1e-9) | 108 ms | 108 ms | 109 ms |
| WCC / SCC (whole graph) | 35 ms / 41 ms | 34 ms / 35 ms | 39 ms / 55 ms |

## Tests

```bash
pip install -e ".[dev]"
python -m pytest
```

The suite (69 tests, offline) covers the hash index (collisions, negative/huge ids), the file format (round trips,
truncation, bit flips, bad magic/version), all algorithms (hand-computed cases plus NetworkX cross-validation),
edge-list parsing and the CLI.

## Design notes and limitations

- Databases are **read-only after import** (build once, query many times); rebuild to change the graph.
- Node ids must be integers (signed 64-bit). Self-loops and parallel edges are dropped on import.
- Graphs are limited to about 4.29 billion nodes (32-bit dense indexes). Import builds the graph in memory first,
  so very large graphs need enough RAM for that step; reads afterwards are memory-mapped.
- Pure Python favours clarity over raw speed. The file format and algorithms would port directly to C++/Rust.

## License

MIT, see [LICENSE](LICENSE). Replace `[Your Name]` in the license before publishing.
