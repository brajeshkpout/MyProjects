"""GraphNexus: a lightweight graph database with hash-based indexing and a binary file format."""
from .algorithms import (
    bfs, dfs, pagerank, shortest_path, strongly_connected_components, top_k,
    weakly_connected_components,
)
from .graph import Graph, load_graph
from .storage import GraphStore, StorageError, write_store

__version__ = "1.0.0"

__all__ = [
    "Graph", "GraphStore", "StorageError", "write_store", "load_graph",
    "bfs", "dfs", "shortest_path", "pagerank", "top_k",
    "weakly_connected_components", "strongly_connected_components",
]
