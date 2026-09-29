import struct

import pytest

from graphnexus import Graph, GraphStore, StorageError, write_store
from graphnexus.storage import HEADER_SIZE


def test_undirected_roundtrip(store_path, undirected_graph):
    with GraphStore(store_path) as s:
        assert s.n == undirected_graph.n == 8  # nodes 1..6, 10, 11
        assert s.num_edges == 8 and not s.directed
        assert s.verify()
        for i in range(s.n):
            assert list(s.out_neighbors(i)) == list(undirected_graph.out_neighbors(i))
            assert list(s.in_neighbors(i)) == list(s.out_neighbors(i))
            assert s.external_id(i) == undirected_graph.external_id(i)


def test_node_and_edge_lookup(store_path):
    with GraphStore(store_path) as s:
        assert s.node_index(1) == 0 and s.has_node(11) and not s.has_node(7)
        assert s.has_edge(3, 4) and s.has_edge(4, 3)  # undirected: both directions
        assert not s.has_edge(1, 6) and not s.has_edge(1, 999) and not s.has_edge(999, 1)
        assert s.neighbors_of(3) == [1, 2, 4]
        with pytest.raises(KeyError):
            s.neighbors_of(12345)
        with pytest.raises(IndexError):
            s.external_id(s.n)


def test_directed_roundtrip_and_direction(directed_store_path, directed_graph):
    with GraphStore(directed_store_path) as s:
        assert s.directed and s.verify()
        assert s.has_edge(3, 4) and not s.has_edge(4, 3)
        assert s.neighbors_of(3, "out") == [1, 4] and s.neighbors_of(3, "in") == [2]
        assert s.out_degree(s.node_index(3)) == 2 and s.in_degree(s.node_index(3)) == 1
        for i in range(s.n):
            assert list(s.in_neighbors(i)) == list(directed_graph.in_neighbors(i))


def test_all_edges_found_and_non_edges_rejected(tmp_path):
    import random
    rng = random.Random(3)
    edges = [(rng.randrange(1, 400), rng.randrange(1, 400)) for _ in range(3000)]
    g = Graph.from_edges(edges, directed=True)
    path = tmp_path / "r.gnx"
    write_store(path, g)
    have = {(u, v) for u, v in edges if u != v}
    with GraphStore(path) as s:
        assert s.num_edges == len(have)
        assert all(s.has_edge(u, v) for u, v in have)
        assert not any(s.has_edge(u, v) for u in range(1, 60) for v in range(1, 60) if (u, v) not in have)


def test_write_is_atomic_and_leaves_no_tmp(tmp_path, undirected_graph):
    path = tmp_path / "x.gnx"
    write_store(path, undirected_graph)
    assert path.exists() and not (tmp_path / "x.gnx.tmp").exists()


def test_bad_magic(tmp_path):
    p = tmp_path / "bad.gnx"
    p.write_bytes(b"NOPE" + b"\0" * 200)
    with pytest.raises(StorageError, match="magic"):
        GraphStore(p)


def test_too_small_and_missing(tmp_path):
    p = tmp_path / "tiny.gnx"
    p.write_bytes(b"GNX1")
    with pytest.raises(StorageError):
        GraphStore(p)
    with pytest.raises(StorageError):
        GraphStore(tmp_path / "missing.gnx")


def test_truncated_file_detected(store_path):
    data = store_path.read_bytes()
    store_path.write_bytes(data[:-16])
    with pytest.raises(StorageError, match="size mismatch"):
        GraphStore(store_path)


def test_bitflip_detected_by_checksum(store_path):
    data = bytearray(store_path.read_bytes())
    data[HEADER_SIZE + 3] ^= 0xFF
    store_path.write_bytes(bytes(data))
    with GraphStore(store_path) as s:
        assert not s.verify()


def test_unsupported_version(store_path):
    data = bytearray(store_path.read_bytes())
    struct.pack_into("<H", data, 4, 99)
    store_path.write_bytes(bytes(data))
    with pytest.raises(StorageError, match="version"):
        GraphStore(store_path)
