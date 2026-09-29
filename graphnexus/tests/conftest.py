import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graphnexus import Graph, write_store  # noqa: E402


@pytest.fixture
def undirected_graph():
    # two triangles joined by a bridge (3-4), plus a separate edge component (10-11)
    edges = [(1, 2), (2, 3), (3, 1), (3, 4), (4, 5), (5, 6), (6, 4), (10, 11)]
    return Graph.from_edges(edges, directed=False)


@pytest.fixture
def directed_graph():
    # SCCs: {1,2,3} cycle, {4,5} cycle, {6} alone; 3->4 and 5->6 link them; 7 is isolated-out
    edges = [(1, 2), (2, 3), (3, 1), (3, 4), (4, 5), (5, 4), (5, 6), (7, 1)]
    return Graph.from_edges(edges, directed=True)


@pytest.fixture
def store_path(tmp_path, undirected_graph):
    path = tmp_path / "u.gnx"
    write_store(path, undirected_graph)
    return path


@pytest.fixture
def directed_store_path(tmp_path, directed_graph):
    path = tmp_path / "d.gnx"
    write_store(path, directed_graph)
    return path
