import random

import pytest

from graphnexus import (
    Graph, GraphStore, bfs, dfs, pagerank, shortest_path, strongly_connected_components, top_k,
    weakly_connected_components, write_store,
)


def ext(g, idxs):
    return [g.external_id(i) for i in idxs]


# ------------------------------------------------------------------------------- traversals
def test_bfs_order_and_distances(undirected_graph):
    g = undirected_graph
    r = bfs(g, 0)  # node 1
    assert ext(g, r.order) == [1, 2, 3, 4, 5, 6]
    assert {g.external_id(k): v for k, v in r.distance.items()} == {1: 0, 2: 1, 3: 1, 4: 2, 5: 3, 6: 3}


def test_bfs_max_depth(undirected_graph):
    r = bfs(undirected_graph, 0, max_depth=1)
    assert ext(undirected_graph, r.order) == [1, 2, 3]


def test_bfs_direction(directed_graph):
    g = directed_graph
    src = g.ext_ids.index(4)
    assert set(ext(g, bfs(g, src, direction="out").order)) == {4, 5, 6}
    assert set(ext(g, bfs(g, src, direction="in").order)) == {4, 5, 3, 2, 1, 7}
    assert len(bfs(g, src, direction="both").order) == g.n
    with pytest.raises(ValueError):
        bfs(g, src, direction="sideways")


def test_dfs_matches_recursive_preorder(undirected_graph):
    g = undirected_graph

    def recursive(u, seen, out):
        seen.add(u)
        out.append(u)
        for v in g.out_neighbors(u):
            if v not in seen:
                recursive(v, seen, out)
        return out

    assert dfs(g, 0) == recursive(0, set(), [])
    assert ext(g, dfs(g, 0)) == [1, 2, 3, 4, 5, 6]


def test_dfs_handles_very_deep_graph_without_recursion_error():
    n = 20_000
    g = Graph.from_edges([(i, i + 1) for i in range(n)], directed=True)
    assert len(dfs(g, 0)) == n + 1
    assert len(strongly_connected_components(g).sizes) == n + 1


def test_shortest_path(undirected_graph, directed_graph):
    g = undirected_graph
    assert ext(g, shortest_path(g, g.ext_ids.index(1), g.ext_ids.index(6))) == [1, 3, 4, 6]
    assert shortest_path(g, 0, g.ext_ids.index(10)) is None
    assert shortest_path(g, 0, 0) == [0]
    d = directed_graph
    assert shortest_path(d, d.ext_ids.index(1), d.ext_ids.index(6)) is not None
    assert shortest_path(d, d.ext_ids.index(6), d.ext_ids.index(1)) is None


def test_invalid_node_raises(undirected_graph):
    with pytest.raises(IndexError):
        bfs(undirected_graph, 99)


# --------------------------------------------------------------------------------- PageRank
def test_pagerank_sums_to_one_and_symmetry():
    g = Graph.from_edges([(1, 2), (2, 3), (3, 1)], directed=True)
    r = pagerank(g)
    assert r.converged and abs(sum(r.scores) - 1) < 1e-9
    assert max(r.scores) - min(r.scores) < 1e-9  # a cycle is perfectly symmetric


def test_pagerank_known_values_with_dangling_node():
    # 1 -> 2, 1 -> 3, 2 -> 3 ; node 3 is dangling. Closed-form check by fixed-point equation.
    g = Graph.from_edges([(1, 2), (1, 3), (2, 3)], directed=True)
    d = 0.85
    s = pagerank(g, damping=d, tol=1e-14, max_iter=1000).scores
    p1, p2, p3 = s
    assert abs(p1 - ((1 - d) / 3 + d * p3 / 3)) < 1e-9
    assert abs(p2 - ((1 - d) / 3 + d * (p1 / 2 + p3 / 3))) < 1e-9
    assert abs(p3 - ((1 - d) / 3 + d * (p1 / 2 + p2 + p3 / 3))) < 1e-9
    assert p3 > p2 > p1


def test_pagerank_argument_validation_and_top_k():
    g = Graph.from_edges([(1, 2)], directed=True)
    with pytest.raises(ValueError):
        pagerank(g, damping=1.0)
    with pytest.raises(ValueError):
        pagerank(g, max_iter=0)
    assert top_k([0.1, 0.5, 0.5, 0.2], 3) == [1, 2, 3]
    asymmetric = Graph.from_edges([(1, 2), (1, 3)], directed=True)
    result = pagerank(asymmetric, tol=1e-30, max_iter=1)
    assert not result.converged and result.iterations == 1


def test_pagerank_hub_ranks_first():
    g = Graph.from_edges([(0, i) for i in range(1, 10)], directed=False)
    scores = pagerank(g).scores
    assert top_k(scores, 1) == [0]


# ---------------------------------------------------------------------------- components
def test_wcc_undirected(undirected_graph):
    c = weakly_connected_components(undirected_graph)
    assert c.count == 2 and sorted(c.sizes) == [2, 6] and c.largest_size == 6
    assert c.sizes[c.largest_component()] == 6


def test_scc_and_wcc_directed(directed_graph):
    g = directed_graph
    scc = strongly_connected_components(g)
    assert sorted(scc.sizes) == [1, 1, 2, 3]
    assert scc.largest_size == 3
    wcc = weakly_connected_components(g)
    assert wcc.count == 1 and wcc.largest_size == 7
    label = {g.external_id(i): scc.labels[i] for i in range(g.n)}
    assert label[1] == label[2] == label[3] and label[4] == label[5]
    assert len({label[1], label[4], label[6], label[7]}) == 4


def test_scc_equals_wcc_for_undirected(undirected_graph):
    assert sorted(strongly_connected_components(undirected_graph).sizes) == \
        sorted(weakly_connected_components(undirected_graph).sizes)


# ----------------------------------------------- cross-validation against NetworkX (if present)
nx = pytest.importorskip("networkx")


def _random_edges(n, m, seed):
    rng = random.Random(seed)
    return [(rng.randrange(n), rng.randrange(n)) for _ in range(m)]


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("directed", [True, False])
def test_matches_networkx(seed, directed, tmp_path):
    edges = _random_edges(60, 150, seed)
    g = Graph.from_edges(edges, directed=directed)
    path = tmp_path / "g.gnx"
    write_store(path, g)
    G = nx.DiGraph() if directed else nx.Graph()
    G.add_nodes_from(range(60))
    G.add_edges_from((u, v) for u, v in edges if u != v)
    G.remove_nodes_from([x for x in list(G.nodes) if x not in set(g.ext_ids)])

    with GraphStore(path) as store:
        for view in (g, store):
            ranks = pagerank(view, tol=1e-13, max_iter=500).scores
            expected = nx.pagerank(G, alpha=0.85, tol=1e-13, max_iter=500)
            for i in range(g.n):
                assert ranks[i] == pytest.approx(expected[g.external_id(i)], abs=1e-8)

            wcc = weakly_connected_components(view)
            nx_wcc = nx.weakly_connected_components(G) if directed else nx.connected_components(G)
            assert sorted(wcc.sizes) == sorted(len(c) for c in nx_wcc)

            scc = strongly_connected_components(view)
            nx_scc = nx.strongly_connected_components(G) if directed else nx.connected_components(G)
            assert sorted(scc.sizes) == sorted(len(c) for c in nx_scc)

            src = 0
            dist = bfs(view, src).distance
            expected_dist = nx.single_source_shortest_path_length(G, g.external_id(src))
            assert {g.external_id(k): v for k, v in dist.items()} == expected_dist
